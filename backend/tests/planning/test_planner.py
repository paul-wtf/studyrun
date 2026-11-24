from datetime import date, timedelta

import pytest

from studyrun.models.db import AttemptStatus
from studyrun.planning.planner import PlanSubject, plan

TODAY = date(2026, 11, 24)
SEMESTERS = {
    "3a": date(2026, 4, 1),
    "3b": date(2026, 7, 1),
    "4a": date(2026, 10, 1),
    "4b": date(2027, 1, 1),
    "5a": date(2027, 4, 1),
    "5b": date(2027, 7, 1),
    "6a": date(2027, 10, 1),
}
SITTINGS = [
    date(2026, 12, 6),
    date(2027, 2, 14),
    date(2027, 5, 16),
    date(2027, 8, 22),
    date(2027, 11, 14),
    date(2028, 2, 20),
]
FAST = 100.0

REGISTERED = AttemptStatus.registered
PLANNED = AttemptStatus.planned
PASSED = AttemptStatus.passed
FAILED = AttemptStatus.failed


def subject(
    id,
    *,
    name=None,
    earliest="3a",
    rec=None,
    not_before=None,
    sittings=SITTINGS,
    effort=10,
    material=True,
    attempts=(),
):
    return PlanSubject(
        id=id,
        name=name or f"Fach {id}",
        earliest_semester=earliest,
        recommended_semester=rec,
        not_before=not_before,
        sittings=list(sittings),
        effort_items=effort,
        has_material=material,
        attempts=list(attempts),
    )


def run(subjects, *, today=TODAY, pace=FAST, semesters=SEMESTERS):
    result = plan(subjects, semesters, today, pace)
    return result, {e.subject_id: e for e in result.entries}


def kinds(result):
    return sorted((c.subject_id, c.kind) for c in result.conflicts)


def test_targets_recommended_semester():
    result, entries = run([subject(1, rec=5)])
    entry = entries[1]
    assert (entry.state, entry.sitting, entry.feasible) == ("open", date(2027, 5, 16), True)
    assert entry.register_by == date(2027, 4, 25)
    assert result.order == [1]
    assert result.conflicts == []


def test_recommended_semester_already_past_takes_earliest_after():
    _, entries = run([subject(1, rec=3)])
    assert entries[1].sitting == date(2027, 2, 14)


def test_unknown_recommended_semester_start_takes_earliest():
    _, entries = run([subject(1, rec=7)])
    assert entries[1].sitting == date(2027, 2, 14)


def test_surplus_subjects_take_free_months_before_the_window():
    result, entries = run([subject(i, rec=6) for i in (1, 2, 3, 4)])
    assert [entries[i].sitting for i in (1, 2, 3, 4)] == [
        date(2027, 11, 14),
        date(2028, 2, 20),
        date(2027, 8, 22),
        date(2027, 5, 16),
    ]
    assert result.order == [4, 3, 1, 2]
    assert result.conflicts == []


def test_window_beyond_all_sittings_plans_the_latest_before_it():
    semesters = {**SEMESTERS, "7a": date(2028, 4, 1)}
    _, entries = run([subject(1, rec=7), subject(2, rec=7)], semesters=semesters)
    assert (entries[1].state, entries[1].sitting) == ("open", date(2028, 2, 20))
    assert entries[2].sitting == date(2027, 11, 14)


def test_window_beyond_all_sittings_without_eligible_ones_is_pending():
    semesters = {**SEMESTERS, "7a": date(2028, 4, 1)}
    result, entries = run(
        [subject(1, earliest="6a", rec=7, sittings=SITTINGS[:4])], semesters=semesters
    )
    assert (entries[1].state, entries[1].sitting) == ("sittings_pending", None)
    assert result.conflicts == []


def test_eligibility_from_semester_start():
    _, entries = run([subject(1, earliest="5b")])
    assert entries[1].sitting == date(2027, 8, 22)


