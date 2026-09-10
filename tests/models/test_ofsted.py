import pytest

from school_finder.models.ofsted import (
    OfstedEquivalentBasis,
    OfstedRating,
    derive_equivalent_ofsted_rating,
)


RENEWED_GOOD = dict(
    safeguarding="Met",
    inclusion="Expected standard",
    curriculum_teaching="Expected standard",
    achievement="Expected standard",
    attendance_behaviour="Expected standard",
    personal_development="Expected standard",
    leadership="Expected standard",
)

RENEWED_STRONG = dict(
    safeguarding="Met",
    inclusion="Strong standard",
    curriculum_teaching="Strong standard",
    achievement="Exceptional",
    attendance_behaviour="Strong standard",
    personal_development="Exceptional",
    leadership="Strong standard",
)

ORIGINAL_GOOD = dict(
    safeguarding="Effective",
    curriculum_teaching="Good",
    attendance_behaviour="Outstanding",
    personal_development="Good",
    leadership="Good",
)


def test_official_overall_rating_is_always_preferred():
    result = derive_equivalent_ofsted_rating(
        official_rating="Good",
        safeguarding="Not met",
        inclusion="Urgent improvement",
    )
    assert result.rating is OfstedRating.GOOD
    assert result.basis is OfstedEquivalentBasis.OFFICIAL
    assert "Official" in result.explanation


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Outstanding", OfstedRating.OUTSTANDING),
        ("GOOD", OfstedRating.GOOD),
        (" requires improvement ", OfstedRating.REQUIRES_IMPROVEMENT),
        ("Inadequate", OfstedRating.INADEQUATE),
    ],
)
def test_official_rating_normalisation(value, expected):
    result = derive_equivalent_ofsted_rating(official_rating=value)
    assert result.rating is expected
    assert result.basis is OfstedEquivalentBasis.OFFICIAL


def test_original_eif_quality_requires_improvement_caps_equivalent_rating():
    values = ORIGINAL_GOOD | {"curriculum_teaching": "Requires improvement"}
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is OfstedRating.REQUIRES_IMPROVEMENT
    assert result.basis is OfstedEquivalentBasis.ORIGINAL_EIF
    assert "Quality of education" in result.explanation


def test_original_eif_any_key_judgement_requires_improvement_caps_rating():
    values = ORIGINAL_GOOD | {"leadership": "Requires Improvement"}
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is OfstedRating.REQUIRES_IMPROVEMENT
    assert "Leadership and management" in result.explanation


def test_original_eif_any_inadequate_key_judgement_gives_inadequate():
    values = ORIGINAL_GOOD | {"attendance_behaviour": "Inadequate"}
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is OfstedRating.INADEQUATE
    assert result.basis is OfstedEquivalentBasis.ORIGINAL_EIF


def test_original_eif_ineffective_safeguarding_gives_inadequate():
    values = ORIGINAL_GOOD | {"safeguarding": "Ineffective"}
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is OfstedRating.INADEQUATE
    assert result.basis is OfstedEquivalentBasis.ORIGINAL_EIF
    assert "safeguarding" in result.explanation.casefold()


def test_original_eif_all_outstanding_gives_outstanding():
    result = derive_equivalent_ofsted_rating(
        safeguarding="Yes",
        curriculum_teaching="Outstanding",
        attendance_behaviour="Outstanding",
        personal_development="Outstanding",
        leadership="Outstanding",
    )
    assert result.rating is OfstedRating.OUTSTANDING
    assert "all four" in result.explanation


def test_original_eif_one_good_prevents_inferred_outstanding():
    result = derive_equivalent_ofsted_rating(
        safeguarding="Effective",
        curriculum_teaching="Outstanding",
        attendance_behaviour="Outstanding",
        personal_development="Good",
        leadership="Outstanding",
    )
    assert result.rating is OfstedRating.GOOD
    assert result.basis is OfstedEquivalentBasis.ORIGINAL_EIF


def test_original_eif_missing_key_judgement_is_unavailable_unless_inadequate_known():
    result = derive_equivalent_ofsted_rating(
        safeguarding="Effective",
        curriculum_teaching="Good",
        attendance_behaviour="Good",
        personal_development="Good",
    )
    assert result.rating is None
    assert result.basis is OfstedEquivalentBasis.UNAVAILABLE

    definite = derive_equivalent_ofsted_rating(
        safeguarding=None,
        curriculum_teaching="Inadequate",
    )
    assert definite.rating is OfstedRating.INADEQUATE
    assert definite.basis is OfstedEquivalentBasis.ORIGINAL_EIF


