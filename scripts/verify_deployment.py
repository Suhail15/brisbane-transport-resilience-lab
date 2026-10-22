#!/usr/bin/env python3
"""Verify a pinned deployment ZIP before copying any files to a new directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import sys
import zipfile
import zlib


MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000

RELEASE_GATES = frozenset({
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
})


class VerificationError(ValueError):
    """The archive or its deployment evidence failed a required check."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_stream(handle) -> str:
    digest = hashlib.sha256()
    total = 0
    while chunk := handle.read(1024 * 1024):
        total += len(chunk)
        _require(total <= MAX_ARCHIVE_BYTES, "Deployment archive exceeds the compressed size limit")
        digest.update(chunk)
    return digest.hexdigest()


def _hex_digest(value, *, length: int, field: str) -> str:
    _require(isinstance(value, str) and re.fullmatch(rf"[0-9a-fA-F]{{{length}}}", value) is not None,
             f"{field} must be {length} hexadecimal characters")
    return value.lower()


def _safe_relative_path(value: str) -> str:
    _require(isinstance(value, str) and bool(value), "ZIP path must be a non-empty string")
    _require("\\" not in value and "\x00" not in value, f"Unsafe ZIP path: {value!r}")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    _require(not posix.is_absolute() and not windows.is_absolute() and not windows.root and not windows.drive,
             f"Absolute or drive-qualified ZIP path: {value!r}")
    _require(posix.as_posix() == value and all(part not in ("", ".", "..") for part in posix.parts),
             f"Non-canonical ZIP path: {value!r}")
    _require(not any(":" in part for part in posix.parts),
             f"Drive-qualified or stream ZIP path: {value!r}")
    return value


def _check_file_entry(info: zipfile.ZipInfo) -> str:
    name = _safe_relative_path(info.filename)
    _require(not info.is_dir(), f"Directory entries are not allowed: {name}")
    _require(not (info.flag_bits & 0x41), f"Encrypted ZIP entries are not allowed: {name}")
    _require(info.file_size >= 0 and info.compress_size >= 0, f"Invalid ZIP sizes: {name}")
    _require(info.file_size <= MAX_MEMBER_UNCOMPRESSED_BYTES,
             f"ZIP entry exceeds the individual size limit: {name}")
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    _require(file_type in (0, stat.S_IFREG), f"Symlink or special ZIP entry is not allowed: {name}")
    _require(not (info.external_attr & 0x10), f"Directory ZIP attributes are not allowed: {name}")
    _require(not (info.external_attr & 0x400), f"Reparse-point ZIP entry is not allowed: {name}")
    _require(name in ("attestation.json", "site-manifest.json") or name.startswith("site/"),
             f"Unexpected outer ZIP path: {name}")
    if name.startswith("site/"):
        _safe_relative_path(name[5:])
    return name


def _read_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    try:
        data = archive.read(info)
    except (OSError, EOFError, RuntimeError, NotImplementedError, zipfile.BadZipFile, zlib.error) as exc:
        raise VerificationError(f"Could not read ZIP entry {info.filename!r}: {exc}") from exc
    _require(len(data) == info.file_size, f"ZIP entry length differs from its header: {info.filename}")
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _json_document(data: bytes, name: str) -> dict:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise VerificationError(f"Invalid UTF-8 JSON in {name}: {exc}") from exc
    _require(isinstance(value, dict), f"{name} must contain a JSON object")
    return value


def _manifest_files(document: dict, name: str) -> dict[str, str]:
    files = document.get("files")
    _require(isinstance(files, dict), f"{name}.files must be an object")
    result = {}
    for relative_path, digest in files.items():
        _safe_relative_path(relative_path)
        result[relative_path] = _hex_digest(digest, length=64, field=f"{name}.files[{relative_path!r}]")
    return result


def _validate_attestation(document: dict, candidate_revision: str, entry_digests: dict[str, str]) -> None:
    fields = {"schema_version", "candidate_revision", "data_manifest_sha256", "site_manifest_sha256", "release_gate"}
    _require(set(document) == fields, "attestation.json has unexpected or missing fields")
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1,
             "Unsupported attestation schema_version")
    attested_revision = _hex_digest(document["candidate_revision"], length=40, field="candidate_revision")
    _require(attested_revision == candidate_revision, "Candidate revision does not match the requested revision")
    data_hash = _hex_digest(document["data_manifest_sha256"], length=64, field="data_manifest_sha256")
    site_hash = _hex_digest(document["site_manifest_sha256"], length=64, field="site_manifest_sha256")
    _require(data_hash == entry_digests["site/manifest.json"], "Data manifest SHA256 mismatch")
    _require(site_hash == entry_digests["site-manifest.json"], "Site manifest SHA256 mismatch")

    gate_report = document["release_gate"]
    _require(isinstance(gate_report, dict) and set(gate_report) == {"passed", "gates"},
             "release_gate must contain only passed and gates")
    _require(type(gate_report["passed"]) is bool and gate_report["passed"], "Release gate did not pass")
    gates = gate_report["gates"]
    _require(isinstance(gates, dict) and set(gates) == RELEASE_GATES,
             "Release gate must contain exactly the eleven approved gates")
    _require(all(type(value) is bool and value is True for value in gates.values()),
             "Every release gate must be strictly true")


