"""Data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime, time
from typing import Any, Mapping

from school_finder.models.preferences import PreferenceMetric
from school_finder.models.scoring import ScoreComponent, SchoolScore


@dataclass(frozen=True, slots=True)
class SchoolIdentity:
    urn: str
    name: str
    sector: str | None = None
    establishment_type: str | None = None
    phase: str | None = None
    age_range: str | None = None
    gender: str | None = None
    religious_character: str | None = None
    religious_ethos: str | None = None
    faith_status: str | None = None
    website: str | None = None
    telephone: str | None = None


@dataclass(frozen=True, slots=True)
class SchoolLocation:
    address: str | None = None
    town: str | None = None
    postcode: str | None = None
    local_authority_code: str | None = None
    local_authority_name: str | None = None
    easting: int | None = None
    northing: int | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True, slots=True)
class AcademicPerformance:
    data_year: str | None = None
    progress8: float | None = None
    progress8_year: str | None = None
    progress8_source_urn: str | None = None
    progress8_source_school_name: str | None = None
    progress8_source_kind: str | None = None
    progress8_source_link_depth: int | None = None
    english_maths_grade5_pct: float | None = None
    english_maths_grade4_pct: float | None = None
    attainment8: float | None = None
    attainment8_english: float | None = None
    attainment8_maths: float | None = None
    attainment8_other: float | None = None
    ebacc_entry_pct: float | None = None
    ebacc_aps: float | None = None


@dataclass(frozen=True, slots=True)
class InspectionSummary:
    rating: str | None = None
    equivalent_rating: str | None = None
    equivalent_basis: str | None = None
    equivalent_explanation: str | None = None
    source_urn: str | None = None
    source_school_name: str | None = None
    source_kind: str | None = None
    source_link_depth: int | None = None
    inspection_date: date | None = None
    publication_date: date | None = None
    safeguarding: str | None = None
    inclusion: str | None = None
    curriculum_teaching: str | None = None
    achievement: str | None = None
    attendance_behaviour: str | None = None
    personal_development: str | None = None
    leadership: str | None = None
    adjusted_score: float | None = None

    @property
    def inspection_year(self) -> int | None:
        return self.inspection_date.year if self.inspection_date else None


@dataclass(frozen=True, slots=True)
class AttendanceStatistics:
    enrolments: int | None = None
    overall_absence_pct: float | None = None
    authorised_absence_pct: float | None = None
    unauthorised_absence_pct: float | None = None
    persistent_absence_pct: float | None = None
    severe_absence_pct: float | None = None
    data_year: str | None = None
    source: str | None = None
    source_dataset_id: str | None = None
    source_urn: str | None = None
    source_school_name: str | None = None
    source_kind: str | None = None
    source_link_depth: int | None = None


@dataclass(frozen=True, slots=True)
class BehaviourStatistics:
    pupil_headcount: int | None = None
    suspension_count: int | None = None
    suspension_rate: float | None = None
    pupils_with_one_or_more_suspension: int | None = None
    pupils_with_one_or_more_suspension_rate: float | None = None
    permanent_exclusion_count: int | None = None
    permanent_exclusion_rate: float | None = None
    data_year: str | None = None
    source: str | None = None
    source_dataset_id: str | None = None
    source_urn: str | None = None
    source_school_name: str | None = None
    source_kind: str | None = None
    source_link_depth: int | None = None


@dataclass(frozen=True, slots=True)
class WorkforceStatistics:
    pupil_fte: float | None = None
    teacher_fte: float | None = None
    qualified_teacher_fte: float | None = None
    classroom_teacher_fte: float | None = None
    teaching_assistant_fte: float | None = None
    support_staff_fte: float | None = None
    teachers_without_qts_fte: float | None = None
    part_time_teacher_pct: float | None = None
    pupil_qualified_teacher_ratio: float | None = None
    pupil_teacher_ratio: float | None = None
    pupil_adult_ratio: float | None = None
    data_year: str | None = None
    ratio_year: str | None = None
    source: str | None = None
    source_dataset_id: str | None = None
    ratio_source: str | None = None
    ratio_source_dataset_id: str | None = None
    source_urn: str | None = None
    source_school_name: str | None = None
    source_kind: str | None = None
    source_link_depth: int | None = None

    @property
    def pupils_per_classroom_teacher(self) -> float | None:
        if not self.pupil_fte or not self.classroom_teacher_fte:
            return None
        return self.pupil_fte / self.classroom_teacher_fte

    @property
    def pupils_per_classroom_and_support_staff(self) -> float | None:
        if not self.pupil_fte:
            return None
        classroom = self.classroom_teacher_fte or 0
        support = self.teaching_assistant_fte or 0
        denominator = classroom + support
        if denominator <= 0:
            return None
        return self.pupil_fte / denominator


@dataclass(frozen=True, slots=True)
class AdmissionsInformation:
    policy: str | None = None
    selective: bool | None = None
    published_admission_number: int | None = None
    catchment_description: str | None = None
    last_offer_distance_miles: float | None = None
    last_offer_year: str | None = None
    likelihood: str | None = None


@dataclass(frozen=True, slots=True)
class SchoolDayPeriod:
    """One repeated school-day pattern, for example Mon-Thu 08:30-15:30."""

    days: tuple[str, ...]
    starts_at: time
    ends_at: time


@dataclass(frozen=True, slots=True)
class SchoolDaySchedule:
    periods: tuple[SchoolDayPeriod, ...] = ()
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class TravelInformation:
    distance_miles: float | None = None
    walking_minutes: int | None = None
    public_transport_minutes: int | None = None
    annual_transport_cost_gbp: float | None = None
    school_day: SchoolDaySchedule | None = None
    leave_home_time: time | None = None
    home_arrival_time: time | None = None
    total_day_minutes: int | None = None

    @property
    def public_transport_time_saved_minutes(self) -> int | None:
        if self.walking_minutes is None or self.public_transport_minutes is None:
            return None
        return self.walking_minutes - self.public_transport_minutes


@dataclass(frozen=True, slots=True)
class UserAssessment:
    """Parent-specific information; never treated as public school data."""

    notes: str | None = None
    score: float | None = None


@dataclass(frozen=True, slots=True)
class SchoolResult:
    """The single school object consumed by the application layer."""

    identity: SchoolIdentity
    location: SchoolLocation = field(default_factory=SchoolLocation)
    academics: AcademicPerformance = field(default_factory=AcademicPerformance)
    inspection: InspectionSummary = field(default_factory=InspectionSummary)
    attendance: AttendanceStatistics = field(default_factory=AttendanceStatistics)
    behaviour: BehaviourStatistics = field(default_factory=BehaviourStatistics)
    workforce: WorkforceStatistics = field(default_factory=WorkforceStatistics)
    admissions: AdmissionsInformation = field(default_factory=AdmissionsInformation)
    travel: TravelInformation = field(default_factory=TravelInformation)
    preference_score: SchoolScore | None = None
    user_assessment: UserAssessment | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialise(self)


@dataclass(frozen=True, slots=True)
class SchoolBenchmarks:
    """Non-school comparison values, such as national or local averages."""

    label: str
    level: str | None = None
    code: str | None = None
    source: str | None = None
    source_dataset_id: str | None = None
    academics: AcademicPerformance = field(default_factory=AcademicPerformance)
    attendance: AttendanceStatistics = field(default_factory=AttendanceStatistics)
    behaviour: BehaviourStatistics = field(default_factory=BehaviourStatistics)
    workforce: WorkforceStatistics = field(default_factory=WorkforceStatistics)

    def to_dict(self) -> dict[str, Any]:
        return _serialise(self)


@dataclass(frozen=True, slots=True)
class SchoolResultSet:
    """A search response ready for filtering, comparison or presentation."""

    schools: tuple[SchoolResult, ...]
    benchmarks: tuple[SchoolBenchmarks, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _serialise(self)


def school_result_from_flat_record(record: Mapping[str, Any]) -> SchoolResult:
    """Translate a canonical flat school record into the application contract.

    This function intentionally understands only School Finder's canonical
    snake_case column names. Dataset-specific column names must be normalised by
    the appropriate source adapter before reaching this boundary.
    """

    inspection_date = _as_date(record.get("ofsted_inspection_date"))
    school_day_summary = _as_str(record.get("school_day_summary"))
    school_day = SchoolDaySchedule(summary=school_day_summary) if school_day_summary else None

    notes = _as_str(record.get("user_notes"))
    score = _as_float(record.get("user_score"))
    assessment = UserAssessment(notes=notes, score=score) if notes is not None or score is not None else None
    preference_score = _preference_score_from_record(record)

    return SchoolResult(
        identity=SchoolIdentity(
            urn=_as_str(record.get("urn")) or "",
            name=_as_str(record.get("school_name")) or "",
            sector=_as_str(record.get("sector")),
            establishment_type=_as_str(record.get("establishment_type")),
            phase=_as_str(record.get("phase")),
            age_range=_as_str(record.get("age_range")),
            gender=_as_str(record.get("gender")),
            religious_character=_as_str(record.get("religious_character")),
            religious_ethos=_as_str(record.get("religious_ethos")),
            faith_status=_as_str(record.get("faith_status")),
            website=_as_str(record.get("website")),
            telephone=_as_str(record.get("telephone")),
        ),
        location=SchoolLocation(
            address=_as_str(record.get("address")),
            town=_as_str(record.get("town")),
            postcode=_as_str(record.get("postcode")),
            local_authority_code=_as_str(record.get("local_authority_code")),
            local_authority_name=_as_str(record.get("local_authority_name")),
            easting=_as_int(record.get("easting")),
            northing=_as_int(record.get("northing")),
            latitude=_as_float(record.get("latitude")),
            longitude=_as_float(record.get("longitude")),
        ),
        academics=AcademicPerformance(
            data_year=_as_str(record.get("performance_year")),
            progress8=_as_float(record.get("progress8")),
            progress8_year=_as_str(record.get("progress8_year")),
            progress8_source_urn=_as_str(record.get("progress8_source_urn")),
            progress8_source_school_name=_as_str(
                record.get("progress8_source_school_name")
            ),
            progress8_source_kind=_as_str(record.get("progress8_source_kind")),
            progress8_source_link_depth=_as_int(
                record.get("progress8_source_link_depth")
            ),
            english_maths_grade5_pct=_as_float(record.get("english_maths_grade5_pct")),
            english_maths_grade4_pct=_as_float(record.get("english_maths_grade4_pct")),
            attainment8=_as_float(record.get("attainment8")),
            attainment8_english=_as_float(record.get("attainment8_english")),
            attainment8_maths=_as_float(record.get("attainment8_maths")),
            attainment8_other=_as_float(record.get("attainment8_other")),
            ebacc_entry_pct=_as_float(record.get("ebacc_entry_pct")),
            ebacc_aps=_as_float(record.get("ebacc_aps")),
        ),
        inspection=InspectionSummary(
            rating=_as_str(record.get("ofsted_rating")),
            equivalent_rating=_as_str(record.get("ofsted_equivalent_rating")),
            equivalent_basis=_as_str(record.get("ofsted_equivalent_basis")),
            equivalent_explanation=_as_str(record.get("ofsted_equivalent_explanation")),
            source_urn=_as_str(record.get("ofsted_source_urn")),
            source_school_name=_as_str(record.get("ofsted_source_school_name")),
            source_kind=_as_str(record.get("ofsted_source_kind")),
            source_link_depth=_as_int(record.get("ofsted_source_link_depth")),
            inspection_date=inspection_date,
            publication_date=_as_date(record.get("ofsted_publication_date")),
            safeguarding=_as_str(record.get("ofsted_safeguarding")),
            inclusion=_as_str(record.get("ofsted_inclusion")),
            curriculum_teaching=_as_str(record.get("ofsted_curriculum_teaching")),
            achievement=_as_str(record.get("ofsted_achievement")),
            attendance_behaviour=_as_str(record.get("ofsted_attendance_behaviour")),
            personal_development=_as_str(record.get("ofsted_personal_development")),
            leadership=_as_str(record.get("ofsted_leadership")),
            adjusted_score=_as_float(record.get("ofsted_adjusted_score")),
        ),
        attendance=AttendanceStatistics(
            enrolments=_as_int(record.get("attendance_enrolments")),
            overall_absence_pct=_as_float(record.get("overall_absence_pct")),
            authorised_absence_pct=_as_float(record.get("authorised_absence_pct")),
            unauthorised_absence_pct=_as_float(record.get("unauthorised_absence_pct")),
            persistent_absence_pct=_as_float(record.get("persistent_absence_pct")),
            severe_absence_pct=_as_float(record.get("severe_absence_pct")),
            data_year=_as_str(record.get("attendance_year")),
            source=_as_str(record.get("attendance_source")),
            source_dataset_id=_as_str(record.get("attendance_source_dataset_id")),
            source_urn=_as_str(record.get("attendance_source_urn")),
            source_school_name=_as_str(record.get("attendance_source_school_name")),
            source_kind=_as_str(record.get("attendance_source_kind")),
            source_link_depth=_as_int(record.get("attendance_source_link_depth")),
        ),
        behaviour=BehaviourStatistics(
            pupil_headcount=_as_int(record.get("behaviour_pupil_headcount")),
            suspension_count=_as_int(record.get("suspension_count")),
            suspension_rate=_as_float(record.get("suspension_rate")),
            pupils_with_one_or_more_suspension=_as_int(
                record.get("pupils_with_one_or_more_suspension")
            ),
            pupils_with_one_or_more_suspension_rate=_as_float(
                record.get("pupils_with_one_or_more_suspension_rate")
            ),
            permanent_exclusion_count=_as_int(record.get("permanent_exclusion_count")),
            permanent_exclusion_rate=_as_float(record.get("permanent_exclusion_rate")),
            data_year=_as_str(record.get("behaviour_year")),
            source=_as_str(record.get("behaviour_source")),
            source_dataset_id=_as_str(record.get("behaviour_source_dataset_id")),
            source_urn=_as_str(record.get("behaviour_source_urn")),
            source_school_name=_as_str(record.get("behaviour_source_school_name")),
            source_kind=_as_str(record.get("behaviour_source_kind")),
            source_link_depth=_as_int(record.get("behaviour_source_link_depth")),
        ),
        workforce=WorkforceStatistics(
            pupil_fte=_as_float(record.get("pupil_fte")),
            teacher_fte=_as_float(record.get("teacher_fte")),
            qualified_teacher_fte=_as_float(record.get("qualified_teacher_fte")),
            classroom_teacher_fte=_as_float(record.get("classroom_teacher_fte")),
            teaching_assistant_fte=_as_float(record.get("teaching_assistant_fte")),
            support_staff_fte=_as_float(record.get("support_staff_fte")),
            teachers_without_qts_fte=_as_float(record.get("teachers_without_qts_fte")),
            part_time_teacher_pct=_as_float(record.get("part_time_teacher_pct")),
            pupil_qualified_teacher_ratio=_as_float(
                record.get("pupil_qualified_teacher_ratio")
            ),
            pupil_teacher_ratio=_as_float(record.get("pupil_teacher_ratio")),
            pupil_adult_ratio=_as_float(record.get("pupil_adult_ratio")),
            data_year=_as_str(record.get("workforce_year")),
            ratio_year=_as_str(record.get("workforce_ratio_year")),
            source=_as_str(record.get("workforce_source")),
            source_dataset_id=_as_str(record.get("workforce_source_dataset_id")),
            ratio_source=_as_str(record.get("workforce_ratio_source")),
            ratio_source_dataset_id=_as_str(
                record.get("workforce_ratio_source_dataset_id")
            ),
            source_urn=_as_str(record.get("workforce_source_urn")),
            source_school_name=_as_str(record.get("workforce_source_school_name")),
            source_kind=_as_str(record.get("workforce_source_kind")),
            source_link_depth=_as_int(record.get("workforce_source_link_depth")),
        ),
        admissions=AdmissionsInformation(
            policy=_as_str(record.get("admissions_policy")),
            selective=_as_bool(record.get("selective")),
            published_admission_number=_as_int(record.get("published_admission_number")),
            catchment_description=_as_str(record.get("catchment_description")),
            last_offer_distance_miles=_as_float(record.get("last_offer_distance_miles")),
            last_offer_year=_as_str(record.get("last_offer_year")),
            likelihood=_as_str(record.get("admissions_likelihood")),
        ),
        travel=TravelInformation(
            distance_miles=_as_float(record.get("distance_miles")),
            walking_minutes=_as_int(record.get("walking_minutes")),
            public_transport_minutes=_as_int(record.get("public_transport_minutes")),
            annual_transport_cost_gbp=_as_float(record.get("annual_transport_cost_gbp")),
            school_day=school_day,
            leave_home_time=_as_time(record.get("leave_home_time")),
            home_arrival_time=_as_time(record.get("home_arrival_time")),
            total_day_minutes=_as_int(record.get("total_day_minutes")),
        ),
        preference_score=preference_score,
        user_assessment=assessment,
    )



def school_benchmark_from_flat_record(record: Mapping[str, Any]) -> SchoolBenchmarks:
    """Translate a canonical benchmark row into the application contract."""

    return SchoolBenchmarks(
        label=_as_str(record.get("benchmark_name")) or "",
        level=_as_str(record.get("benchmark_level")),
        code=_as_str(record.get("benchmark_code")),
        source=_as_str(record.get("source")),
        source_dataset_id=_as_str(record.get("source_dataset_id")),
        academics=AcademicPerformance(
            data_year=_as_str(record.get("performance_year")),
            progress8=_as_float(record.get("progress8")),
            progress8_year=_as_str(record.get("progress8_year")),
            english_maths_grade5_pct=_as_float(
                record.get("english_maths_grade5_pct")
            ),
            english_maths_grade4_pct=_as_float(
                record.get("english_maths_grade4_pct")
            ),
            attainment8=_as_float(record.get("attainment8")),
            ebacc_entry_pct=_as_float(record.get("ebacc_entry_pct")),
            ebacc_aps=_as_float(record.get("ebacc_aps")),
        ),
        attendance=AttendanceStatistics(
            enrolments=_as_int(record.get("attendance_enrolments")),
            overall_absence_pct=_as_float(record.get("overall_absence_pct")),
            authorised_absence_pct=_as_float(record.get("authorised_absence_pct")),
            unauthorised_absence_pct=_as_float(record.get("unauthorised_absence_pct")),
            persistent_absence_pct=_as_float(record.get("persistent_absence_pct")),
            severe_absence_pct=_as_float(record.get("severe_absence_pct")),
            data_year=_as_str(record.get("attendance_year")),
            source=_as_str(record.get("attendance_source")),
            source_dataset_id=_as_str(record.get("attendance_source_dataset_id")),
        ),
        behaviour=BehaviourStatistics(
            pupil_headcount=_as_int(record.get("behaviour_pupil_headcount")),
            suspension_count=_as_int(record.get("suspension_count")),
            suspension_rate=_as_float(record.get("suspension_rate")),
            pupils_with_one_or_more_suspension=_as_int(
                record.get("pupils_with_one_or_more_suspension")
            ),
            pupils_with_one_or_more_suspension_rate=_as_float(
                record.get("pupils_with_one_or_more_suspension_rate")
            ),
            permanent_exclusion_count=_as_int(record.get("permanent_exclusion_count")),
            permanent_exclusion_rate=_as_float(record.get("permanent_exclusion_rate")),
            data_year=_as_str(record.get("behaviour_year")),
            source=_as_str(record.get("behaviour_source")),
            source_dataset_id=_as_str(record.get("behaviour_source_dataset_id")),
        ),
        workforce=WorkforceStatistics(
            pupil_fte=_as_float(record.get("pupil_fte")),
            teacher_fte=_as_float(record.get("teacher_fte")),
            qualified_teacher_fte=_as_float(record.get("qualified_teacher_fte")),
            classroom_teacher_fte=_as_float(record.get("classroom_teacher_fte")),
            teaching_assistant_fte=_as_float(record.get("teaching_assistant_fte")),
            support_staff_fte=_as_float(record.get("support_staff_fte")),
            teachers_without_qts_fte=_as_float(record.get("teachers_without_qts_fte")),
            part_time_teacher_pct=_as_float(record.get("part_time_teacher_pct")),
            pupil_qualified_teacher_ratio=_as_float(
                record.get("pupil_qualified_teacher_ratio")
            ),
            pupil_teacher_ratio=_as_float(record.get("pupil_teacher_ratio")),
            pupil_adult_ratio=_as_float(record.get("pupil_adult_ratio")),
            data_year=_as_str(record.get("workforce_year")),
            ratio_year=_as_str(record.get("workforce_ratio_year")),
            source=_as_str(record.get("workforce_source")),
            source_dataset_id=_as_str(record.get("workforce_source_dataset_id")),
            ratio_source=_as_str(record.get("workforce_ratio_source")),
            ratio_source_dataset_id=_as_str(
                record.get("workforce_ratio_source_dataset_id")
            ),
        ),
    )

def _preference_raw_value(
    record: Mapping[str, Any],
    metric: PreferenceMetric,
) -> float | str | None:
    if metric is PreferenceMetric.DISTANCE:
        return _as_float(record.get("distance_miles"))
    if metric is PreferenceMetric.OFSTED:
        return _as_str(record.get("ofsted_equivalent_rating"))
    column = {
        PreferenceMetric.ATTAINMENT8: "attainment8",
        PreferenceMetric.PROGRESS8: "progress8",
        PreferenceMetric.GRADE5_ENGLISH_MATHS: "english_maths_grade5_pct",
        PreferenceMetric.EBACC_APS: "ebacc_aps",
    }[metric]
    return _as_float(record.get(column))


def _preference_score_from_record(record: Mapping[str, Any]) -> SchoolScore | None:
    if "preference_score_coverage_pct" not in record:
        return None

    components = []
    for metric in PreferenceMetric:
        key = metric.value.replace("-", "_")
        components.append(
            ScoreComponent(
                metric=metric,
                raw_value=_preference_raw_value(record, metric),
                score=_as_float(record.get(f"preference_{key}_score")),
                requested_weight_pct=_as_float(
                    record.get(f"preference_{key}_requested_weight_pct")
                )
                or 0.0,
                effective_weight_pct=_as_float(
                    record.get(f"preference_{key}_effective_weight_pct")
                )
                or 0.0,
            )
        )

    return SchoolScore(
        overall=_as_float(record.get("preference_score")),
        coverage_pct=_as_float(record.get("preference_score_coverage_pct")) or 0.0,
        components=tuple(components),
    )


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if text in {"", "<NA>", "NaT", "nan", "None", "N/A", "?"}:
        return True
    try:
        return bool(value != value)  # NaN
    except (TypeError, ValueError):
        return False


def _as_str(value: Any) -> str | None:
    if _is_missing(value):
        return None
    return str(value).strip()


def _as_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    if number is None:
        return None
    return int(round(number))


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _as_str(value)
    if text is None:
        return None
    lowered = text.casefold()
    if lowered in {"true", "yes", "y", "1"}:
        return True
    if lowered in {"false", "no", "n", "0"}:
        return False
    return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _as_str(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_time(value: Any) -> time | None:
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, time):
        return value.replace(microsecond=0)
    text = _as_str(value)
    if text is None:
        return None
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M%p", "%I:%M %p"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            pass
    return None


def _serialise(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _serialise(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialise(item) for item in value]
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value