def test_sitting_on_semester_start_is_eligible():
    semesters = {**SEMESTERS, "5b": date(2027, 8, 22)}
    _, entries = run([subject(1, earliest="5b")], semesters=semesters)
    assert entries[1].sitting == date(2027, 8, 22)


def test_not_before():
    _, entries = run([subject(1, not_before=date(2027, 5, 17))])
    assert entries[1].sitting == date(2027, 8, 22)
    _, entries = run([subject(1, not_before=date(2027, 5, 16))])
    assert entries[1].sitting == date(2027, 5, 16)


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 11, 15), date(2026, 12, 6)),
        (date(2026, 11, 16), date(2027, 2, 14)),
    ],
)
def test_registration_deadline_boundary(today, expected):
    _, entries = run([subject(1)], today=today)
    assert entries[1].sitting == expected
    assert entries[1].register_by == expected - timedelta(days=21)


def test_two_subjects_on_the_same_date_get_different_months():
    shared = [date(2027, 2, 14), date(2027, 5, 16)]
    result, entries = run(
        [subject(2, name="Beta", sittings=shared), subject(1, name="Alpha", sittings=shared)]
    )
    assert entries[1].sitting == date(2027, 2, 14)
    assert entries[2].sitting == date(2027, 5, 16)
    assert result.order == [1, 2]


def test_same_month_different_day_is_pushed_too():
    result, entries = run(
        [
            subject(1, sittings=[date(2027, 2, 14)]),
            subject(2, sittings=[date(2027, 2, 21), date(2027, 5, 16)]),
        ]
    )
    assert entries[2].sitting == date(2027, 5, 16)
    assert result.conflicts == []


def test_no_free_month_is_a_conflict_without_a_sitting():
    result, entries = run(
        [subject(1, sittings=[date(2027, 2, 14)]), subject(2, sittings=[date(2027, 2, 21)])]
    )
    assert entries[1].sitting == date(2027, 2, 14)
    assert (entries[2].state, entries[2].sitting, entries[2].feasible) == ("open", None, False)
    assert kinds(result) == [(2, "no_feasible_sitting")]
    assert result.order == [1]


def test_registered_earlier_sitting_is_kept_and_others_move():
    result, entries = run(
        [
            subject(1, name="Alpha", rec=4),
            subject(2, name="Beta", rec=5, attempts=[(date(2027, 2, 14), REGISTERED)]),
        ]
    )
    assert (entries[2].state, entries[2].sitting) == ("registered", date(2027, 2, 14))
    assert entries[2].register_by is None
    assert entries[1].sitting == date(2027, 5, 16)
    assert result.order == [2, 1]
    assert result.conflicts == []


def test_study_order_follows_the_sittings():
    result, entries = run(
        [
            subject(1, effort=30, attempts=[(date(2027, 5, 16), REGISTERED)]),
            subject(2, effort=30),
        ],
        pace=1.0,
    )
    assert entries[2].sitting == date(2027, 2, 14)
    assert result.order == [2, 1]
    assert entries[2].study_from == TODAY
    assert entries[1].study_from == entries[2].study_until


def test_registering_the_proposal_keeps_the_plan():
    subjects = [subject(1, rec=4, effort=40), subject(2, rec=4, effort=40), subject(3, rec=5)]
    before, entries = run(subjects, pace=1.0)
    proposed = entries[1].sitting
    subjects[0] = subject(1, rec=4, effort=40, attempts=[(proposed, REGISTERED)])
    after, again = run(subjects, pace=1.0)
    assert again[1].state == "registered"
    assert [(e.subject_id, e.sitting, e.study_until) for e in after.entries] == [
        (e.subject_id, e.sitting, e.study_until) for e in before.entries
    ]
    assert after.order == before.order


def test_open_subject_does_not_break_a_registered_one():
    result, entries = run(
        [
            subject(1, name="Alpha", sittings=[date(2027, 1, 10), date(2027, 5, 16)], effort=30),
            subject(2, name="Beta", effort=60, attempts=[(date(2027, 2, 14), REGISTERED)]),
        ],
        pace=1.0,
    )
    assert entries[2].feasible
    assert entries[2].study_until == date(2027, 1, 23)
    assert entries[1].sitting == date(2027, 5, 16)
    assert (entries[1].study_from, entries[1].study_until) == (
        date(2027, 1, 23),
        date(2027, 2, 22),
    )
    assert result.order == [2, 1]


