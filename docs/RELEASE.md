# Release verification

Release 1 uses three real recorded mornings (19–21 October 2026), 72 replay frames and 54 frozen comparisons. The source archive remains outside Git. Published recordings are compact, attributed derivatives; disruptions and recovery services are simulations. Read [findings](FINDINGS.md) for the measured outcome and its limits.

## Evidence and authorization

`configs/release-evidence.json` is deliberately an empty template. Actual candidate evidence is generated locally in ignored storage and exported as reviewed release assets, avoiding a self-referential commit hash.

Every gate report names the exact candidate Git revision, scope, hashed check artifacts and a concrete coordinator acceptance. The required gates are:

- Five complete six-hour weekday recording windows; three selected morning dates.
- A clean, frozen candidate revision.
- Scoped independent OpenTripPlanner checks and documented disagreements.
- At least 100 journey measurements with p95 below two seconds.
- Source permissions, attribution and derivative database availability.
- Credential/private-data inspection and successful candidate CI.
- Browser walkthrough without the backend and exact public artifact verification.

The release assets include reports, acceptance records, checksums and the exact deployed site identity. A checked box or an arbitrary filename cannot substitute for those artifacts. The publisher reply was supplied by the project owner; its sender headers were not authenticated by this software. The private correspondence and contact details are not redistributed.

## Two local phases

1. Prepare a source-eligible public candidate with `python scripts/prepare_morning_bundle.py --public --candidate --output <new-directory>`. Set `RESILIENCE_RELEASE_EVIDENCE` to the ignored evidence file. This requires complete source windows, selected dates and reviewed licensing. The catalog retains its historical preparation state; that state does not authorize a deployment.
2. After all artifact checks, run `python scripts/verify_release.py --bundle <candidate-directory>`. This checks the exact file set and manifest identity against the accepted report and requires every final gate. Another bundle cannot inherit approval.

## Deployment boundary

GitHub Pages serves the reviewed static site and cannot access the local raw archive or run custom calculations. The local application retains collection, routing and custom experiments. The public demo reads lazy replay bundles and completed comparisons with no backend dependency.

The manually dispatched Pages workflow downloads `github-pages-site.zip` from the specified release in this repository. The dispatched ref, release tag and attested candidate must match. A pinned outer ZIP hash, a full site manifest (including HTML and JavaScript), a compact data manifest and eleven strictly true gates are checked by `scripts/verify_deployment.py` before extraction or deployment. No private source archive is required on the runner.

Python verification runs on Linux, macOS and Windows. Frontend verification installs the lock, runs tests and builds production assets. The first public release is authorized only after candidate CI and the local checks pass; final public access and deployed data hashes are then checked separately.

For reproduction use [REPRODUCTION.md](REPRODUCTION.md). Download the release's `verification-evidence.zip` and `SHA256SUMS.txt` for the candidate-specific proof. Later code changes require a fresh candidate and acceptance; an old green badge does not approve changed code or data.
