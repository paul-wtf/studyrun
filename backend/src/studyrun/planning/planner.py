from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from studyrun.models.db import AttemptStatus

REGISTRATION_DAYS = 21

EntryState = Literal[
    "open",
    "planned",
    "registered",
    "passed",
    "needs_result",
    "no_material",
    "not_plannable",
    "sittings_pending",
]
ConflictKind = Literal[
    "no_feasible_sitting",
    "two_in_month",
    "before_not_before",
    "no_material",
    "missing_semester",
    "planned_not_allowed",
]
Month = tuple[int, int]


@dataclass(frozen=True)
class PlanSubject:
    id: int
    name: str
    earliest_semester: str
    recommended_semester: int | None
    not_before: date | None
    sittings: list[date]
    effort_items: int
    has_material: bool
    attempts: list[tuple[date, AttemptStatus]] = field(default_factory=list)


@dataclass
class PlanEntry:
    subject_id: int
    state: EntryState
    sitting: date | None = None
    register_by: date | None = None
    feasible: bool = False
    study_from: date | None = None
    study_until: date | None = None


@dataclass(frozen=True)
class Conflict:
    subject_id: int
    kind: ConflictKind
    message_de: str


@dataclass(frozen=True)
class Plan:
    entries: list[PlanEntry]
    order: list[int]
    conflicts: list[Conflict]


@dataclass(frozen=True)
class _Slot:
    subject_id: int
    study_from: date
    study_until: date
    feasible: bool


