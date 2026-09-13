import pytest

from school_finder.models.personalisation import PersonalSchoolState, SchoolDisposition


def test_personal_school_state_defaults_to_neutral_and_empty():
    state = PersonalSchoolState()
    assert state.disposition is SchoolDisposition.NEUTRAL
    assert state.rating is None
    assert state.notes is None
    assert state.is_default is True


def test_personal_school_state_normalises_notes_and_reports_non_default():
    state = PersonalSchoolState(
        disposition=SchoolDisposition.SHORTLISTED,
        rating=4,
        notes="  Great open evening.  ",
    )
    assert state.notes == "Great open evening."
    assert state.is_default is False

    notes_only = PersonalSchoolState(notes="Useful note")
    assert notes_only.is_default is False

    rating_only = PersonalSchoolState(rating=1)
    assert rating_only.is_default is False

    assert PersonalSchoolState(notes="   ").is_default is True


def test_personal_school_state_requires_a_disposition_enum():
    with pytest.raises(TypeError, match="SchoolDisposition"):
        PersonalSchoolState(disposition="shortlisted")  # type: ignore[arg-type]


@pytest.mark.parametrize("rating", [True, 0, 6, 2.5])
def test_personal_school_state_rejects_invalid_ratings(rating):
    with pytest.raises(ValueError, match="integer from 1 to 5"):
        PersonalSchoolState(rating=rating)


@pytest.mark.parametrize("rating", [1, 2, 3, 4, 5, None])
def test_personal_school_state_accepts_valid_ratings(rating):
    assert PersonalSchoolState(rating=rating).rating == rating
