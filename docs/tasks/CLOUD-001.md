# CLOUD-001 — Draft-only offline cell verification

- Status: implemented locally; coordinator source review and cloud smoke pending
- Owner: integration engineer
- Reviewer: root

## Model and reasoning

GPT-6.1-sol, medium, explicitly assigned by root. No subagents.

## Approved specification and decisions

Root approved a bounded, manual GitHub Actions acceleration for offline verification
only while the unchanged local production workers continue. The input is a reviewed
normalized pack ZIP on an unpublished draft release, pinned externally by ZIP and
original pack-manifest SHA-256. No raw archive is uploaded. Each fresh process
compares the complete recomputed result, including every route, against the stored
cell. Neither this task nor its workflow publishes a release or Pages content.

Root explicitly approved authenticated initial origins `https://api.github.com`
for metadata/download and the canonical own-repository release-assets path on
`https://uploads.github.com` for uploads. Every redirected download request strips
Authorization, including redirects back to the API. Upload paths are constructed
from the API-verified own-repository draft ID; arbitrary `upload_url` values are
never used. The coordinator owns draft creation, input upload, dispatch, smoke
review, result review and aggregation. No external transfer was made during local
implementation.

## Required inputs and dependencies

- Reviewed initializer-corrected normalized pack and externally pinned ZIP and
  manifest hashes; its source-code dependency lock must exactly match checkout.
- Own-repository unpublished draft release and input asset IDs.
- A scoped job `GITHUB_TOKEN` with contents write; the trusted transport parent
  retains it, and the calculation subprocess receives a small environment without
  token/secret/credential variables or Actions runtime credentials.
- GitHub-hosted `ubuntu-24.04`, Python 3.11, locked dependencies. The manual smoke
  is only 9 October budget 2 / delta 0; full mode is the exact registered 24 cells.
- Official API behavior references: [release assets](https://docs.github.com/en/rest/releases/assets)
  and [releases](https://docs.github.com/en/rest/releases/releases).

## Files owned

- `.github/workflows/case-study-review.yaml`
- `scripts/review_case_study_pack.py`
- `tests/integration/test_case_study_cloud_review.py`
- `docs/tasks/CLOUD-001.md`

Frozen producer, source normalizers, engine and protocol are unchanged.

## Expected output

A manual workflow with at most 8 concurrent per-cell jobs and a 330-minute per-cell timeout. Input downloads are
bounded to 512 MiB, ZIP expansion to 2 GiB / 512 members / 512 MiB per file. Extraction
rejects traversal, symlinks, duplicate names, unsafe paths, raw/archive material,
encrypted members and recognizable credential bytes. Strict manifest/file-set and
all file hashes are verified before frozen imports. Module locations and code hash
must match the pack; initial route cache is empty. The fresh child denies Python
network/DNS/HTTP access and original checkout data access during computation.

Each successful cell returns one uniquely named gzip JSON asset to the same draft,
containing its complete recomputed result, exact stored-cell hash, match status,
protocol/manifest/code hashes, worker hash, run ID/attempt/commit, ZIP hash, cell key,
Python version, elapsed time and isolation checks. Draft state is checked before
and after each transport operation. No Actions result artifact or plaintext
outcome log is created. Public logs contain only bounded failure reason codes or
a generic completion message; private child output is temporary and removed.

## Acceptance checks

- [x] Local focused tests: `python -B -m pytest -q tests/integration/test_case_study_cloud_review.py`
  passed 26/26; combined with the 6 exporter gates,32/32 passed in 0.91s. Synthetic transport tests cover Authorization stripping on
  redirects back to API, rejection of published/non-draft state, canonical upload
  path and digest, and unsafe origins. ZIP tests cover traversal/absolute/Windows
  paths, NUL normalization, symlinks, raw/nested archive material, credential markers and expansion
  limits. Exact24 plus separate smoke selection and the reviewed local fixture's
  pinned manifest/tamper gate pass. Seven self-contained fresh-subprocess cases prove exact full-route match, tampered-but-re-signed stored-result rejection, nonempty-cache rejection, network denial, credential-environment rejection, non-frozen preloaded-module rejection, and successful parent transport with all job/runtime tokens removed from the actual child. These tiny synthetic modules test wrapper boundaries only; they are not observed study outcomes or numerical parity evidence. Tests never contact GitHub.
- [x] Smoke matrix command emits only `2026-10-09:2:0`; full mode has 24 unique cells.
- [ ] Coordinator source/workflow review before commit or external execution.
- [ ] Actual cloud smoke with frozen normalized inputs, draft-only returned asset,
  full route equality, module/environment provenance and independent asset review.
- [ ] Full registered 24 result assets and independent exact-identity aggregation.

These remaining boxes are execution gates, not completed evidence. Existing local
production and the approved two-worker local offline fallback remain available.

## Escalation issues

No cloud authentication or packaging attempts have occurred. Abort acceleration
after two repeated authentication/packaging failures and preserve bounded evidence;
do not alter frozen calculations to obtain a result. This implementation is
limited to 60 minutes of setup/review. A cloud runner failure or mismatch must not
be presented as successful reproduction. Python audit guards establish the stated
trusted-code upstream restriction; this is not an OS sandbox for arbitrary hostile
code. External pins and coordinator-reviewed frozen source are required.