def _de(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _month(d: date) -> Month:
    return d.year, d.month


_MONTHS_DE = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


def _month_de(d: date) -> str:
    return f"{_MONTHS_DE[d.month - 1]} {d.year}"


class _Planner:
    def __init__(
        self, subjects: list[PlanSubject], semesters: dict[str, date], today: date, pace: float
    ) -> None:
        self.subjects = subjects
        self.semesters = semesters
        self.today = today
        self.deadline = today + timedelta(days=REGISTRATION_DAYS)
        self.by_id = {s.id: s for s in subjects}
        self.days = {
            s.id: math.ceil(round(s.effort_items / pace, 6)) if s.effort_items > 0 else 0
            for s in subjects
        }
        self.entries = {s.id: PlanEntry(s.id, "open") for s in subjects}
        self.conflicts: list[Conflict] = []
        self.taken: dict[Month, str] = {}
        self.scheduled: dict[int, date] = {}
        self.lapsed: list[tuple[PlanSubject, date, str]] = []

    def conflict(self, subject: PlanSubject, kind: ConflictKind, message: str) -> None:
        self.conflicts.append(Conflict(subject.id, kind, message))

    def schedule(self, subject: PlanSubject, sitting: date) -> None:
        self.scheduled[subject.id] = sitting
        self.taken.setdefault(_month(sitting), subject.name)
        self.entries[subject.id].sitting = sitting

    def layout(self, scheduled: dict[int, date]) -> list[_Slot]:
        slots: list[_Slot] = []
        cursor = self.today
        for subject_id in sorted(scheduled, key=lambda i: (scheduled[i], self.by_id[i].name, i)):
            until = cursor + timedelta(days=self.days[subject_id])
            slots.append(_Slot(subject_id, cursor, until, until <= scheduled[subject_id]))
            cursor = until
        return slots

    def try_sitting(self, subject_id: int, sitting: date) -> tuple[bool, list[int]]:
        before = [s.subject_id for s in self.layout(self.scheduled) if s.feasible]
        after = {
            s.subject_id: s.feasible for s in self.layout({**self.scheduled, subject_id: sitting})
        }
        return after[subject_id], [i for i in before if not after[i]]

    def fix_attempts(self) -> tuple[list[tuple[date, PlanSubject]], list[PlanSubject]]:
        fixed: list[tuple[date, PlanSubject, EntryState]] = []
        planned: list[tuple[date, PlanSubject]] = []
        open_: list[PlanSubject] = []
        for s in self.subjects:
            passed = [d for d, st in s.attempts if st == AttemptStatus.passed]
            registered = sorted(d for d, st in s.attempts if st == AttemptStatus.registered)
            upcoming = [d for d in registered if d >= self.today]
            chosen = sorted(
                d for d, st in s.attempts if st == AttemptStatus.planned and d >= self.today
            )
            if passed:
                fixed.append((max(passed), s, "passed"))
            elif upcoming:
                fixed.append((upcoming[0], s, "registered"))
            elif registered:
                fixed.append((registered[-1], s, "needs_result"))
            elif chosen:
                planned.append((chosen[0], s))
            else:
                open_.append(s)

        for sitting, s, state in sorted(fixed, key=lambda f: (f[0], f[1].name, f[1].id)):
            entry = self.entries[s.id]
            entry.state, entry.sitting, entry.feasible = state, sitting, True
            if state == "registered":
                other = self.taken.get(_month(sitting))
                if other is not None:
                    self.conflict(
                        s,
                        "two_in_month",
                        f"Im {_month_de(sitting)} ist schon {other} angesetzt.",
                    )
                if s.not_before is not None and sitting < s.not_before:
                    self.conflict(
                        s,
                        "before_not_before",
                        f"Angemeldet für den {_de(sitting)}, möglich erst ab dem "
                        f"{_de(s.not_before)}.",
                    )
                self.schedule(s, sitting)
            else:
                self.taken.setdefault(_month(sitting), s.name)
        return sorted(planned, key=lambda p: (p[0], p[1].name, p[1].id)), open_

    def planned_problem(self, s: PlanSubject, sitting: date) -> str | None:
        eligible = self.semesters.get(s.earliest_semester)
        if sitting < self.deadline:
            return f"Die Anmeldung war bis zum {_de(sitting - timedelta(REGISTRATION_DAYS))}"
        if eligible is None:
            return f"Für Semester {s.earliest_semester} fehlt das Startdatum"
        if sitting < eligible:
            return f"Das Fach ist erst ab Semester {s.earliest_semester} zugelassen"
        if s.not_before is not None and sitting < s.not_before:
            return f"Das Fach ist erst ab dem {_de(s.not_before)} möglich"
        other = self.taken.get(_month(sitting))
        if other is not None:
            return f"Im {_month_de(sitting)} ist schon {other} angesetzt"
        return None

    def keep_planned(self, planned: list[tuple[date, PlanSubject]]) -> list[PlanSubject]:
        replan: list[PlanSubject] = []
        for sitting, s in planned:
            problem = self.planned_problem(s, sitting)
            if problem is None:
                self.entries[s.id].state = "planned"
                self.schedule(s, sitting)
            else:
                self.lapsed.append((s, sitting, problem))
                replan.append(s)
        return replan

    def report_lapsed(self) -> None:
        for s, sitting, problem in self.lapsed:
            message = f"Der gewählte Termin {_de(sitting)} geht nicht mehr: {problem}."
            proposed = self.entries[s.id].sitting
            if proposed is not None:
                message += f" Vorgeschlagen ist jetzt der {_de(proposed)}."
            self.conflict(s, "planned_not_allowed", message)

    def candidates(self, s: PlanSubject, eligible: date) -> tuple[list[date], list[date]]:
        lower = max(eligible, self.deadline, s.not_before or eligible)
        possible = sorted({d for d in s.sittings if d >= lower})
        window = (
            self.semesters.get(f"{s.recommended_semester}a")
            if s.recommended_semester is not None
            else None
        )
        if window is None:
            return possible, []
        return [d for d in possible if d >= window], [d for d in possible if d < window]

    def propose(self, open_: list[PlanSubject]) -> None:
        queue: list[tuple[PlanSubject, date, list[date], list[date]]] = []
        for s in open_:
            entry = self.entries[s.id]
            eligible = self.semesters.get(s.earliest_semester)
            if eligible is None:
                entry.state = "not_plannable"
                self.conflict(
                    s,
                    "missing_semester",
                    f"Für Semester {s.earliest_semester} fehlt das Startdatum.",
                )
                continue
            if not s.has_material:
                entry.state = "no_material"
                self.conflict(
                    s, "no_material", "Stoff fehlt: Für dieses Fach gibt es noch kein Heft."
                )
                continue
            preferred, earlier = self.candidates(s, eligible)
            if not preferred and not earlier:
                entry.state = "sittings_pending"
                continue
            first_eligible = min(d for d in s.sittings if d >= eligible)
            queue.append((s, first_eligible, preferred, earlier))

        queue.sort(
            key=lambda q: (
                q[0].recommended_semester is None,
                q[0].recommended_semester or 0,
                q[1],
                q[0].name,
                q[0].id,
            )
        )
        for s, _, preferred, earlier in queue:
            self.choose(s, preferred, earlier)

    def choose(self, s: PlanSubject, preferred: list[date], earlier: list[date]) -> None:
        free = [d for d in earlier + preferred if _month(d) not in self.taken]
        if not free:
            self.conflict(
                s,
                "no_feasible_sitting",
                "Kein freier Termin: Jeder mögliche Termin liegt in einem Monat, "
                "in dem schon eine Prüfung ansteht.",
            )
            return
        checks = {d: self.try_sitting(s.id, d) for d in free}

        def good(d: date) -> bool:
            fits, harmed = checks[d]
            return fits and not harmed

        in_window = [d for d in free if d in preferred and good(d)]
        before_window = [d for d in free if d in earlier and good(d)]
        if in_window or before_window:
            self.schedule(s, in_window[0] if in_window else before_window[-1])
            return
        harmless = [d for d in free if not checks[d][1]]
        if harmless:
            choice = harmless[-1]
            self.conflict(
                s,
                "no_feasible_sitting",
                "Beim aktuellen Tempo reicht die Zeit für keinen Termin. "
                f"Vorgeschlagen ist der {_de(choice)}.",
            )
            self.schedule(s, choice)
            return
        displaced = list(dict.fromkeys(i for d in free for i in checks[d][1]))
        names = ", ".join(self.by_id[i].name for i in displaced)
        self.conflict(
            s,
            "no_feasible_sitting",
            f"Kein Termin passt: Jeder freie Termin würde die Vorbereitung auf {names} "
            "zu knapp machen.",
        )

    def finish(self) -> Plan:
        slots = self.layout(self.scheduled)
        for slot in slots:
            entry = self.entries[slot.subject_id]
            entry.study_from, entry.study_until = slot.study_from, slot.study_until
            entry.feasible = slot.feasible
        for entry in self.entries.values():
            if entry.state in ("open", "planned") and entry.sitting is not None:
                entry.register_by = entry.sitting - timedelta(days=REGISTRATION_DAYS)
        return Plan(
            entries=[self.entries[s.id] for s in self.subjects],
            order=[slot.subject_id for slot in slots],
            conflicts=self.conflicts,
        )


def plan(
    subjects: list[PlanSubject], semesters: dict[str, date], today: date, pace_per_day: float
) -> Plan:
    if pace_per_day <= 0:
        raise ValueError("pace_per_day must be positive")
    planner = _Planner(subjects, semesters, today, pace_per_day)
    planned, open_ = planner.fix_attempts()
    open_ += planner.keep_planned(planned)
    planner.propose(open_)
    planner.report_lapsed()
    return planner.finish()