def test_harmful_only_candidate_is_not_scheduled():
    result, entries = run(
        [
            subject(1, name="Alpha", sittings=[date(2027, 2, 27)], effort=20),
            subject(
                2,
                name="Beta",
                sittings=[date(2027, 3, 20)],
                effort=100,
                attempts=[(date(2027, 3, 20), REGISTERED)],
            ),
        ],
        pace=1.0,
    )
    assert (entries[1].state, entries[1].sitting, entries[1].feasible) == ("open", None, False)
    assert entries[2].feasible
    assert entries[2].study_until == date(2027, 3, 4)
    assert result.order == [2]
    assert kinds(result) == [(1, "no_feasible_sitting")]
    assert "Beta" in result.conflicts[0].message_de


def test_kept_hand_planned_sitting_reports_whom_it_squeezes():
    result, entries = run(
        [
            subject(
                1,
                name="Alpha",
                sittings=[date(2027, 2, 27)],
                effort=20,
                attempts=[(date(2027, 2, 27), PLANNED)],
            ),
            subject(
                2,
                name="Beta",
                sittings=[date(2027, 3, 20)],
                effort=100,
                attempts=[(date(2027, 3, 20), REGISTERED)],
            ),
        ],
        pace=1.0,
    )
    assert (entries[1].state, entries[1].sitting) == ("planned", date(2027, 2, 27))
    assert not entries[2].feasible
    assert kinds(result) == [(1, "squeezes_other")]
    assert result.conflicts[0].message_de == (
        "Dein Termin für Alpha macht die Vorbereitung auf Beta zu knapp."
    )


def test_fallback_names_the_subject_a_fitting_sitting_would_squeeze():
    result, entries = run(
        [
            subject(1, name="Alpha", sittings=[date(2027, 2, 27), date(2027, 4, 25)], effort=80),
            subject(
                2,
                name="Beta",
                sittings=[date(2027, 3, 20)],
                effort=100,
                attempts=[(date(2027, 3, 20), REGISTERED)],
            ),
        ],
        pace=1.0,
    )
    assert (entries[1].sitting, entries[1].feasible) == (date(2027, 4, 25), False)
    assert entries[2].feasible
    assert kinds(result) == [(1, "no_feasible_sitting")]
    message = result.conflicts[0].message_de
    assert "Beta" in message and "reicht die Zeit für keinen Termin" not in message
    assert "25.04.2027" in message


def test_effort_too_large_takes_a_later_sitting():
    _, entries = run([subject(1, effort=100)], pace=1.0)
    entry = entries[1]
    assert entry.sitting == date(2027, 5, 16)
    assert (entry.study_from, entry.study_until, entry.feasible) == (
        TODAY,
        date(2027, 3, 4),
        True,
    )


def test_study_order_chains_subjects():
    result, entries = run([subject(1, effort=60), subject(2, effort=60)], pace=1.0)
    assert entries[1].sitting == date(2027, 2, 14)
    assert (entries[1].study_from, entries[1].study_until) == (TODAY, date(2027, 1, 23))
    assert entries[2].sitting == date(2027, 5, 16)
    assert (entries[2].study_from, entries[2].study_until) == (
        date(2027, 1, 23),
        date(2027, 3, 24),
    )
    assert result.order == [1, 2]


def test_effort_rounds_up_to_whole_days():
    _, entries = run([subject(1, effort=9)], pace=4.0)
    assert entries[1].study_until == TODAY + timedelta(days=3)
    _, entries = run([subject(1, effort=3)], pace=0.1)
    assert entries[1].study_until == TODAY + timedelta(days=30)


