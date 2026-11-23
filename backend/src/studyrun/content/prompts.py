from __future__ import annotations

import json
from collections.abc import Sequence

from studyrun.content.schemas import ItemUnion

ITEMS_PER_PAGE = 2
MIN_ITEMS = 8
MAX_ITEMS = 40

GENERATION_SYSTEM = """\
Du erstellst Lernmaterial aus einem Kursheft für einen berufsbegleitend Studierenden. \
Er liest das Heft vorher nicht; was du schreibst, ist sein erster Kontakt mit dem Stoff. \
Schreibe alles auf Deutsch.

Regeln:
- Alles stammt aus den angehängten Seiten. Kein Allgemeinwissen, keine Fakten, Zahlen oder \
Beispiele, die dort nicht stehen.
- Jede Frage nennt in source_page die Seite, auf der ihre Antwort steht.
- Fragen prüfen Verständnis und Anwendung des Stoffs, nicht Seitenzahlen, Abbildungsnummern, \
Layout oder den Wortlaut von Überschriften.
- Verteile die Fragen über alle Seiten und alle wichtigen Themen des Kapitels. Keine zwei \
Fragen fragen dasselbe ab.
- explanation erklärt in ein bis drei Sätzen, warum die Lösung stimmt.

Fragetypen (Feld kind):
- mc: prompt ist die Frage, options sind 3 bis 5 Antworten, von denen genau eine richtig ist, \
answer_index ist ihre Position (ab 0). Falsche Antworten sind plausibel, aber nach dem Heft \
eindeutig falsch. Keine Optionen wie „alle genannten“ oder „keine davon“, keine doppelten \
Optionen.
- true_false: statement ist eine Aussage, die nach dem Heft eindeutig wahr oder falsch ist; \
correct sagt, welches von beiden. Etwa die Hälfte der Aussagen ist falsch.
- cloze: text ist ein Satz mit genau einer Lücke, geschrieben als drei Unterstriche ___. \
answers nennt alle Lösungen, die das Heft als richtig trägt (Synonyme, Schreibweisen).
- free: prompt verlangt eine kurze freie Antwort (eine Definition, eine Aufzählung, ein \
„Warum“). model_answer ist eine vollständige Musterantwort, rubric nennt 1 bis 5 Punkte, \
die eine gute Antwort enthalten muss. source_excerpt ist ein wörtliches Zitat aus dem Heft \
(höchstens 600 Zeichen), das die Antwort trägt.

Außerdem:
- summary ist eine Zusammenfassungskarte des Kapitels in 4 bis 8 Sätzen.
- concepts sind die zentralen Begriffe des Kapitels, jeder mit einer kurzen Erklärung \
nach dem Heft.
"""

VERIFICATION_SYSTEM = """\
Du prüfst Lernfragen, die aus einem Kursheft erzeugt wurden, gegen die angehängten Seiten \
dieses Hefts. Sei streng: Eine Frage, die du nicht sicher bestätigen kannst, fällt durch.

Gib für jede Frage genau ein Urteil mit ihrem index zurück:
- correct ist wahr, wenn die angegebene Lösung nach dem Heft richtig und die Frage eindeutig \
ist. Bei mc ist genau die Option an answer_index richtig und alle anderen falsch; bei \
true_false stimmt correct; bei cloze passt jede Lösung in answers in die Lücke; bei free \
erfüllt model_answer alle Punkte der rubric.
- in_source ist wahr, wenn Frage und Lösung auf den angehängten Seiten stehen, und zwar auf \
der Seite source_page oder ab ihr. Bei free muss source_excerpt wörtlich im Heft stehen.
- note begründet das Urteil in einem Satz auf Deutsch, vor allem bei einer Ablehnung.
"""


def item_count(first_page: int, last_page: int) -> int:
    pages = last_page - first_page + 1
    return max(MIN_ITEMS, min(MAX_ITEMS, ITEMS_PER_PAGE * pages))


def _pages(first_page: int, last_page: int) -> str:
    return (
        f"Das angehängte Dokument enthält die Seiten {first_page} bis {last_page} des Kurshefts. "
        f"Seine erste Seite ist Seite {first_page} des Hefts, die zweite Seite {first_page + 1} "
        "und so weiter. Seitenangaben beziehen sich auf diese Zählung, nicht auf die "
        "gedruckten Seitenzahlen."
    )


def generation_request(title: str, first_page: int, last_page: int) -> str:
    total = item_count(first_page, last_page)
    true_false = round(total * 0.15)
    cloze = round(total * 0.15)
    mc = round(total * 0.5)
    free = total - mc - true_false - cloze
    return (
        f"Kapitel: {title}\n\n{_pages(first_page, last_page)} source_page liegt also "
        f"zwischen {first_page} und {last_page}.\n\n"
        f"Erstelle etwa {total} Fragen: etwa {mc} mc, {true_false} true_false, {cloze} cloze "
        f"und {free} free."
    )


def verification_request(first_page: int, last_page: int, items: Sequence[ItemUnion]) -> str:
    numbered = [
        {"index": n, **item.model_dump(mode="json")} for n, item in enumerate(items, start=1)
    ]
    return (
        f"{_pages(first_page, last_page)}\n\n"
        f"Prüfe diese {len(items)} Fragen:\n\n"
        f"{json.dumps(numbered, ensure_ascii=False, indent=2)}"
    )
