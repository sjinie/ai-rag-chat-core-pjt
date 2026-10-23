"""한국어 위키백과. references/streamlit_lab/step8_wiki_api.py의 검색·본문 호출과 같은 파라미터."""
import html
import re

from rag import web
from rag.sources import Candidate, Doc

API_URL = "https://ko.wikipedia.org/w/api.php"


def search(query: str, limit: int = 5) -> list[Candidate]:
    data = web.get(API_URL, {"action": "query", "list": "search", "srsearch": query, "srlimit": limit,
                             "format": "json", "formatversion": 2}).json()
    return [Candidate("wiki", f"wiki-{item['pageid']}", item["title"],
                      html.unescape(re.sub(r"<[^>]+>", "", item.get("snippet", ""))),
                      f"https://ko.wikipedia.org/wiki/{item['title'].replace(' ', '_')}")
            for item in data["query"]["search"]]


def fetch(c: Candidate) -> Doc | None:
    data = web.get(API_URL, {"action": "query", "prop": "extracts|info", "titles": c.title, "explaintext": 1,
                             "inprop": "url", "redirects": 1, "format": "json", "formatversion": 2}).json()
    page = data["query"]["pages"][0]
    if page.get("missing"):
        return None
    return Doc("wiki", f"wiki-{page['pageid']}", page["title"], page["fullurl"], page.get("extract", ""))
