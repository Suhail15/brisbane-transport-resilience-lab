from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import warnings
import zipfile

import pytest

from scripts import verify_deployment as deployment


CANDIDATE = "a" * 40
GATE_NAMES = {
    "five_complete_windows",
    "three_real_morning_bundles",
    "candidate_revision",
    "candidate_code_clean",
    "independent_otp",
    "performance",
    "licences",
    "secrets",
    "ci",
    "static_demo",
    "public_artifacts",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _build_package(
    directory: Path,
    *,
    site_mutations=None,
    removed_entries=(),
    extra_entries=(),
    duplicate_entry=None,
    special_entries=(),
    attestation_updates=None,
    gate_updates=None,
    removed_gates=(),
    release_gate_updates=None,
    data_manifest_updates=None,
    site_manifest_updates=None,
):
    site_files = {
        "index.html": b"<!doctype html><main>public demo</main>",
        "assets/app.js": b"document.querySelector('main');",
        "catalog.json": b'{"compact":true,"preview_only":false}',
        "experiments/index.json": b'{"runs":[]}',
    }
    data_manifest = {
        "version": 1,
        "public": True,
        "compact": True,
        "candidate_preparation_only": False,
        "files": {
            "catalog.json": _sha(site_files["catalog.json"]),
            "experiments/index.json": _sha(site_files["experiments/index.json"]),
        },
    }
    data_manifest.update(data_manifest_updates or {})
    data_manifest_bytes = _json_bytes(data_manifest)
    site_files["manifest.json"] = data_manifest_bytes
    site_manifest = {"version": 1, "files": {name: _sha(data) for name, data in site_files.items()}}
    site_manifest.update(site_manifest_updates or {})
    site_manifest_bytes = _json_bytes(site_manifest)
    gates = {name: True for name in GATE_NAMES}
    gates.update(gate_updates or {})
    for name in removed_gates:
        gates.pop(name, None)
    attestation = {
        "schema_version": 1,
        "candidate_revision": CANDIDATE,
        "data_manifest_sha256": _sha(data_manifest_bytes),
        "site_manifest_sha256": _sha(site_manifest_bytes),
        "release_gate": {"passed": True, "gates": gates, **(release_gate_updates or {})},
    }
    attestation.update(attestation_updates or {})

    entries = [
        ("attestation.json", _json_bytes(attestation), None),
        ("site-manifest.json", site_manifest_bytes, None),
    ]
    for name, data in site_files.items():
        entries.append((f"site/{name}", (site_mutations or {}).get(name, data), None))
    entries = [entry for entry in entries if entry[0] not in set(removed_entries)]
    entries.extend((name, data, None) for name, data in extra_entries)
    entries.extend(special_entries)

    archive_path = directory / "deployment.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data, external_attr in entries:
                # ZipInfo normalizes backslashes on Windows. Preserve the deliberately
                # malformed member bytes so every OS tests the same rejection.
                info = zipfile.ZipInfo(name)
                info.filename = name
                info.compress_type = zipfile.ZIP_DEFLATED
                if external_attr is not None:
                    info.create_system = 3
                    info.external_attr = external_attr
                archive.writestr(info, data)
            if duplicate_entry:
                info = zipfile.ZipInfo(duplicate_entry)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, b"duplicate")
    return archive_path, _sha(archive_path.read_bytes()), CANDIDATE, site_files


def _run_cli(archive_path: Path, digest: str, candidate: str, output_dir: Path):
    script = Path(__file__).resolve().parents[2] / "scripts" / "verify_deployment.py"
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--archive",
            str(archive_path),
            "--expected-sha256",
            digest,
            "--candidate-revision",
            candidate,
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_rejected_without_output(archive_path, digest, candidate, output_dir, match=None):
    with pytest.raises(deployment.VerificationError, match=match):
        deployment.verify_deployment(archive_path, digest, candidate, output_dir)
    assert not output_dir.exists()


def test_cli_verifies_package_and_preserves_all_member_bytes(tmp_path):
    archive_path, digest, candidate, site_files = _build_package(tmp_path)
    output_dir = tmp_path / "verified"

    result = _run_cli(archive_path, digest, candidate, output_dir)

    assert result.returncode == 0, result.stderr
    assert "Verified" in result.stdout
    assert (output_dir / "attestation.json").is_file()
    assert (output_dir / "site-manifest.json").is_file()
    for relative_path, data in site_files.items():
        assert (output_dir / "site" / relative_path).read_bytes() == data


def test_cli_rejects_changed_outer_archive_before_creating_output(tmp_path):
    archive_path, digest, candidate, _ = _build_package(tmp_path)
    output_dir = tmp_path / "verified"

    result = _run_cli(archive_path, "0" * 64, candidate, output_dir)

    assert result.returncode == 1
    assert "pinned digest" in result.stderr
    assert not output_dir.exists()


def test_candidate_revision_must_match_attestation(tmp_path):
    archive_path, digest, candidate, _ = _build_package(tmp_path)

    _assert_rejected_without_output(archive_path, digest, "b" * 40, tmp_path / "verified", "Candidate revision")


@pytest.mark.parametrize(
    ("gate_updates", "message"),
    [({"performance": False}, "strictly true"), ({"performance": 1}, "strictly true"), ({"unreviewed": True}, "exactly the eleven")],
)
def test_all_eleven_release_gates_must_be_strictly_true(tmp_path, gate_updates, message):
    archive_path, digest, candidate, _ = _build_package(tmp_path, gate_updates=gate_updates)

    _assert_rejected_without_output(archive_path, digest, candidate, tmp_path / "verified", message)


