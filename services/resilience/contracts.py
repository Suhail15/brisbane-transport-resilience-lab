"""Version 1 interchange contracts for recorded Brisbane transport analysis.

All timetable times are integer seconds since the Brisbane service-day midnight.
The engine deliberately has no network or database dependency.
"""

from __future__ import annotations

from datetime import date, datetime, time
from math import ceil
from typing import Annotated, Literal, Union
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonNegativeSeconds = Annotated[int, Field(ge=0)]
Identifier = Annotated[str, Field(min_length=1)]
TransportMode = Literal["bus", "rail"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRecord(Contract):
    record_id: Identifier
    source_kind: Literal["gtfs", "gtfs_rt", "osm"]
    received_at: datetime
    event_at: datetime | None = None
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    source_ref: Identifier

    @model_validator(mode="after")
    def require_aware_times(self) -> SourceRecord:
        for value in (self.received_at, self.event_at):
            if value is not None and value.utcoffset() is None:
                raise ValueError("source timestamps must include a timezone")
        return self


class QualityMetadata(Contract):
    realtime_status: Literal["fresh", "stale", "missing", "degraded", "unknown"] = "unknown"
    schedule_status: Literal["verified", "unverified", "missing"] = "unverified"
    walking_status: Literal["verified_osm", "incomplete", "missing"] = "missing"
    realtime_age_seconds: NonNegativeSeconds | None = None
    source_event_age_seconds: int | None = None
    warnings: tuple[str, ...] = ()
    # These are collection facts; neither flag can be inferred from a download.
    complete_morning_collection: bool = False
    observed_passenger_demand: bool = False


class SnapshotMetadata(Contract):
    snapshot_id: Identifier
    snapshot_at: datetime
    service_date: date
    timezone: Literal["Australia/Brisbane"] = "Australia/Brisbane"
    sources: tuple[SourceRecord, ...]
    quality: QualityMetadata = Field(default_factory=QualityMetadata)

    @model_validator(mode="after")
    def enforce_as_of_boundary(self) -> SnapshotMetadata:
        if self.snapshot_at.utcoffset() is None:
            raise ValueError("snapshot_at must include a timezone")
        if any(source.received_at > self.snapshot_at for source in self.sources):
            raise ValueError("a snapshot cannot use a record received after snapshot_at")
        if self.snapshot_s < 0:
            raise ValueError("snapshot_at precedes its service-day midnight")
        if len({source.record_id for source in self.sources}) != len(self.sources):
            raise ValueError("duplicate source record ids")
        return self

    @property
    def snapshot_s(self) -> int:
        midnight = datetime.combine(self.service_date, time(), ZoneInfo(self.timezone))
        return int((self.snapshot_at - midnight).total_seconds())


class Stop(Contract):
    stop_id: Identifier
    name: str = ""
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class Connection(Contract):
    connection_id: Identifier
    trip_instance_id: Identifier
    route_id: Identifier
    mode: TransportMode
    sequence: Annotated[int, Field(ge=0)]
    from_stop_id: Identifier
    to_stop_id: Identifier
    departure_s: NonNegativeSeconds
    arrival_s: NonNegativeSeconds
    pickup_allowed: bool = True
    drop_off_allowed: bool = True
    provenance: Literal["scheduled", "realtime", "hypothetical_relief"] = "scheduled"

    @model_validator(mode="after")
    def chronological(self) -> Connection:
        if self.arrival_s < self.departure_s:
            raise ValueError("connection arrives before it departs")
        return self


class WalkingLink(Contract):
    link_id: Identifier
    from_stop_id: Identifier
    to_stop_id: Identifier
    length_m: Annotated[float, Field(gt=0, le=600)]
    duration_s: Annotated[int, Field(gt=0)]
    osm_node_ids: Annotated[tuple[int, ...], Field(min_length=2)]
    from_snap_distance_m: Annotated[float, Field(ge=0, le=30)] = 0
    to_snap_distance_m: Annotated[float, Field(ge=0, le=30)] = 0
    # GeoJSON order: longitude, latitude. Geometry must come from this OSM path.
    geometry: Annotated[tuple[tuple[float, float], ...], Field(min_length=2)]

    @model_validator(mode="after")
    def fixed_walking_speed(self) -> WalkingLink:
        if self.from_stop_id == self.to_stop_id:
            raise ValueError("walking links must connect different stops")
        if self.duration_s != ceil(self.length_m / 1.2):
            raise ValueError("walking duration must be ceil(length_m / 1.2)")
        return self


class PatternStop(Contract):
    stop_id: Identifier
    arrival_offset_s: NonNegativeSeconds
    departure_offset_s: NonNegativeSeconds
    pickup_allowed: bool = True
    drop_off_allowed: bool = True

    @model_validator(mode="after")
    def dwell_is_nonnegative(self) -> PatternStop:
        if self.departure_offset_s < self.arrival_offset_s:
            raise ValueError("pattern departure precedes arrival")
        return self


class BusPattern(Contract):
    pattern_id: Identifier
    route_id: Identifier
    direction_id: Identifier
    source_trip_instance_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    stops: Annotated[tuple[PatternStop, ...], Field(min_length=2)]

    @model_validator(mode="after")
    def chronological(self) -> BusPattern:
        if self.stops[0].departure_offset_s != 0:
            raise ValueError("pattern first departure offset must be zero")
        for previous, current in zip(self.stops, self.stops[1:]):
            if current.arrival_offset_s < previous.departure_offset_s:
                raise ValueError("pattern times are not chronological")
        if self.stops[-1].arrival_offset_s <= 0:
            raise ValueError("a bus pattern must have positive running time")
        return self


class PatternPair(Contract):
    pair_id: Identifier
    outbound: BusPattern
    inbound: BusPattern

    @model_validator(mode="after")
    def complete_round_trip(self) -> PatternPair:
        if (self.outbound.stops[-1].stop_id != self.inbound.stops[0].stop_id
                or self.inbound.stops[-1].stop_id != self.outbound.stops[0].stop_id):
            raise ValueError("paired patterns must meet at both terminals")
        return self


class TimetableSnapshot(Contract):
    metadata: SnapshotMetadata
    stops: tuple[Stop, ...]
    connections: tuple[Connection, ...]
    walking_links: tuple[WalkingLink, ...] = ()
    recovery_pairs: tuple[PatternPair, ...] = ()

    @model_validator(mode="after")
    def referential_integrity(self) -> TimetableSnapshot:
        stops = {stop.stop_id for stop in self.stops}
        if len(stops) != len(self.stops):
            raise ValueError("duplicate stop ids")
        for collection, key in ((self.connections, "connection_id"),
                                (self.walking_links, "link_id"),
                                (self.recovery_pairs, "pair_id")):
            if len({getattr(item, key) for item in collection}) != len(collection):
                raise ValueError(f"duplicate {key} values")
        trips: dict[str, list[Connection]] = {}
        for connection in self.connections:
            if connection.from_stop_id not in stops or connection.to_stop_id not in stops:
                raise ValueError("a connection references an unknown stop")
            trips.setdefault(connection.trip_instance_id, []).append(connection)
        for trip in trips.values():
            ordered = sorted(trip, key=lambda item: item.sequence)
            if [item.sequence for item in ordered] != list(range(len(ordered))):
                raise ValueError("full trips require contiguous connection sequences starting at zero")
            for previous, current in zip(ordered, ordered[1:]):
                if previous.to_stop_id != current.from_stop_id or previous.arrival_s > current.departure_s:
                    raise ValueError("trip connections are not contiguous and chronological")
        for link in self.walking_links:
            if link.from_stop_id not in stops or link.to_stop_id not in stops:
                raise ValueError("a walking link references an unknown stop")
        for pair in self.recovery_pairs:
            if any(item.stop_id not in stops for pattern in (pair.outbound, pair.inbound)
                   for item in pattern.stops):
                raise ValueError("a recovery pattern references an unknown stop")
        return self


class JourneyRequest(Contract):
    request_id: Identifier
    origin_stop_id: Identifier
    destination_stop_id: Identifier
    departure_s: NonNegativeSeconds
    # Optional supplied research weight. Primary metrics always use equal weights.
    od_weight: Annotated[float, Field(gt=0)] | None = None


class ScenarioBase(Contract):
    scenario_id: Identifier
    start_s: NonNegativeSeconds
    end_s: NonNegativeSeconds

    @model_validator(mode="after")
    def nonempty_window(self) -> ScenarioBase:
        if self.end_s <= self.start_s:
            raise ValueError("scenario interval must be nonempty")
        return self


class TripCancellation(ScenarioBase):
    kind: Literal["trip_cancellation"] = "trip_cancellation"
    trip_instance_ids: Annotated[tuple[str, ...], Field(min_length=1)]


class StopUnavailable(ScenarioBase):
    kind: Literal["stop_unavailable"] = "stop_unavailable"
    stop_ids: Annotated[tuple[str, ...], Field(min_length=1)]


class CorridorSegment(Contract):
    from_stop_id: Identifier
    to_stop_id: Identifier
    bidirectional: bool = True


class CorridorClosure(ScenarioBase):
    kind: Literal["corridor_closure"] = "corridor_closure"
    segments: Annotated[tuple[CorridorSegment, ...], Field(min_length=1)]


class AdditionalDelay(ScenarioBase):
    kind: Literal["additional_delay"] = "additional_delay"
    trip_instance_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    additional_seconds: Annotated[int, Field(gt=0)]


Scenario = Annotated[Union[TripCancellation, StopUnavailable, CorridorClosure,
                           AdditionalDelay], Field(discriminator="kind")]


class TransitLeg(Contract):
    kind: Literal["transit"] = "transit"
    mode: TransportMode
    trip_instance_id: Identifier
    route_id: Identifier
    from_stop_id: Identifier
    to_stop_id: Identifier
    departure_s: NonNegativeSeconds
    arrival_s: NonNegativeSeconds
    connection_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    provenance: Literal["scheduled", "realtime", "hypothetical_relief"]


class WalkingLeg(Contract):
    kind: Literal["walk"] = "walk"
    from_stop_id: Identifier
    to_stop_id: Identifier
    departure_s: NonNegativeSeconds
    arrival_s: NonNegativeSeconds
    link_id: Identifier
    length_m: float
    osm_node_ids: tuple[int, ...]
    geometry: tuple[tuple[float, float], ...]


JourneyLeg = Annotated[Union[TransitLeg, WalkingLeg], Field(discriminator="kind")]


class RouteResult(Contract):
    request: JourneyRequest
    reachable: bool
    arrival_s: NonNegativeSeconds | None = None
    duration_s: NonNegativeSeconds | None = None
    boardings: Annotated[int, Field(ge=0, le=4)] = 0
    transfers: Annotated[int, Field(ge=0, le=3)] = 0
    legs: tuple[JourneyLeg, ...] = ()
    quality: QualityMetadata


class ScenarioImpact(Contract):
    cancelled_trip_instance_ids: tuple[str, ...] = ()
    delayed_trip_instance_ids: tuple[str, ...] = ()
    unavailable_stop_ids: tuple[str, ...] = ()


class ScenarioApplication(Contract):
    snapshot: TimetableSnapshot
    impact: ScenarioImpact


class MissedConnection(Contract):
    request_id: Identifier
    from_trip_instance_id: Identifier
    to_trip_instance_id: Identifier
    alight_stop_id: Identifier
    board_stop_id: Identifier
    earliest_boarding_s: NonNegativeSeconds
    departure_s: NonNegativeSeconds


class EvaluationMetrics(Contract):
    request_count: NonNegativeSeconds
    reachability_horizon_s: int = 3600
    duration_cap_s: int = 5400
    baseline_reachable_count: NonNegativeSeconds
    disrupted_reachable_count: NonNegativeSeconds
    recovered_reachable_count: NonNegativeSeconds
    lost_count: NonNegativeSeconds
    restored_count: NonNegativeSeconds
    restored_fraction: Annotated[float, Field(ge=0, le=1)] | None
    baseline_total_capped_duration_s: NonNegativeSeconds
    disrupted_total_capped_duration_s: NonNegativeSeconds
    recovered_total_capped_duration_s: NonNegativeSeconds
    requests_with_missed_connections: NonNegativeSeconds
    missed_connection_count: NonNegativeSeconds


class ScenarioEvaluation(Contract):
    baseline: tuple[RouteResult, ...]
    disrupted: tuple[RouteResult, ...]
    recovered: tuple[RouteResult, ...]
    metrics: EvaluationMetrics
    missed_connections: tuple[MissedConnection, ...] = ()
    impact: ScenarioImpact


class CandidateIssue(Contract):
    candidate_id: Identifier
    reason: Identifier


class RecoveryCandidate(Contract):
    candidate_id: Identifier
    pair_id: Identifier
    activation_s: NonNegativeSeconds
    # Every candidate is exactly one bus committed for two hours.
    duty_duration_s: Literal[7200] = 7200
    bus_hours: Literal[2] = 2


class RecoveryDuty(Contract):
    candidate: RecoveryCandidate
    cycle_count: Annotated[int, Field(gt=0)]
    duty_end_s: NonNegativeSeconds
    connection_ids: tuple[str, ...]
    trip_instance_ids: tuple[str, ...]


class RecoveryObjective(Contract):
    restored_count: NonNegativeSeconds
    total_capped_duration_s: NonNegativeSeconds
    bus_hours: Annotated[int, Field(ge=0, le=8)]


class RecoveryProgress(Contract):
    stage: Literal["preparing", "greedy", "swaps", "exhaustive", "completed"]
    evaluated_plan_count: NonNegativeSeconds
    considered_candidate_count: Annotated[int, Field(ge=0, le=12)]
    feasible_candidate_count: Annotated[int, Field(ge=0, le=12)]
    evaluation_upper_bound: NonNegativeSeconds | None = None


class RecoveryPlan(Contract):
    candidate_ids: tuple[str, ...]
    duties: tuple[RecoveryDuty, ...]
    bus_count: Annotated[int, Field(ge=0, le=4)]
    bus_hours: Annotated[int, Field(ge=0, le=8)]
    objective: RecoveryObjective
    evaluation: ScenarioEvaluation


class RecoveryResult(Contract):
    budget_bus_hours: Literal[0, 2, 4, 8]
    plan: RecoveryPlan
    no_intervention: RecoveryObjective
    busiest_affected_pattern: RecoveryObjective | None
    evaluated_plan_count: Annotated[int, Field(gt=0)]
    considered_candidate_ids: tuple[str, ...] = ()
    infeasible_candidate_ids: tuple[str, ...] = ()
    infeasible_candidates: tuple[CandidateIssue, ...] = ()
    method: Literal["greedy_bounded_swap", "exhaustive"]
    optimality_proven: bool = False
    hypothetical: Literal[True] = True
    tie_break: str = "restore most, then minimize capped duration, then bus-hours, then sorted candidate ids"


class AnalysisAssumptions(Contract):
    bus_running_time_sensitivity_seconds: Literal[0, 300, 600] = 0
    max_walk_m: Literal[600] = 600
    walking_speed_m_s: Literal[1.2] = 1.2
    max_stop_snap_m: Literal[30] = 30
    walking_length_basis: Literal["actual_osm_edges"] = "actual_osm_edges"
    transfer_slack_s: Literal[300] = 300
    max_boardings: Literal[4] = 4
    max_requests: Literal[500] = 500
    primary_request_weight: Literal[1] = 1
    reachability_horizon_s: Literal[3600] = 3600
    duration_cap_s: Literal[5400] = 5400
    activation_lead_s: Literal[600] = 600
    bus_duty_s: Literal[7200] = 7200
    terminal_turn_s: Literal[300] = 300
    bus_hours_per_duty: Literal[2] = 2
    max_candidates: Literal[12] = 12
    max_buses: Literal[4] = 4
    trip_updates_cadence_s: Literal[30] = 30
    vehicle_positions_cadence_s: Literal[30] = 30
    alerts_cadence_s: Literal[60] = 60
    recording_window: Literal["weekdays 06:00-12:00 Australia/Brisbane"] = "weekdays 06:00-12:00 Australia/Brisbane"
    fleet_availability: Literal["hypothetical_unverified"] = "hypothetical_unverified"
    passenger_demand: Literal["unknown_equal_request_weights"] = "unknown_equal_request_weights"


class RunMetadata(Contract):
    schema_version: Literal[1] = 1
    input_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    engine_version: Identifier
    engine_code_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    journey_set_version: Identifier
    request_set_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    scenario_set_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    candidate_set_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    budget_bus_hours: Literal[0, 2, 4, 8]
    snapshot_id: Identifier
    snapshot_at: datetime
    snapshot_content_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    source_gtfs_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    source_osm_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None
    source_record_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    candidate_selection_version: Literal["affected-corridor-topology-v1"] = "affected-corridor-topology-v1"
    objective_version: Identifier
    search_method: Literal["greedy_bounded_swap", "exhaustive"] = "greedy_bounded_swap"
    max_swap_evaluations: Annotated[int, Field(ge=0, le=4096)] = 128
    assumptions: AnalysisAssumptions = Field(default_factory=AnalysisAssumptions)

    @model_validator(mode="after")
    def aware_snapshot(self) -> RunMetadata:
        if self.snapshot_at.utcoffset() is None:
            raise ValueError("run snapshot_at must include a timezone")
        if len(set(self.source_record_ids)) != len(self.source_record_ids):
            raise ValueError("run source record ids must be unique")
        return self
