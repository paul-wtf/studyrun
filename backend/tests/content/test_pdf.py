import pytest
from pdfs import build_pdf, page_count

from studyrun.content.pdf import BookletError, extract_slice, split_booklet


def ranges(slices):
    return [(s.first_page, s.last_page) for s in slices]


def test_outline_chapters():
    data = build_pdf(12, outline=[("Grundlagen", 1), ("Vertiefung", 4), ("Anwendung", 9)])
    slices = split_booklet(data, max_pages=40, window=15)
    assert ranges(slices) == [(1, 3), (4, 8), (9, 12)]
    assert [s.title for s in slices] == ["Grundlagen", "Vertiefung", "Anwendung"]
    assert [page_count(s.pdf) for s in slices] == [3, 5, 4]


def test_preamble_joins_first_chapter():
    data = build_pdf(10, outline=[("Erstes", 3), ("Zweites", 7)])
    slices = split_booklet(data, max_pages=40, window=15)
    assert ranges(slices) == [(1, 6), (7, 10)]
    assert slices[0].title == "Erstes"


def test_no_outline_windows():
    slices = split_booklet(build_pdf(31), max_pages=40, window=15)
    assert ranges(slices) == [(1, 15), (16, 30), (31, 31)]
    assert [s.title for s in slices] == ["Seiten 1–15", "Seiten 16–30", "Seiten 31–31"]


def test_long_chapter_split():
    data = build_pdf(50, outline=[("Kurz", 1), ("Lang", 6)])
    slices = split_booklet(data, max_pages=20, window=15)
    assert ranges(slices) == [(1, 5), (6, 20), (21, 35), (36, 50)]
    assert [s.title for s in slices] == ["Kurz", "Lang (Teil 1)", "Lang (Teil 2)", "Lang (Teil 3)"]


def test_non_advancing_outline_entries_are_skipped():
    data = build_pdf(10, outline=[("A", 1), ("B", 1), ("C", 5), ("D", 3), ("E", 8)])
    slices = split_booklet(data, max_pages=40, window=15)
    assert ranges(slices) == [(1, 4), (5, 7), (8, 10)]
    assert [s.title for s in slices] == ["A", "C", "E"]


def test_slice_page_count():
    data = build_pdf(12)
    assert page_count(extract_slice(data, 4, 8)) == 5
    assert page_count(extract_slice(data, 12, 12)) == 1


def test_rejects_non_pdf():
    with pytest.raises(BookletError) as error:
        split_booklet(b"das ist kein pdf", max_pages=40, window=15)
    assert error.value.message_de == "Die Datei ist kein lesbares PDF."


def test_rejects_encrypted():
    with pytest.raises(BookletError) as error:
        split_booklet(build_pdf(5, password="geheim"), max_pages=40, window=15)
    assert "verschlüsselt" in error.value.message_de


def test_rejects_no_text_layer():
    with pytest.raises(BookletError) as error:
        split_booklet(build_pdf(5, text=False), max_pages=40, window=15)
    assert "Textebene" in error.value.message_de