def test_missing_release_gate_is_rejected(tmp_path):
    archive_path, digest, candidate, _ = _build_package(tmp_path, removed_gates=("ci",))

    _assert_rejected_without_output(archive_path, digest, candidate, tmp_path / "verified", "exactly the eleven")


def test_release_gate_passed_marker_must_be_true(tmp_path):
    archive_path, digest, candidate, _ = _build_package(tmp_path, release_gate_updates={"passed": False})

    _assert_rejected_without_output(archive_path, digest, candidate, tmp_path / "verified", "Release gate did not pass")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"site_mutations": {"index.html": b"altered site bytes"}}, "Site file SHA256 mismatch"),
        ({"data_manifest_updates": {"files": {"catalog.json": "0" * 64}}}, "Data and site manifest hashes differ"),
        ({"attestation_updates": {"data_manifest_sha256": "0" * 64}}, "Data manifest SHA256 mismatch"),
        ({"attestation_updates": {"site_manifest_sha256": "0" * 64}}, "Site manifest SHA256 mismatch"),
        ({"data_manifest_updates": {"public": False}}, "Data manifest is not public"),
        ({"data_manifest_updates": {"compact": False}}, "Data manifest is not compact"),
    ],
)
def test_manifest_and_attested_hashes_are_checked(tmp_path, kwargs, message):
    archive_path, digest, candidate, _ = _build_package(tmp_path, **kwargs)

    _assert_rejected_without_output(archive_path, digest, candidate, tmp_path / "verified", message)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"extra_entries": [("README.md", b"extra")]}, "Unexpected outer ZIP path"),
        ({"removed_entries": ("site/catalog.json",)}, "Site regular-file set differs"),
        ({"removed_entries": ("site-manifest.json",)}, "missing its attestation or site manifest"),
        ({"extra_entries": [("site/../escape.txt", b"escape")]}, "Non-canonical ZIP path"),
        ({"duplicate_entry": "site/index.html"}, "Duplicate ZIP entry names"),
        ({"special_entries": [("site/link", b"index.html", (stat.S_IFLNK | 0o777) << 16)]}, "Symlink or special ZIP entry"),
        ({"special_entries": [("site/fifo", b"", (stat.S_IFIFO | 0o600) << 16)]}, "Symlink or special ZIP entry"),
    ],
)
def test_invalid_outer_members_are_rejected_without_output(tmp_path, kwargs, message):
    archive_path, digest, candidate, _ = _build_package(tmp_path, **kwargs)

    _assert_rejected_without_output(archive_path, digest, candidate, tmp_path / "verified", message)


@pytest.mark.parametrize(
    ("limit_name", "limit_value", "message"),
    [
        ("MAX_MEMBER_UNCOMPRESSED_BYTES", 1, "individual size limit"),
        ("MAX_TOTAL_UNCOMPRESSED_BYTES", 1, "total uncompressed size limit"),
        ("MAX_ARCHIVE_BYTES", 1, "compressed size limit"),
        ("MAX_ARCHIVE_ENTRIES", 1, "entry-count limit"),
    ],
)
def test_archive_limits_fail_before_output_creation(tmp_path, monkeypatch, limit_name, limit_value, message):
    archive_path, digest, candidate, _ = _build_package(tmp_path)
    monkeypatch.setattr(deployment, limit_name, limit_value)

    _assert_rejected_without_output(archive_path, digest, candidate, tmp_path / "verified", message)


def test_existing_output_directory_is_never_overwritten(tmp_path):
    archive_path, digest, candidate, _ = _build_package(tmp_path)
    output_dir = tmp_path / "existing"
    output_dir.mkdir()

    with pytest.raises(deployment.VerificationError, match="must not already exist"):
        deployment.verify_deployment(archive_path, digest, candidate, output_dir)

    assert list(output_dir.iterdir()) == []


@pytest.mark.parametrize(
    "path",
    ["/site/absolute", "site/a\\b", "site/../escape", "site/C:/drive", "site/C:escape.txt", "site/file.txt:stream"],
)
def test_noncanonical_paths_are_rejected(tmp_path, path):
    archive_path, digest, candidate, _ = _build_package(tmp_path, extra_entries=[(path, b"bad")])
    with zipfile.ZipFile(archive_path) as archive:
        # filename/namelist normalize backslashes again when reading on Windows.
        # orig_filename is the raw central-directory spelling on every platform.
        assert path in {info.orig_filename for info in archive.infolist()}

    _assert_rejected_without_output(archive_path, digest, candidate, tmp_path / "verified", "Unsafe|Absolute|Non-canonical|Drive-qualified")


@pytest.mark.parametrize(
    ("original", "normalized"),
    [("site/a\\b", "site/a/b"), ("site/index.html\x00ignored", "site/index.html")],
)
def test_original_member_spelling_is_checked_before_host_normalization(original, normalized):
    # Model ZipInfo's Windows separator normalization and all-host NUL truncation
    # explicitly, so a POSIX test run also exercises the Windows security boundary.
    info = zipfile.ZipInfo(original)
    info.filename = normalized
    assert info.orig_filename == original and info.filename != info.orig_filename

    with pytest.raises(deployment.VerificationError, match="Unsafe"):
        deployment._check_file_entry(info)