def test_original_eif_unknown_safeguarding_does_not_overstate_rating():
    result = derive_equivalent_ofsted_rating(**(ORIGINAL_GOOD | {"safeguarding": None}))
    assert result.rating is None
    assert result.basis is OfstedEquivalentBasis.UNAVAILABLE


@pytest.mark.parametrize(
    ("renewed_grade", "expected"),
    [
        ("Urgent improvement", OfstedRating.INADEQUATE),
        ("Needs attention", OfstedRating.REQUIRES_IMPROVEMENT),
        ("Expected standard", OfstedRating.GOOD),
        ("Strong standard", OfstedRating.OUTSTANDING),
        ("Exceptional", OfstedRating.OUTSTANDING),
    ],
)
def test_renewed_eif_grade_mapping_when_all_core_areas_match(renewed_grade, expected):
    values = {
        "safeguarding": "Met",
        "inclusion": renewed_grade,
        "curriculum_teaching": renewed_grade,
        "achievement": renewed_grade,
        "attendance_behaviour": renewed_grade,
        "personal_development": renewed_grade,
        "leadership": renewed_grade,
    }
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is expected
    assert result.basis is OfstedEquivalentBasis.RENEWED_EIF


def test_renewed_eif_weakest_core_area_caps_overall_equivalent():
    values = RENEWED_STRONG | {"curriculum_teaching": "Needs attention"}
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is OfstedRating.REQUIRES_IMPROVEMENT
    assert "Curriculum and teaching: Needs attention" in result.explanation


def test_renewed_eif_expected_standard_caps_otherwise_strong_school_at_good():
    values = RENEWED_STRONG | {"achievement": "Expected standard"}
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is OfstedRating.GOOD
    assert "Achievement: Expected standard" in result.explanation


def test_renewed_eif_all_strong_or_exceptional_gives_outstanding():
    result = derive_equivalent_ofsted_rating(**RENEWED_STRONG)
    assert result.rating is OfstedRating.OUTSTANDING
    assert result.basis is OfstedEquivalentBasis.RENEWED_EIF


def test_renewed_eif_safeguarding_not_met_gives_inadequate():
    values = RENEWED_STRONG | {"safeguarding": "Not met"}
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is OfstedRating.INADEQUATE
    assert result.basis is OfstedEquivalentBasis.RENEWED_EIF


def test_renewed_eif_missing_core_area_is_unavailable_unless_urgent_known():
    values = RENEWED_GOOD | {"leadership": None}
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is None
    assert result.basis is OfstedEquivalentBasis.UNAVAILABLE

    definite = derive_equivalent_ofsted_rating(
        inclusion="Urgent improvement",
        safeguarding=None,
    )
    assert definite.rating is OfstedRating.INADEQUATE
    assert definite.basis is OfstedEquivalentBasis.RENEWED_EIF


def test_renewed_eif_unknown_safeguarding_is_unavailable():
    values = RENEWED_GOOD | {"safeguarding": "Not set"}
    result = derive_equivalent_ofsted_rating(**values)
    assert result.rating is None
    assert result.basis is OfstedEquivalentBasis.UNAVAILABLE


def test_unrecognised_or_absent_inspection_data_is_unavailable():
    result = derive_equivalent_ofsted_rating(
        official_rating="Not judged",
        safeguarding="Unknown",
        curriculum_teaching="Not applicable",
    )
    assert result.rating is None
    assert result.basis is OfstedEquivalentBasis.UNAVAILABLE
    assert "No comparable" in result.explanation


def test_safeguarding_no_is_recognised_as_failure_even_without_framework_grades():
    result = derive_equivalent_ofsted_rating(safeguarding="No")
    assert result.rating is OfstedRating.INADEQUATE
    assert result.basis is OfstedEquivalentBasis.UNAVAILABLE


def test_safeguarding_case_and_whitespace_are_normalised():
    result = derive_equivalent_ofsted_rating(**(RENEWED_GOOD | {"safeguarding": "  MET  "}))
    assert result.rating is OfstedRating.GOOD
