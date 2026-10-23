"""NASA science.nasa.gov. WordPress 검색 API로 후보를 찾고, 글 API로 본문을 받는다."""
from rag import web
from rag.html_text import html_to_text
from rag.sources import Candidate, Doc

SEARCH_URL = "https://science.nasa.gov/wp-json/wp/v2/search"
_self_href: dict[str, str] = {}  # doc_id → 본문 API 주소 (검색 결과에만 있다)


def search(query: str, limit: int = 5) -> list[Candidate]:
    results = []
    for item in web.get(SEARCH_URL, {"search": query, "per_page": limit}).json():
        doc_id = f"nasa-{item['id']}"
        _self_href[doc_id] = item["_links"]["self"][0]["href"]
        results.append(Candidate("nasa", doc_id, item["title"], item["title"], item["url"]))
    return results


def fetch(c: Candidate) -> Doc | None:
    href = _self_href.get(c.doc_id)
    if not href:
        return None
    text = html_to_text(web.get(href).json().get("content", {}).get("rendered", ""))
    return Doc("nasa", c.doc_id, c.title, c.url, text) if text else None
