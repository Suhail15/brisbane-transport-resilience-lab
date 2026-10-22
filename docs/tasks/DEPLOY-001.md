# DEPLOY-001: verify pinned static deployment packages

- **Task ID:** DEPLOY-001
- **Status:** implementation complete; coordinator integration pending
- **Owner:** bounded implementation
- **Reviewer:** coordinator

## Model and reasoning

- Requested model: GPT-6 Luna Max
- Reasoning effort: max
- Serving identity is not independently introspectable.

## Approved specification and decisions

- Relevant approval: Decision 28 in `docs/DECISIONS.md`, approved 2026-10-22.
- Preserve the local all-gates attestation boundary. The verifier checks the pinned bytes and supplied attestation; it does not recompute private release gates, execute extracted code, make network calls, or publish files.
- The output directory must be new. All archive members and hashes are validated before the output directory is created; copying is manual and uses the validated regular-file entries only.

## Required inputs and dependencies

- Required inputs: deployment ZIP, pinned outer SHA256, expected 40-hex candidate revision, and a nonexistent output directory whose parent exists.
- Dependencies: Python standard library only. Limits are 10,000 entries, 500 MiB compressed archive, 2 GiB total uncompressed, and 100 MiB per member.
- Approval evidence: Decision 28 specifies the deployment ZIP layout, attestation, manifests, gate set, and extraction boundary.

## Files owned

- `scripts/verify_deployment.py`
- `tests/integration/test_deployment_integrity.py`
- `docs/tasks/DEPLOY-001.md`

## Expected output

The CLI accepts `--archive PATH --expected-sha256 HEX --candidate-revision 40HEX --output-dir NEWDIR`. It verifies exact outer membership (`attestation.json`, `site-manifest.json`, and regular `site/*` files), safe canonical paths, unique entries, file types and limits; checks candidate revision, exactly eleven strictly true release gates, the public compact data manifest, full site manifest membership, and all recorded hashes; then extracts the validated package tree to the new output directory.

## Acceptance checks

- [x] Valid synthetic package accepted through the CLI; extracted bytes match all ZIP members.
- [x] Changed pinned digest, candidate mismatch, missing or extra gates, false or non-boolean gate values, false passed marker, invalid public/compact data manifest, and bad site/data hashes are rejected.
- [x] Extra, missing, unsafe, duplicate, symlink, and FIFO members are rejected. Archive, entry-count, individual-file, and total-uncompressed limits are exercised with reduced test thresholds.
- [x] Every rejection test confirms the output directory was not created; an existing empty output directory remains untouched.
- [x] `.venv/bin/python -m pytest tests/integration/test_deployment_integrity.py -q` — 30 passed.
- [x] `git diff --check` — passed.
- [x] The CLI imports only Python standard-library modules; no extracted content is executed and no network or publishing operation is called.

## Escalation issues

None. Workflow integration, creation of the real attestation, final gate evidence, and deployment remain coordinator-owned.
