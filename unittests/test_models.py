from datetime import date

import bnetza_bk6_scraper as pkg
from bnetza_bk6_scraper.models import CandidateDocument, Document, Proceeding


def test_document_minimal() -> None:
    doc = Document(
        title="Konsultationsdokument",
        doc_type="konsultationsdokument",
        source_url="https://www.bundesnetzagentur.de/.../BK6-23-241_konsultationsdokument.pdf",
        filename="BK6-23-241_konsultationsdokument.pdf",
    )
    assert doc.filename.endswith(".pdf")


def test_proceeding_roundtrips_to_json() -> None:
    p = Proceeding(
        aktenzeichen="BK6-23-241",
        year=2023,
        title="Fortentwicklung des sog. 'Redispatch 2.0'",
        stand=date(2024, 9, 26),
        status="Konsultation",
        deadline=date(2024, 11, 4),
        pages=[],
        documents=[],
    )
    dumped = p.model_dump(mode="json")
    assert dumped["aktenzeichen"] == "BK6-23-241"
    assert dumped["stand"] == "2024-09-26"
    assert Proceeding.model_validate(dumped) == p


def test_candidate_document_defaults() -> None:
    c = CandidateDocument(
        source_url="https://x/DE/Beschlusskammern/BK06/a/PID_1.pdf",
        filename="PID_1.pdf",
        title="Anwendungsübersicht der Prüfidentifikatoren",
        found_on="https://x/DE/Beschlusskammern/BK06/a/index.html",
    )
    assert c.aktenzeichen is None
    assert c.doc_type is None


def test_candidate_document_with_aktenzeichen() -> None:
    c = CandidateDocument(
        source_url="https://x/BK6-GZ/2024/BK6-24-174/Beschluss/BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        filename="BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        title="GPKE Teil 1 (Lesefassung)",
        found_on="https://x/gpke_node.html",
        aktenzeichen="BK6-24-174",
        doc_type="GPKE_Teil1_Lesefassung",
    )
    assert c.aktenzeichen == "BK6-24-174"
    assert c.doc_type == "GPKE_Teil1_Lesefassung"


def test_candidate_document_is_publicly_exported() -> None:
    assert "CandidateDocument" in pkg.__all__
    assert pkg.CandidateDocument is not None
