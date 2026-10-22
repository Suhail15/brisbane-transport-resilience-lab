# ARCH-010

- Title: final release implementation review
- Status: bounded implementation review complete; discovered path defect resolved; exact public-artifact acceptance remains pending
- Owner: ARCH-010 independent review agent
- Reviewer: root coordinator

## Model and reasoning

- Requested model: GPT-6.1 Sol.
- Requested reasoning: max.
- Actual exposed configuration: inherited parent session. Serving model identity and reasoning effort are not independently introspectable. No additional agent was created.

## Approved specification and decisions

- Coordinator requests a bounded, read-only review under Decision 28 of the deployment verifier/workflow, static builder, public reproduction guard and new tests.
- GitHub receives the pinned deployment archive containing `attestation.json`, `site-manifest.json` and `site/*`; the private analytical/source checks remain local.
- Candidate generation history is distinct from the final eleven-gate deployment attestation. No gate, source cutoff or public eligibility rule may be weakened.
- Only this task handoff may be edited by this reviewer. Runtime/code/results and numerical analyses remain coordinator-owned.

## Required inputs and dependencies

- Reviewed `scripts/verify_deployment.py`, `.github/workflows/pages.yaml`, `frontend/scripts/build-static.mjs`, `frontend/vite.config.js`, `services/resilience/pipeline/reproduction.py`, and their new tests.
- Read supporting bundle/coverage/evidence adapters, morning packaging script, release/reproduction documentation, Decision 28, and DEPLOY-001/002 and PACK-001 handoffs.
- Deployment test evidence: `data/runtime/release-2026-10-22/deployment-tests.log`.
- Coordinator's final post-fix results are 204 Python checks passed with one optional skip, 23 frontend checks passed, two live API/PostGIS checks passed and all 54 offline exact recomputations in 508.35 seconds. These broader checks were not independently rerun during this bounded review.
- The exact public 72-frame/54-run candidate had not yet been prepared at dispatch; no claim of final candidate byte/content acceptance is made here.

## Files owned

- `docs/tasks/ARCH-010.md` only.

## Expected output

- Confirm the implemented Decision 28 boundary, identify concrete defects promptly, review their resolutions and distinguish remaining artifact-preparation work from implementation failures.
- Record actual evidence and limits so the coordinator can freeze the candidate revision and complete its exact artifact/privacy/release checks.

## Acceptance checks

- PASS, code review: deployment requires the pinned outer SHA-256 and 40-hex candidate revision, exactly eleven boolean-true gates, public/compact data flags, attested data/site manifest hashes, the exact site file set and every listed file hash. It rejects duplicate JSON keys, unsafe/duplicate/special ZIP members, encrypted entries and bounded archive/member/count sizes before creating a fresh output directory. Archive and member bytes are rechecked before copying; partial output is cleaned on copy failure. No extracted code is executed.
- PASS, code review: manually dispatched workflow checks out `github.sha`, resolves the same-repository release tag through annotated-tag objects and requires the same commit, finds exactly one uploaded named ZIP asset, validates input formats, limits downloads, strips API authorization from redirects and uploads only the verifier's extracted `site/` subtree. It does not check out or upload the raw archive. Attestation/private checks are not presented as rerun on GitHub.
- PASS, code review: frontend verifies an exact compact manifest/file set, hashes, safe references and regular files, rejects symlinks and full timetable headers, stages only those verified bytes into a new temporary directory, preserves the original manifest and cleans staging after the build. The explicit separately licensed walking database remains allowed without admitting a full timetable.
- PASS, code review: normal public export retains all final gates. Candidate preparation retains the three authorized preparation gates, and the exported preparation flag remains historical state. Deployment uses its separate all-gates attestation; it does not treat the preparation flag as permission. The null committed `configs/release-evidence.json` is an intentionally pending template; root selects its actual hashed evidence separately.
- PASS, code review: public reproduction candidate preflights nonempty unique explicit run IDs, completed nonlegacy immutable inputs, exactly three selected dates represented by eligible weekday morning snapshots, and same-day morning realtime receipts explicitly marked `development_capture: false`, before writing. Static GTFS/OSM retain existing integrity/cutoff checks without an invented morning receipt requirement. Private pack behavior remains separate.
- PASS, observed defect and fix: `_safe_relative_path('site/C:escape.txt')` originally accepted a nested Windows drive-relative component. Read-only `PureWindowsPath('D:/review-output').joinpath(...)` demonstrated extraction would resolve to `C:escape.txt` outside the selected output directory on Windows. Root changed validation to reject a colon in every component, also covering alternate data streams.
- PASS, independent targeted recheck after root's fix: `site/C:escape.txt`, `site/file.txt:stream` and `site/C:/drive` all raise `VerificationError`. Read the real-ZIP corruption cases for both newly found forms and the actual log reporting **32 deployment tests passed in 0.17s**. No repeat of the broader numerical/test workload was needed.
- PASS, test review: new tests cover valid extraction and byte preservation, bad digest/revision/manifests, strict gate typing/membership, unsafe/extra/missing/duplicate/symlink/FIFO ZIP entries, size/count ceilings and untouched output on failure. Frontend tests cover exact-byte staging, corrupted/missing/extra files, unsafe references, symlinks, compactness and an actual synthetic static build. Public pack tests cover date/window/development/legacy/missing-date rejection before output and unchanged private behavior.
- PENDING, exact artifact acceptance: verify the final public candidate has exactly the intended 72 replay frames and 54 frozen runs, inspect its actual data/site/reproduction file lists and contents, freeze both manifest identities, complete all eleven local evidence gates and attest the final bytes. This review found no further concrete implementation blocker; it is not a substitute for those checks.

## Escalation issues

- The Windows drive-relative path issue was escalated immediately and fixed by root. It did not escape on the current Ubuntu Pages runner, but contradicted the portable unsafe-entry boundary. The independent targeted recheck and added real-ZIP regression cases resolve the reported defect.
- Privacy scope: the intended compact exporter writes explicit display/choices/network/run/input/metadata paths and does not sweep raw source files or correspondence directories into the frontend. The static builder deliberately copies every file in the reviewed exact manifest; it is not a secret or privacy classifier. A deliberately added, newly manifested private document would therefore need to be caught by the mandatory local privacy/public-artifact review before attestation. No automatic correspondence exclusion is claimed beyond the explicit export/staging boundary.
- Reproduction packs intentionally contain selected source objects and receipts for offline execution and are separate release assets. Their manifest is not a compact frontend manifest and cannot be used directly as static data input. Optional supplementary files are explicit pack inputs and still require concrete content/licensing/privacy review; generation alone does not authorize publication.
- No final public ZIP, exact public site, GitHub dispatch, visibility change or deployment was performed by this task. The pending template and pending concrete-artifact checks are expected release work, not evidence that the boundary has failed. Root owns final candidate freezing and release acceptance.
