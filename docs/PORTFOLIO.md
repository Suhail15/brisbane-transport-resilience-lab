# Portfolio and résumé wording

Use these claims with the recorded release and linked evidence. This is an independent portfolio project, not employment with Translink or an operational deployment for a transport operator.

## Short project entry

**Brisbane Transport Resilience Lab — Python, FastAPI, PostgreSQL/PostGIS, Redpanda, React, Docker, GitHub Actions**

- Built a transport replay and disruption-analysis platform using real bus–rail schedules and recorded realtime feeds, with immutable source archives and receipt-time cutoffs to prevent hindsight leakage.
- Implemented timetable routing and a resource-constrained recovery search; evaluated 54 reproducible scenarios across three recorded mornings, retaining null findings and validating sensitivity to bus running-time assumptions.
- Published a browser demo and offline reproduction pack; independently reconciled all 54 cases and measured a worst-date journey API p95 of 0.173 seconds across 300 HTTP queries on the documented pilot hardware.

## Emphasis by role

| Role | Evidence to discuss |
|---|---|
| Data engineering | Replayable raw archive, source hashes and schema checks, Kafka-compatible event delivery, indexed spatial storage, versioned analytical extracts, cross-platform CI. |
| Software engineering | Inspectable routing, asynchronous calculations, cancellation and progress, API contracts, immutable results, independent route and optimizer checks. |
| Analytics / consulting | Fixed comparisons, explicit denominators and budgets, no-action baseline, sensitivity tests and recommendations that change when the assumptions change. |

## What the findings do and do not support

The nominal stop-closure model reduces aggregate capped duration by 584/782/782 seconds across 100 equally weighted queries using a hypothetical two-hour bus duty. It restores no previously lost sixty-minute journey, and the running-time stress cases select no additional bus. Describe that limited and assumption-sensitive result honestly. Do not convert it into passenger savings, revenue, a production SLA, official endorsement or proof of available vehicles.

The independent OpenTripPlanner comparison explains source-specific access differences; it does not establish identical walking models or measured-arrival accuracy. Mac/Linux/Windows CI is separate from an unverified Windows collector installation. Detailed evidence: [findings](FINDINGS.md), [verification](VERIFICATION.md), [release](RELEASE.md).
