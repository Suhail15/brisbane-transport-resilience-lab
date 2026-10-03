# Private offline reproduction

Use the matching repository revision and locked Python environment. No upstream
reload is used: saved requests, scenarios, candidate IDs, budgets and bounds are
recomputed from the recorded normalized snapshot or its hashed stress derivative.

The private INT-003 pack is under `data/derived/reproduction-int003-reviewed`. It includes
eight immutable completed runs, canonical inputs/metadata, full nominal/stress
snapshots, original compressed source objects and receipts, frozen engine/adapter
code, configuration, software/data licences and attribution. OSM-derived walking
links are separately available under `walking/` with ODbL attribution; they also
occur in the full engine snapshots. Supplementary monthly proxy evidence is separate
from the primary inputs. The pack is ignored by Git and has not been published.

Run from the repository root, substituting the externally reviewed manifest digest:

```text
python scripts/reproduce.py data/derived/reproduction-int003-reviewed --expected-manifest-sha256 <reviewed-sha256> --runs <run-id> ...
```

The verifier checks the exact pack file set, all listed bytes and exact engine/adapter identities, then
compares primary metrics, plan/comparison objectives, selected candidates, duties
and rejection facts exactly. Timing, progress and store diagnostics are excluded.
A supplied wrong manifest digest fails. Without an expected digest, the check only
establishes internal consistency; it does not authenticate an untrusted pack.

Four final stop-closure budget runs were independently recomputed. The task handoff
records their exact IDs, externally reviewed manifest hash and local report path.
The prepared manifest identity is
`67160494c4307f5cae928e4ed52268beffd990a4779b90035461f78bdf3cdf92`.
This anchors 65 files (138632495 content bytes); the pack remains private.
Changing a snapshot, derived input, source receipt/object, immutable input or final
result is rejected. Historical runs are never relabelled with current code hashes.
Private previews may show explicitly legacy or unavailable-code runs; public exports
require complete versioned artifacts and matching code.
Bundle export and the live run index enumerate immutable final results first and
reject any conflicting progress file before eligibility filtering. A completed
final remains available when its mutable progress file is absent; removing metadata
from a progress file cannot relabel the final as legacy.

To prepare another reviewed private packet:

```text
python scripts/prepare_release.py --bundle data/derived/private-preview --pack data/derived/private-pack --runs <explicit-reviewed-run-ids>
```

Use a fresh pack directory. Raw source redistribution still requires the reviewed
source conditions and publisher approval; producing this private pack does not
satisfy collection, licence or publication gates.
