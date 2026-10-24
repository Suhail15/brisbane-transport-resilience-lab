# Reproduce the recorded experiments

The first release contains 54 completed cases from 19–21 October 2026. They use the same fixed journey set, 07:30:05 Brisbane decision cutoff and frozen scenario selection rules. See [the protocol](MORNING_EVALUATION.md) and [findings](FINDINGS.md) before interpreting the numbers.

## Download and check

Use the repository revision named in the release attestation, the locked Python environment, and the `morning-reproduction.zip` asset from the [release](https://github.com/Suhail15/brisbane-transport-resilience-lab/releases/tag/v1.0.0). The release's `SHA256SUMS.txt` records the ZIP and extracted manifest identities. Verify the downloaded bytes, extract into a new directory and run from the repository root:

```text
python scripts/reproduce.py <extracted-pack-directory> --expected-manifest-sha256 <manifest-sha256-from-release>
```

An optional `--runs <run-id> ...` selects a subset. Omitting it recomputes all 54. No upstream requests, running database or collector are needed for this command. Use [SETUP.md](SETUP.md) for the environment; Python dependencies are pinned in `requirements.lock.txt`.

The verifier checks the exact file set, hashes, engine and adapter identities. It recomputes metrics, no-action and simple-policy objectives, selected services, vehicle duties and rejections. Those facts must match exactly. Timing, progress and store diagnostics are excluded. A wrong external manifest digest fails. Without that external digest, a manifest establishes internal consistency only.

## What is included

The pack contains immutable requests and results, nominal and stress-derived normalized snapshots, selected compressed source objects and receipt records, matching engine code, configuration and licences. It contains only the selected source inputs, not the full collection archive. OSM-derived walking data is available separately under `walking/` with ODbL attribution; full engine snapshots also contain those walking links. Translink data attribution and modifications are described in `code/DATA_LICENSE.md`.

Before publication, all 54 cases were recomputed offline and matched in 508.35 seconds on the documented Mac environment. This is a reproducibility check, not an independent proof of routing optimality. A separate independent checker recalculates the saved journey metrics; source-specific OpenTripPlanner comparisons are documented in [reference validation](REFERENCE_VALIDATION.md).

## Preparing a new release

Keep archives and generated packs outside Git. `scripts/prepare_mornings.py`, `scripts/run_mornings.py`, `scripts/verify_morning_results.py` and `scripts/summarize_mornings.py` implement the frozen protocol. Public preparation requires the complete recording windows, exactly three eligible morning dates and reviewed source permissions. Candidate preparation is not publication authorization. All release gates must pass before any upload.

The older afternoon development packet remains local and separate from this release. It is not relabelled as morning or final evaluation evidence.

## Separate rail-closure study

The additive study uses [corridor-impact.v2.json](../configs/corridor-impact.v2.json)
and the source-expanded [station-access network](../configs/station-access-network.v1.json).
It has 240 equal-weight primary requests and 100 separately scored controls,
four nominal budgets and two additional stress cases per date. October 22 is
the separate confirmation date; October 19–21 are explicitly reused replication
dates. The original release and its reproduction asset remain available.

An exact study pack contains normalized snapshots, full saved route arrays,
source identities, the matching calculation code and pinned dependencies. It
does not require the full raw archive, a database, a broker or upstream requests.
From the extracted pack directory, using its locked Python environment:

```text
python code/scripts/run_case_study.py reproduce --destination . --expected-manifest-sha256 <externally-published-manifest-sha256>
```

This recomputes every packed cell, including selected duties and all primary
and control route arrays. The comparison excludes elapsed time. A full run can
take substantially longer than an individual journey query. Source topology,
metric reconciliation and exact recomputation are different checks; none alone
establishes observed passenger benefit or a globally optimal recovery plan.

With eligible local source archives, `scripts/run_case_study.py prepare` freezes
isolated study inputs. `run --dates ...` defaults to development execution;
`--allow-registered` is reserved for the reviewed, frozen confirmation and
replication matrix. `report` exports completed summaries and `pack` creates a
new immutable reproduction directory. The historical `refreeze` helper supports
the v1 study only; a v2 correction needs a new reviewed preparation that includes
its network artifacts. Do not edit frozen inputs or reuse a past approval.

`scripts/prepare_case_study_bundle.py` adds reviewed results to a fresh copy of
the original compact demo. It requires protocol-matched complete 24-cell
independent and reproduction evidence, verifies the checked cell bytes, retains
the original result/replay files, and exports separate per-query CSV and ODbL
walking databases. This command prepares an artifact; publication still requires
the candidate-specific checks described in [RELEASE.md](RELEASE.md).
