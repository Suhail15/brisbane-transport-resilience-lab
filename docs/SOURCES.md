# Source register and publication review

Reviewed 2026-10-02; public-use terms rechecked 2026-10-22. Source receipts preserve exact retrieval times and SHA256 locally.

| Source | Publisher | Source and terms | Licence / coverage |
|---|---|---|---|
| SEQ GTFS | Queensland Department of Transport and Main Roads / Translink | [Schedule ZIP](https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip), [open data](https://translink.com.au/about-translink/open-data) | CC BY 4.0; acquired feed states 2026-10-01–2026-11-30 |
| TripUpdates / VehiclePositions / Alerts | Translink | [Open data feed links](https://translink.com.au/about-translink/open-data) | CC BY 4.0; unauthenticated live feeds, receipt-bounded archive |
| Monthly OD July 2026 | Translink | [Dataset](https://www.data.qld.gov.au/dataset/translink-origin-destination-trips-2022-onwards) | CC BY 4.0 dataset metadata; source Readme caveats in DATA_AUDIT |
| Pilot OSM ways/nodes | OpenStreetMap contributors, via Overpass | [Copyright/licence](https://www.openstreetmap.org/copyright), [ODbL](https://opendatacommons.org/licenses/odbl/1-0/) | ODbL 1.0; extract acquired 2026-10-02, not historic OSM |
| OTP independent reference | OpenTripPlanner | [Basic tutorial](https://docs.opentripplanner.org/en/latest/Basic-Tutorial/), [GraphQL](https://docs.opentripplanner.org/en/latest/apis/GTFS-GraphQL-API/) | OTP 2.10.0 official Java25 shaded JAR; not project engine |

Source data and source-derived geometry are distinct from the project's source code
licence. Preserve attribution for Translink/TMR, CC BY 4.0 links and changes made.
Display `© OpenStreetMap contributors` linked to its copyright page on map views;
OSM-derived database exports need ODbL notice and derivative-data distribution review.
No basemap tile service is assumed or downloaded as part of this pipeline.

[Translink open data terms](https://translink.com.au/about-translink/open-data/terms-and-conditions)
require contact details be supplied/current. Their public-material provision addresses
network/logo/images and requests intended use be submitted to marketing@translink.com.au;
it allows three full business days for processing. On 2026-10-02, the user authorized
a request in their own name. It was sent to marketing@translink.com.au and verified
in the user's Sent mailbox, with current contact details supplied. On 2026-10-22 the
user supplied the written Translink reply in this project chat. It covers source code
and compact static/realtime GTFS recordings for noncommercial research, academic and
portfolio use, subject to attribution, independent branding and explicit simulation
labels. This is user-provided correspondence; original sender headers and the email
timestamp were not independently inspected. The private supplied text and its hash
remain outside public Git history. It does not imply Translink endorsement or cover
another publisher's data. The release licence review must still verify the actual
packaged contents and OSM obligations.

Required notice, retained in the README and app:

> Contains public transport data provided by Translink (Department of Transport and Main Roads, Queensland) under CC BY 4.0. Translink does not endorse and is not affiliated with this independent project or its simulation outcomes.

The compact data is a selected, normalized and sampled derivative of the archived
GTFS feeds. Disruption overlays, additional buses and running-time stresses are this
project's hypothetical changes. Source vehicle positions and provider predictions
retain their own timestamps; neither proves an observed passenger arrival.

Public release must document Translink contact/approval handling, OSM derivative data
licensing, and the exact compact bundle contents. Raw archives are local and ignored.
The committed configs/release-evidence.json remains an empty future-candidate template; actual accepted v1.0.0 evidence is distributed with the release. The sent request
and private contact details are recorded under ignored data/runtime/ rather than in
the public source repository.

On 2026-10-03, the published open-data and separate terms pages were rechecked.
Online licence information does not constitute an individual approval reply. The
request remains pending; no approval record or release gate was changed. Exact
retrieved terms and review hashes are retained privately under `data/runtime/`.

On 2026-10-22, the official Translink terms, CC BY 4.0 deed and OSM copyright page
were rechecked alongside the user-provided reply. Publisher handling is now supported
by that correspondence rather than inferred from a public licence page. OSM-derived
walking exports are separately offered under ODbL 1.0 with their source/derivation
records. All remaining evidence gates continue to apply before publication.

Release v1.0.0 was published on 22 October 2026 after all scoped source and artifact checks passed. The [public demo](https://suhail15.github.io/brisbane-transport-resilience-lab/) and [release evidence](https://github.com/Suhail15/brisbane-transport-resilience-lab/releases/tag/v1.0.0) retain attribution and simulation labels; the selected source reproduction pack and separate ODbL walking derivative are downloadable. Private correspondence and contact details remain outside the public repository and assets.
