# Data attribution and licences

The MIT code licence does not relicense transport data, OpenStreetMap data or
third-party map tiles. Keep these notices with any distributed replay bundle.

## Transport data

Source: Queensland Department of Transport and Main Roads / Translink.

Schedules, trip updates, vehicle positions and alerts come from the
[Translink open-data feeds](https://translink.com.au/about-translink/open-data).
Monthly origin–destination counts come from the
[Queensland open-data dataset](https://www.data.qld.gov.au/dataset/translink-origin-destination-trips-2022-onwards).
Source metadata identifies [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).

Project changes include pilot selection, conversion to timetable connections,
receipt-bounded replay, data-quality classification, and separately labelled
hypothetical disruptions and extra-bus services. None of these is an official
transport forecast or evidence of achieved passenger outcomes.

Translink's additional publication conditions and contact/approval status are
recorded in [the source register](docs/SOURCES.md). Public release remains gated
until that review is resolved.

## Walking network and basemap

© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).
The OSM-derived walking-network database is available under the
[Open Database Licence 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Its changes include pedestrian-way filtering, a bounded geographic extract,
stop-to-path mapping and derived path distances and durations.

Retain its attribution and database licence when distributing the walking
component. Keep it distinguishable from the transport-data component. Source
receipts and bundle manifests identify their respective inputs and versions.
The local archive and derived OSM extract are outside Git history; any public
release must provide the associated derivative-data distribution information.

The browser map uses OpenStreetMap tiles for interactive display, with visible
attribution. Tiles are a separate service; the application does not bulk-download
or prefetch them for offline use.

## Independent project

This project uses its own name and visual identity. It is not operated or
endorsed by Translink, Queensland Government or OpenStreetMap contributors.
