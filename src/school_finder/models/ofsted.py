"""Ofsted rating normalisation and School Finder equivalent overall grades."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OfstedRating(StrEnum):
    OUTSTANDING = "Outstanding"
    GOOD = "Good"
    REQUIRES_IMPROVEMENT = "Requires improvement"
    INADEQUATE = "Inadequate"


class OfstedEquivalentBasis(StrEnum):
    OFFICIAL = "official"
    ORIGINAL_EIF = "derived-original-eif"
    RENEWED_EIF = "derived-renewed-eif"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class OfstedEquivalent:
    rating: OfstedRating | None
    basis: OfstedEquivalentBasis
    explanation: str


_OLD_GRADES = {
    "outstanding": OfstedRating.OUTSTANDING,
    "good": OfstedRating.GOOD,
    "requires improvement": OfstedRating.REQUIRES_IMPROVEMENT,
    "inadequate": OfstedRating.INADEQUATE,
}

_RENEWED_TO_OLD_BAND = {
    "exceptional": OfstedRating.OUTSTANDING,
    "strong standard": OfstedRating.OUTSTANDING,
    "expected standard": OfstedRating.GOOD,
    "needs attention": OfstedRating.REQUIRES_IMPROVEMENT,
    "urgent improvement": OfstedRating.INADEQUATE,
}

_RATING_SCORE = {
    OfstedRating.INADEQUATE: 1,
    OfstedRating.REQUIRES_IMPROVEMENT: 2,
    OfstedRating.GOOD: 3,
    OfstedRating.OUTSTANDING: 4,
}

_SAFEGUARDING_PASS = {
    "met",
    "effective",
    "yes",
}
_SAFEGUARDING_FAIL = {
    "not met",
    "ineffective",
    "no",
}


def _normalise(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().casefold()
    if not text or text in {"nan", "none", "null", "not applicable", "not set"}:
        return None
    return text


def _old_grade(value: object) -> OfstedRating | None:
    text = _normalise(value)
    return _OLD_GRADES.get(text) if text else None


def _renewed_grade(value: object) -> OfstedRating | None:
    text = _normalise(value)
    return _RENEWED_TO_OLD_BAND.get(text) if text else None


def _safeguarding_state(value: object) -> bool | None:
    text = _normalise(value)
    if text in _SAFEGUARDING_PASS:
        return True
    if text in _SAFEGUARDING_FAIL:
        return False
    return None


def _worst_rating(ratings: list[OfstedRating]) -> OfstedRating:
    return min(ratings, key=_RATING_SCORE.__getitem__)


def derive_equivalent_ofsted_rating(
    *,
    official_rating: object = None,
    safeguarding: object = None,
    inclusion: object = None,
    curriculum_teaching: object = None,
    achievement: object = None,
    attendance_behaviour: object = None,
    personal_development: object = None,
    leadership: object = None,
) -> OfstedEquivalent:
    official = _old_grade(official_rating)
    if official is not None:
        return OfstedEquivalent(
            rating=official,
            basis=OfstedEquivalentBasis.OFFICIAL,
            explanation="Official Ofsted overall effectiveness grade.",
        )

    safeguarding_state = _safeguarding_state(safeguarding)
    if safeguarding_state is False:
        return OfstedEquivalent(
            rating=OfstedRating.INADEQUATE,
            basis=_infer_derived_basis(
                inclusion,
                curriculum_teaching,
                achievement,
                attendance_behaviour,
                personal_development,
                leadership,
            ),
            explanation=(
                "Equivalent rating capped at Inadequate because safeguarding "
                "is not met/effective."
            ),
        )

    renewed_values = [
        inclusion,
        curriculum_teaching,
        achievement,
        attendance_behaviour,
        personal_development,
        leadership,
    ]
    renewed_ratings = [_renewed_grade(value) for value in renewed_values]
    if any(rating is not None for rating in renewed_ratings):
        known = [rating for rating in renewed_ratings if rating is not None]
        worst = _worst_rating(known)

        if worst is OfstedRating.INADEQUATE:
            return OfstedEquivalent(
                rating=worst,
                basis=OfstedEquivalentBasis.RENEWED_EIF,
                explanation=_renewed_explanation(renewed_values, renewed_ratings, worst),
            )

        if safeguarding_state is not True or any(
            rating is None for rating in renewed_ratings
        ):
            return OfstedEquivalent(
                rating=None,
                basis=OfstedEquivalentBasis.UNAVAILABLE,
                explanation=(
                    "Not enough renewed-EIF evaluation data to derive a reliable "
                    "equivalent overall rating."
                ),
            )

        return OfstedEquivalent(
            rating=worst,
            basis=OfstedEquivalentBasis.RENEWED_EIF,
            explanation=_renewed_explanation(renewed_values, renewed_ratings, worst),
        )

    old_values = [
        curriculum_teaching,
        attendance_behaviour,
        personal_development,
        leadership,
    ]
    old_ratings = [_old_grade(value) for value in old_values]
    if any(rating is not None for rating in old_ratings):
        known = [rating for rating in old_ratings if rating is not None]
        worst = _worst_rating(known)

        if worst is OfstedRating.INADEQUATE:
            return OfstedEquivalent(
                rating=worst,
                basis=OfstedEquivalentBasis.ORIGINAL_EIF,
                explanation=_original_eif_explanation(old_values, old_ratings, worst),
            )

        if safeguarding_state is not True or any(rating is None for rating in old_ratings):
            return OfstedEquivalent(
                rating=None,
                basis=OfstedEquivalentBasis.UNAVAILABLE,
                explanation=(
                    "Not enough original-EIF key judgement data to derive a reliable "
                    "equivalent overall rating."
                ),
            )

        if worst is OfstedRating.REQUIRES_IMPROVEMENT:
            equivalent = OfstedRating.REQUIRES_IMPROVEMENT
        else:
            equivalent = (
                OfstedRating.OUTSTANDING
                if all(rating is OfstedRating.OUTSTANDING for rating in old_ratings)
                else OfstedRating.GOOD
            )
        return OfstedEquivalent(
            rating=equivalent,
            basis=OfstedEquivalentBasis.ORIGINAL_EIF,
            explanation=_original_eif_explanation(old_values, old_ratings, equivalent),
        )

    return OfstedEquivalent(
        rating=None,
        basis=OfstedEquivalentBasis.UNAVAILABLE,
        explanation="No comparable Ofsted overall or evaluation grades are available.",
    )


def _infer_derived_basis(*values: object) -> OfstedEquivalentBasis:
    if any(_renewed_grade(value) is not None for value in values):
        return OfstedEquivalentBasis.RENEWED_EIF
    if any(_old_grade(value) is not None for value in values):
        return OfstedEquivalentBasis.ORIGINAL_EIF
    return OfstedEquivalentBasis.UNAVAILABLE


def _renewed_explanation(
    values: list[object],
    ratings: list[OfstedRating | None],
    result: OfstedRating,
) -> str:
    labels = [
        "Inclusion",
        "Curriculum and teaching",
        "Achievement",
        "Attendance and behaviour",
        "Personal development and wellbeing",
        "Leadership and governance",
    ]
    limiting = [
        f"{label}: {str(value).strip()}"
        for label, value, rating in zip(labels, values, ratings, strict=True)
        if rating is result
    ]
    detail = "; ".join(limiting)
    return (
        f"Derived from renewed EIF evaluation areas using School Finder's "
        f"four-band limiting-judgement method. Limiting area(s): {detail}."
    )


def _original_eif_explanation(
    values: list[object],
    ratings: list[OfstedRating | None],
    result: OfstedRating,
) -> str:
    labels = [
        "Quality of education",
        "Behaviour and attitudes",
        "Personal development",
        "Leadership and management",
    ]
    limiting = [
        f"{label}: {str(value).strip()}"
        for label, value, rating in zip(labels, values, ratings, strict=True)
        if rating is result
    ]
    if result is OfstedRating.OUTSTANDING:
        return (
            "Derived from original EIF key judgements: all four published key "
            "judgements are Outstanding and safeguarding is effective."
        )
    detail = "; ".join(limiting)
    return (
        "Derived conservatively from original EIF key judgements using the former "
        f"limiting-judgement rules. Limiting area(s): {detail}."
    )