def test_no_feasible_sitting_keeps_the_latest_candidate():
    result, entries = run([subject(1, effort=10_000)], pace=1.0)
    entry = entries[1]
    assert (entry.state, entry.sitting, entry.feasible) == ("open", date(2028, 2, 20), False)
    assert kinds(result) == [(1, "no_feasible_sitting")]
    assert result.order == [1]


def test_no_material_has_no_proposal():
    result, entries = run([subject(1, material=False)])
    assert (entries[1].state, entries[1].sitting, entries[1].register_by) == (
        "no_material",
        None,
        None,
    )
    assert kinds(result) == [(1, "no_material")]
    assert result.order == []


def test_missing_semester_is_not_plannable():
    result, entries = run([subject(1, earliest="7a")])
    assert (entries[1].state, entries[1].sitting) == ("not_plannable", None)
    assert kinds(result) == [(1, "missing_semester")]
    assert "7a" in result.conflicts[0].message_de


def test_sittings_beyond_the_list_are_pending():
    result, entries = run([subject(1, earliest="6a", sittings=SITTINGS[:4])])
    assert (entries[1].state, entries[1].sitting) == ("sittings_pending", None)
    assert result.conflicts == []
    assert result.order == []


def test_no_sittings_at_all_are_pending():
    _, entries = run([subject(1, sittings=[])])
    assert entries[1].state == "sittings_pending"


def test_registered_on_exam_day_and_after():
    sitting = date(2027, 2, 14)
    _, entries = run([subject(1, attempts=[(sitting, REGISTERED)])], today=sitting)
    assert entries[1].state == "registered"
    _, entries = run([subject(1, attempts=[(sitting, REGISTERED)])], today=sitting + timedelta(1))
    assert (entries[1].state, entries[1].sitting) == ("needs_result", sitting)


def test_past_registered_without_result_still_occupies_its_month():
    today = date(2026, 11, 2)
    result, entries = run(
        [
            subject(1, attempts=[(date(2026, 11, 1), REGISTERED)]),
            subject(2, sittings=[date(2026, 11, 29), date(2027, 2, 14)]),
        ],
        today=today,
    )
    assert entries[1].state == "needs_result"
    assert entries[2].sitting == date(2027, 2, 14)
    assert result.order == [2]


def test_passed_subject_is_done_and_occupies_its_month():
    today = date(2026, 11, 2)
    result, entries = run(
        [
            subject(1, attempts=[(date(2026, 6, 1), FAILED), (date(2026, 11, 1), PASSED)]),
            subject(2, sittings=[date(2026, 11, 29), date(2027, 2, 14)]),
        ],
        today=today,
    )
    assert (entries[1].state, entries[1].sitting) == ("passed", date(2026, 11, 1))
    assert entries[2].sitting == date(2027, 2, 14)
    assert result.order == [2]


def test_failed_subject_is_planned_again():
    _, entries = run([subject(1, attempts=[(date(2026, 11, 8), FAILED)])])
    assert (entries[1].state, entries[1].sitting) == ("open", date(2027, 2, 14))


def test_planned_by_hand_is_kept_even_before_the_recommended_semester():
    result, entries = run([subject(1, rec=5, attempts=[(date(2027, 2, 14), PLANNED)])])
    entry = entries[1]
    assert (entry.state, entry.sitting, entry.register_by) == (
        "planned",
        date(2027, 2, 14),
        date(2027, 1, 24),
    )
    assert result.conflicts == []


def test_planned_by_hand_blocks_its_month_for_others():
    _, entries = run(
        [
            subject(1, attempts=[(date(2027, 5, 16), PLANNED)]),
            subject(2, sittings=[date(2027, 5, 9), date(2027, 8, 22)]),
        ]
    )
    assert entries[2].sitting == date(2027, 8, 22)


def test_planned_after_the_deadline_is_replanned_with_a_conflict():
    result, entries = run([subject(1, attempts=[(date(2026, 12, 6), PLANNED)])])
    assert (entries[1].state, entries[1].sitting) == ("open", date(2027, 2, 14))
    assert kinds(result) == [(1, "planned_not_allowed")]
    assert "06.12.2026" in result.conflicts[0].message_de
    assert "Vorgeschlagen ist jetzt der 14.02.2027" in result.conflicts[0].message_de


