from bnetza_bk6_scraper.parse import parse_candidate_documents, parse_followable_links

BASE = "https://www.bundesnetzagentur.de"
GPKE_PAGE = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/gpke_node.html"

# One PDF under a proceeding (has Aktenzeichen), one PDF without (PID), one HTML sub-link.
PAGE_HTML = (
    "<html><head><base href='/'/></head><body><div id='content'>"
    "<a href='/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/BK6-24-174/Beschluss/"
    "BK6-24-174_GPKE_Teil1_Lesefassung.pdf'>GPKE Teil 1 (Lesefassung)</a>"
    "<a href='/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/835_mitteilungen_datenformate/"
    "Mitteilung_48/Anlagen/PID_3_2.pdf?__blob=publicationFile&v=1'>Prüfidentifikatoren</a>"
    "<a href='/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/detail.html'>Mehr</a>"
    "</div></body></html>"
)


def test_parse_candidate_documents_extracts_pdfs_with_context() -> None:
    cands = parse_candidate_documents(PAGE_HTML, page_url=GPKE_PAGE)
    by_name = {c.filename: c for c in cands}
    assert set(by_name) == {"BK6-24-174_GPKE_Teil1_Lesefassung.pdf", "PID_3_2.pdf"}

    gpke = by_name["BK6-24-174_GPKE_Teil1_Lesefassung.pdf"]
    assert gpke.aktenzeichen == "BK6-24-174"
    assert gpke.doc_type == "GPKE_Teil1_Lesefassung"
    assert gpke.title == "GPKE Teil 1 (Lesefassung)"
    assert gpke.found_on == GPKE_PAGE
    assert gpke.source_url.startswith(f"{BASE}/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/")

    pid = by_name["PID_3_2.pdf"]
    assert pid.aktenzeichen is None
    assert pid.doc_type is None
    assert "__blob=publicationFile" in pid.source_url


def test_parse_followable_links_returns_absolute_html_links() -> None:
    links = parse_followable_links(PAGE_HTML, page_url=GPKE_PAGE)
    assert f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/detail.html" in links
    # PDF anchors are not followable HTML links
    assert not any(link.endswith(".pdf") for link in links)


def test_parse_followable_links_deduplicates() -> None:
    html = "<html><body>" "<a href='/a/x.html'>x</a><a href='/a/x.html'>x again</a>" "</body></html>"
    links = parse_followable_links(html, page_url=f"{BASE}/a/index.html")
    assert links.count(f"{BASE}/a/x.html") == 1
