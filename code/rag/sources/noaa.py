"""NOAA Climate.gov. robots.txt가 /search를 막아, 사이트맵의 Q&A·Understanding Climate 목록에서 고른다."""
import json
import re
from urllib.parse import unquote, urlparse

from config import DATA_DIR
from rag import web
from rag.html_text import html_to_text
from rag.sources import Candidate, Doc

SITEMAPS = ["https://www.climate.gov/sitemap.xml?page=1", "https://www.climate.gov/sitemap.xml?page=2"]
SECTIONS = ("/news-features/climate-qa/", "/news-features/understanding-climate/")
CATALOG_PATH = DATA_DIR / "raw" / "noaa_catalog.json"


def _title(url: str) -> str:
    return unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]).replace("-", " ")


def catalog() -> list[str]:
    """두 구역의 글 URL 목록. data/raw/noaa_catalog.json을 지우면 새로 만든다."""
    if CATALOG_PATH.exists():
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    urls = [u for page in SITEMAPS for u in re.findall(r"<loc>([^<]+)</loc>", web.get(page).text)
            if urlparse(u).path.startswith(SECTIONS)]
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(urls, ensure_ascii=False), encoding="utf-8")
    return urls


def search(query: str, limit: int = 5) -> list[Candidate]:
    """검색어 단어와 제목 단어가 겹치는 개수 순. 하나도 겹치지 않으면 뺀다."""
    words = set(query.lower().split())
    scored = [(len(words & set(_title(u).split())), u) for u in catalog()]
    best = sorted((s for s in scored if s[0] > 0), key=lambda s: -s[0])[:limit]
    return [Candidate("noaa", "noaa-" + _title(u).replace(" ", "-"), _title(u), _title(u), u) for _, u in best]


def fetch(c: Candidate) -> Doc | None:
    text = html_to_text(web.get(c.url).text)
    return Doc("noaa", c.doc_id, c.title, c.url, text) if text else None
