# Release preparation and verification

No data or site has been published by INT-003. Future complete mornings and
publisher approval remain missing. The current release check fails by design.

`configs/release-evidence.json` schema 2 binds a candidate Git revision, exactly
three selected complete morning dates and hashed reports for OTP, performance,
licences, secrets, candidate CI, static walkthrough and public artifacts. A boolean
and arbitrary reference cannot authorize release. Each report must identify its gate,
revision, scope and passed actual checks with hashed evidence artifacts. Root or
architecture acceptance must reference concrete reviewed bytes and their hash.
Performance requires at least 100 measurements and p95 below two seconds; publisher
approval must be received. Manual acceptance cannot replace absent recordings. Uncommitted executable/build
inputs cannot inherit approval for HEAD; the code/build working tree must be clean.
All nonignored staged/unstaged/untracked changes fail final authorization. Generated
data packs remain ignored. Keep the committed config as a pending template; place
actual candidate evidence in ignored `data/runtime/release-evidence.json` and set
`RESILIENCE_RELEASE_EVIDENCE` to that path after freezing the candidate commit.
This avoids a self-referential evidence/config commit revision.

## Two local phases

1. Prepare an eligible public candidate projection locally with
   `resilience export --public --candidate --output <fresh-directory>`. This requires
   five complete weekday recording windows, exactly three selected complete mornings,
   source provenance and licence/publisher eligibility. It uses the public integrity
   and legacy exclusion rules. Artifact-dependent static/manifest/CI acceptance can
   follow preparation; publication authorization remains false.
2. Record the candidate's exact manifest hash in its accepted `public_artifacts`
   report. Run `python scripts/verify_release.py --bundle <candidate-directory>`.
   This checks the exact candidate file set and every manifest hash, rejects unsafe
   paths and symlinks, binds the supplied manifest to the reviewed
   identity and requires every final gate. A different bundle cannot inherit approval.

`.github/workflows/pages.yaml` is a guarded preparation harness. It verifies eligible
immutable assets and runs mandatory frontend install/tests/build. It has no upload
or deployment action. The root coordinator will add/execute the publication step only
after final reviewed evidence passes, then verify public bytes/state against the
prepared manifest. The current private preview fails the verifier; no credentials or
remote visibility changes are involved.

Backend CI remains the macOS/Windows/Linux Python matrix. Frontend CI now always
requires the committed lock, installation, tests and production build. The older
private Verification run 36965117356 at fec68f7 passed the backend matrix; a new run
must validate the final candidate including the frontend.
