import io

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

FILLER = "Dies ist erfundener Beispieltext fuer einen Testkurs ohne echten Inhalt. " * 3


def _text_stream(text: str) -> DecodedStreamObject:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 40 700 Td ({escaped}) Tj ET".encode("latin-1"))
    return stream


def build_pdf(
    pages: int,
    *,
    outline: list[tuple[str, int]] | None = None,
    text: bool = True,
    password: str | None = None,
) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    for number in range(1, pages + 1):
        page = writer.add_blank_page(width=595, height=842)
        if text:
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
            )
            content = _text_stream(f"Seite {number}. {FILLER}")
            page[NameObject("/Contents")] = writer._add_object(content)
    for title, page_number in outline or []:
        writer.add_outline_item(title=title, page_number=page_number - 1)
    if password is not None:
        writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def page_count(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)
