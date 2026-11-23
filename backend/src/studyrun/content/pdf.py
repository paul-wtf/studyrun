import io
from dataclasses import dataclass

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

MIN_TEXT_CHARS = 200
TEXT_PROBE_PAGES = 5


class BookletError(Exception):
    def __init__(self, message_de: str) -> None:
        super().__init__(message_de)
        self.message_de = message_de


@dataclass(frozen=True)
class ChapterSlice:
    title: str
    first_page: int
    last_page: int
    pdf: bytes


def _open(data: bytes) -> PdfReader:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise BookletError(
                "Das PDF ist verschlüsselt. Bitte eine ungeschützte Fassung hochladen."
            )
        if len(reader.pages) == 0:
            raise BookletError("Die Datei ist kein lesbares PDF.")
        return reader
    except BookletError:
        raise
    except (PyPdfError, ValueError, OSError, KeyError, TypeError, RecursionError):
        raise BookletError("Die Datei ist kein lesbares PDF.") from None


def _check_text_layer(reader: PdfReader) -> None:
    chars = 0
    try:
        for page in list(reader.pages)[:TEXT_PROBE_PAGES]:
            chars += len("".join((page.extract_text() or "").split()))
    except (PyPdfError, ValueError, KeyError, TypeError, RecursionError):
        raise BookletError("Die Datei ist kein lesbares PDF.") from None
    if chars < MIN_TEXT_CHARS:
        raise BookletError(
            "Das PDF hat keine Textebene (z. B. ein Scan) und kann nicht verarbeitet werden."
        )


def _outline_starts(reader: PdfReader) -> list[tuple[str, int]]:
    try:
        entries = reader.outline
    except (PyPdfError, ValueError, KeyError, TypeError, RecursionError):
        return []
    total = len(reader.pages)
    starts: list[tuple[str, int]] = []
    for entry in entries:
        if isinstance(entry, list):
            continue
        try:
            page = reader.get_destination_page_number(entry)
            title = str(entry.title).strip()
        except (PyPdfError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if page is None or page < 0 or page >= total:
            continue
        first = page + 1
        if starts and first <= starts[-1][1]:
            continue
        starts.append((title or f"Seite {first}", first))
    return starts


def _windows(first: int, last: int, window: int) -> list[tuple[int, int]]:
    return [(a, min(a + window - 1, last)) for a in range(first, last + 1, window)]


def extract_slice(data: bytes, first_page: int, last_page: int) -> bytes:
    reader = _open(data)
    writer = PdfWriter()
    for index in range(first_page - 1, last_page):
        writer.add_page(reader.pages[index])
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def split_booklet(data: bytes, *, max_pages: int, window: int) -> list[ChapterSlice]:
    reader = _open(data)
    _check_text_layer(reader)
    total = len(reader.pages)

    starts = _outline_starts(reader)
    plan: list[tuple[str | None, int, int]] = []
    if starts:
        starts[0] = (starts[0][0], 1)
        for i, (name, first) in enumerate(starts):
            last = starts[i + 1][1] - 1 if i + 1 < len(starts) else total
            plan.append((name, first, last))
    else:
        plan = [(None, 1, total)]

    slices: list[ChapterSlice] = []
    for title, first, last in plan:
        parts: list[tuple[str, int, int]]
        if title is None:
            parts = [(f"Seiten {a}–{b}", a, b) for a, b in _windows(first, last, window)]
        elif last - first + 1 > max_pages:
            parts = [
                (f"{title} (Teil {n})", a, b)
                for n, (a, b) in enumerate(_windows(first, last, window), start=1)
            ]
        else:
            parts = [(title, first, last)]
        for part_title, a, b in parts:
            slices.append(ChapterSlice(part_title, a, b, extract_slice(data, a, b)))
    return slices
