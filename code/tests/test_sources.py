import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rag.sources import nasa, noaa, wiki
from tests.fakes import FakeResponse


def respond(*bodies):
    """web.get 대체: 호출마다 bodies를 차례로 FakeResponse(200)로 돌려준다."""
    queue = [b if isinstance(b, str) else json.dumps(b) for b in bodies]
    return lambda url, params=None: FakeResponse(200, queue.pop(0))


class WikiTest(unittest.TestCase):
    def test_wiki_search_strips_tags(self):
        body = {"query": {"search": [{"pageid": 123, "title": "열대야",
                                      "snippet": '<span class="searchmatch">열대야</span> 현상'}]}}
        with patch("rag.web.get", respond(body)):
            [c] = wiki.search("열대야")
        self.assertEqual((c.source, c.doc_id, c.title, c.summary), ("wiki", "wiki-123", "열대야", "열대야 현상"))
        self.assertEqual(c.url, "https://ko.wikipedia.org/wiki/열대야")

    def test_wiki_fetch_missing_returns_none(self):
        body = {"query": {"pages": [{"title": "없는문서", "missing": True}]}}
        with patch("rag.web.get", respond(body)):
            self.assertIsNone(wiki.fetch(wiki.Candidate("wiki", "wiki-0", "없는문서", "", "")))


class NasaTest(unittest.TestCase):
    def test_nasa_search_maps_fields(self):
        body = [{"id": 973897, "title": "What Is the Greenhouse Effect?",
                 "url": "https://science.nasa.gov/kids/earth/what-is-the-greenhouse-effect/",
                 "_links": {"self": [{"href": "https://science.nasa.gov/wp-json/wp/v2/topic/973897"}]}}]
        with patch("rag.web.get", respond(body)):
            [c] = nasa.search("greenhouse effect")
        self.assertEqual((c.source, c.doc_id, c.title), ("nasa", "nasa-973897", "What Is the Greenhouse Effect?"))
        self.assertEqual(c.url, "https://science.nasa.gov/kids/earth/what-is-the-greenhouse-effect/")

        page = {"content": {"rendered": "<p>Gases trap heat.</p><script>x</script>"}}
        with patch("rag.web.get", respond(page)):
            doc = nasa.fetch(c)
        self.assertEqual((doc.doc_id, doc.text), ("nasa-973897", "Gases trap heat."))


class NoaaTest(unittest.TestCase):
    def test_noaa_catalog_filters_and_ranks(self):
        base = "https://www.climate.gov/news-features"
        page1 = f"<urlset><url><loc>{base}/features/unrelated-story</loc></url></urlset>"
        page2 = (f"<urlset><url><loc>{base}/climate-qa/do-solar-storms-cause-heat-waves-earth</loc></url>"
                 f"<url><loc>{base}/understanding-climate/climate-change-global-sea-level</loc></url></urlset>")
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(noaa, "CATALOG_PATH", Path(tmp) / "noaa_catalog.json"), \
                patch("rag.web.get", respond(page1, page2)):
            self.assertEqual(len(noaa.catalog()), 2)
            hits = noaa.search("solar storms heat waves")
        self.assertEqual(hits[0].doc_id, "noaa-do-solar-storms-cause-heat-waves-earth")
        self.assertEqual(hits[0].title, "do solar storms cause heat waves earth")
        self.assertEqual(len(hits), 1)  # 겹치는 단어가 없는 해수면 글은 빠진다


if __name__ == "__main__":
    unittest.main()