def _validate_manifests(site_manifest: dict, data_manifest: dict, entry_digests: dict[str, str]) -> None:
    _require(set(site_manifest) == {"version", "files"}, "site-manifest.json has unexpected or missing fields")
    _require(type(site_manifest["version"]) is int and site_manifest["version"] == 1,
             "Unsupported site manifest version")
    site_files = _manifest_files(site_manifest, "site-manifest.json")
    actual_site_files = {name[5:] for name in entry_digests if name.startswith("site/")}
    _require("manifest.json" in actual_site_files, "site/manifest.json is missing")
    _require(set(site_files) == actual_site_files,
             "Site regular-file set differs from site-manifest.json")
    for relative_path, expected_digest in site_files.items():
        _require(expected_digest == entry_digests[f"site/{relative_path}"],
                 f"Site file SHA256 mismatch: {relative_path}")

    _require(data_manifest.get("public") is True, "Data manifest is not public")
    _require(data_manifest.get("compact") is True, "Data manifest is not compact")
    data_files = _manifest_files(data_manifest, "site/manifest.json")
    _require("manifest.json" not in data_files, "Data manifest must not hash itself")
    for relative_path, expected_digest in data_files.items():
        _require(relative_path != "index.html" and not relative_path.startswith("assets/"),
                 f"Static site asset is listed as compact data: {relative_path}")
        _require(relative_path in site_files, f"Data file is missing from the site manifest: {relative_path}")
        _require(expected_digest == site_files[relative_path],
                 f"Data and site manifest hashes differ: {relative_path}")


def verify_deployment(archive_path, expected_sha256: str, candidate_revision: str, output_dir):
    """Verify the pinned deployment ZIP, then extract its validated layout to a new directory."""
    archive_path = Path(archive_path)
    output_dir = Path(output_dir)
    expected_sha256 = _hex_digest(expected_sha256, length=64, field="expected SHA256")
    candidate_revision = _hex_digest(candidate_revision, length=40, field="candidate revision")

    _require(archive_path.is_file(), "Deployment archive is not a regular file")
    _require(archive_path.stat().st_size <= MAX_ARCHIVE_BYTES, "Deployment archive exceeds the compressed size limit")
    _require(not os.path.lexists(output_dir), "Output directory must not already exist")
    _require(output_dir.parent.is_dir(), "Output directory parent must already exist")

    try:
        with archive_path.open("rb") as archive_file:
            actual_archive_digest = _sha256_stream(archive_file)
            _require(actual_archive_digest == expected_sha256, "Deployment archive SHA256 does not match the pinned digest")
            archive_file.seek(0)
            with zipfile.ZipFile(archive_file, "r") as archive:
                infos = archive.infolist()
                _require(len(infos) <= MAX_ARCHIVE_ENTRIES, "Deployment archive exceeds the entry-count limit")
                names = [info.filename for info in infos]
                _require(len(names) == len(set(names)), "Duplicate ZIP entry names are not allowed")

                info_by_name = {}
                total_uncompressed = 0
                for info in infos:
                    name = _check_file_entry(info)
                    info_by_name[name] = info
                    total_uncompressed += info.file_size
                    _require(total_uncompressed <= MAX_TOTAL_UNCOMPRESSED_BYTES,
                             "Deployment archive exceeds the total uncompressed size limit")

                _require("attestation.json" in info_by_name and "site-manifest.json" in info_by_name,
                         "Deployment archive is missing its attestation or site manifest")
                _require("site/manifest.json" in info_by_name, "Deployment archive is missing site/manifest.json")

                entry_digests = {}
                documents = {}
                document_names = {"attestation.json", "site-manifest.json", "site/manifest.json"}
                for name, info in info_by_name.items():
                    payload = _read_entry(archive, info)
                    entry_digests[name] = _sha256_bytes(payload)
                    if name in document_names:
                        documents[name] = _json_document(payload, name)

                _validate_attestation(documents["attestation.json"], candidate_revision, entry_digests)
                _validate_manifests(documents["site-manifest.json"], documents["site/manifest.json"], entry_digests)

                # Recheck the pinned bytes before creating the output directory.
                archive_file.seek(0)
                _require(_sha256_stream(archive_file) == expected_sha256,
                         "Deployment archive changed during verification")

                output_dir.mkdir()
                try:
                    for name, info in info_by_name.items():
                        payload = _read_entry(archive, info)
                        _require(_sha256_bytes(payload) == entry_digests[name],
                                 f"Deployment archive changed after verification: {name}")
                        target = output_dir.joinpath(*PurePosixPath(name).parts)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with target.open("xb") as handle:
                            handle.write(payload)
                except BaseException:
                    shutil.rmtree(output_dir, ignore_errors=True)
                    raise
    except VerificationError:
        raise
    except (OSError, EOFError, RuntimeError, NotImplementedError, zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error) as exc:
        raise VerificationError(f"Could not verify deployment archive: {exc}") from exc

    return {"archive_sha256": expected_sha256, "candidate_revision": candidate_revision, "files": len(info_by_name)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify and extract a pinned static deployment package")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_deployment(args.archive, args.expected_sha256, args.candidate_revision, args.output_dir)
    except (VerificationError, OSError) as exc:
        print(f"Deployment verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified {result['files']} files for candidate {result['candidate_revision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
