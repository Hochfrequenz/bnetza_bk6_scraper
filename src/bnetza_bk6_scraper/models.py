"""Pydantic models describing a BK6 proceeding and its documents."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Document(BaseModel):
    """A single downloadable document (PDF) belonging to a proceeding."""

    title: str
    doc_type: str
    source_url: str
    filename: str


class ProceedingPage(BaseModel):
    """One phase page (e.g. konsultation, festlegungsverfahren) of a proceeding."""

    phase: str
    source_url: str


class Proceeding(BaseModel):
    """A BK6 proceeding, keyed by Aktenzeichen, aggregating all its phase pages."""

    aktenzeichen: str
    year: int
    title: str
    stand: date | None = None
    status: str | None = None
    deadline: date | None = None
    pages: list[ProceedingPage] = []
    documents: list[Document] = []