def test_planned_without_semester_start_says_so_and_proposes_nothing():
    result, entries = run([subject(1, earliest="7a", attempts=[(date(2027, 2, 14), PLANNED)])])
    assert entries[1].state == "not_plannable"
    assert kinds(result) == [(1, "missing_semester"), (1, "planned_not_allowed")]
    lapsed = next(c for c in result.conflicts if c.kind == "planned_not_allowed")
    assert "Startdatum" in lapsed.message_de
    assert "Vorgeschlagen" not in lapsed.message_de


def test_planned_in_a_registered_month_is_replanned_with_a_conflict():
    result, entries = run(
        [
            subject(1, attempts=[(date(2027, 2, 14), REGISTERED)]),
            subject(
                2,
                sittings=[date(2027, 2, 21), date(2027, 5, 16)],
                attempts=[(date(2027, 2, 21), PLANNED)],
            ),
        ]
    )
    assert (entries[2].state, entries[2].sitting) == ("open", date(2027, 5, 16))
    assert kinds(result) == [(2, "planned_not_allowed")]


def test_planned_before_not_before_or_eligibility_is_replanned():
    result, _ = run(
        [
            subject(1, not_before=date(2027, 3, 1), attempts=[(date(2027, 2, 14), PLANNED)]),
            subject(2, earliest="5a", attempts=[(date(2027, 2, 14), PLANNED)]),
        ]
    )
    assert kinds(result) == [(1, "planned_not_allowed"), (2, "planned_not_allowed")]


def test_past_planned_attempt_is_ignored():
    result, entries = run([subject(1, attempts=[(date(2026, 11, 8), PLANNED)])])
    assert (entries[1].state, entries[1].sitting) == ("open", date(2027, 2, 14))
    assert result.conflicts == []


def test_two_registered_in_one_month_is_a_conflict():
    result, entries = run(
        [
            subject(1, attempts=[(date(2027, 2, 14), REGISTERED)]),
            subject(2, sittings=[date(2027, 2, 21)], attempts=[(date(2027, 2, 21), REGISTERED)]),
        ]
    )
    assert entries[1].state == entries[2].state == "registered"
    assert kinds(result) == [(2, "two_in_month")]
    assert "Februar 2027" in result.conflicts[0].message_de


def test_registered_before_not_before_is_a_conflict():
    result, entries = run(
        [subject(1, not_before=date(2027, 3, 1), attempts=[(date(2027, 2, 14), REGISTERED)])]
    )
    assert entries[1].sitting == date(2027, 2, 14)
    assert kinds(result) == [(1, "before_not_before")]


def test_recommended_semester_is_processed_first():
    shared = [date(2027, 5, 16), date(2027, 8, 22)]
    _, entries = run(
        [subject(1, name="Alpha", sittings=shared), subject(2, name="Beta", rec=5, sittings=shared)]
    )
    assert entries[2].sitting == date(2027, 5, 16)
    assert entries[1].sitting == date(2027, 8, 22)


def test_earlier_eligible_sitting_is_processed_before_name():
    later = [date(2027, 5, 16), date(2027, 8, 22)]
    _, entries = run(
        [
            subject(1, name="Alpha", earliest="5a", sittings=later),
            subject(2, name="Zeta", sittings=[date(2026, 6, 7), *later]),
        ]
    )
    assert entries[2].sitting == date(2027, 5, 16)
    assert entries[1].sitting == date(2027, 8, 22)


def test_entries_follow_input_order_and_rejects_non_positive_pace():
    result, _ = run([subject(3), subject(1), subject(2)])
    assert [e.subject_id for e in result.entries] == [3, 1, 2]
    with pytest.raises(ValueError):
        plan([subject(1)], SEMESTERS, TODAY, 0.0)
