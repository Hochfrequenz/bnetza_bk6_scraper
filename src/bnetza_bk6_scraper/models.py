"""Pydantic models describing a BK6 proceeding and its documents."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Document(BaseModel):
    """A single downloadable document (PDF) belonging to a proceeding."""

    title: str
    """Human-readable link text, e.g. ``"Konsultationsdokument"``."""

    doc_type: str
    """Document-type slug parsed from the filename after the Aktenzeichen prefix.

    Deliberately a free-form ``str`` and not a ``Literal``: BK6 proceedings name their
    documents ad hoc (e.g. ``"konsultationsdokument"``, ``"beschluss"``, ``"anlage_bilarem"``,
    ``"bilarem"``), so a closed ``Literal`` would reject unseen types and drop documents.
    """

    source_url: str
    """Absolute URL the PDF was downloaded from, e.g. ``"https://www.bundesnetzagentur.de/.../BK6-23-241_konsultationsdokument.pdf?__blob=publicationFile&v=3"``."""

    filename: str
    """Bare filename written into the mirror, e.g. ``"BK6-23-241_konsultationsdokument.pdf"``."""


class ProceedingPage(BaseModel):
    """One phase page (e.g. konsultation, festlegungsverfahren) of a proceeding."""

    phase: str
    """Phase slug taken from the page URL, e.g. ``"konsultation"``, ``"festlegungsverfahren"``, ``"beschluss"``."""

    source_url: str
    """Absolute URL of this phase page."""


class Proceeding(BaseModel):
    """A BK6 proceeding, keyed by Aktenzeichen, aggregating all its phase pages."""

    aktenzeichen: str
    """The BK6 file reference, e.g. ``"BK6-23-241"``."""

    year: int
    """Four-digit year derived from the Aktenzeichen, e.g. ``2023``."""

    title: str
    """Proceeding title (the ``<h2>`` of the page), e.g. ``"Fortentwicklung des sog. „Redispatch 2.0“"``."""
    stand: date | None = None
    """The page's *"Stand:"* revision date, parsed from the German ``dd.mm.yyyy`` format
    into a :class:`datetime.date` (e.g. ``Stand: 26.09.2024`` -> ``date(2024, 9, 26)``).
    ``None`` when the page carries no *Stand* marker."""

    status: str | None = None
    """Procedural phase label derived from the page URL, e.g. ``"Konsultation"``, ``"Beschluss"``."""

    deadline: date | None = None
    """Submission deadline (*"Frist zur Stellungnahme"*) for the consultation, as a German
    ``dd.mm.yyyy`` date. **Inclusive**: statements are accepted up to and including this day.
    Best-effort — ``None`` when no deadline is confidently found on the page."""

    pages: list[ProceedingPage] = []
    """All phase pages discovered for this Aktenzeichen."""

    documents: list[Document] = []
    """All PDFs linked from the proceeding's pages."""
