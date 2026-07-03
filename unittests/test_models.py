from datetime import date

from bnetza_bk6_scraper.models import Document, Proceeding


def test_document_minimal():
    doc = Document(
        title="Konsultationsdokument",
        doc_type="konsultationsdokument",
        source_url="https://www.bundesnetzagentur.de/.../BK6-23-241_konsultationsdokument.pdf",
        filename="BK6-23-241_konsultationsdokument.pdf",
    )
    assert doc.filename.endswith(".pdf")


def test_proceeding_roundtrips_to_json():
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
