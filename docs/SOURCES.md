# Source register and publication review

Reviewed 2026-10-02. Source receipts preserve exact retrieval times and SHA256 locally.

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
it allows three full business days for processing. No contact or approval has been
sent/received by this task. This is an explicit release blocker for public network
material. Branding must remain independent; attribution is not endorsement. Source
availability and a CC licence alone do not mark the project licence gate complete.

Public release must document Translink contact/approval handling, OSM derivative data
licensing, and the exact compact bundle contents. Raw archives are local and ignored.
Licence release gate remains false in configs/release-evidence.json.
