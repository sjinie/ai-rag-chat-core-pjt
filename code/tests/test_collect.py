import tempfile
import unittest
from unittest.mock import patch

from langchain_core.embeddings import DeterministicFakeEmbedding

from config import CONFIG
from domain.prompts import Plan
from rag.cache import connect_cache
from rag.collect import collect, search_docs
from rag.sources import Candidate, Doc
from rag.store import get_store
from tests.fakes import FakeLLM


class FakeAdapter:
    def __init__(self, source: str, docs: dict[str, str], fail: bool = False):
        self.source, self.docs, self.fail, self.searches = source, docs, fail, 0

    def search(self, query, limit=5):
        self.searches += 1
        if self.fail:
            raise RuntimeError("science.nasa.gov 연결 실패: ConnectionError")
        return [Candidate(self.source, doc_id, f"제목 {doc_id}", "요약", f"https://x/{doc_id}") for doc_id in self.docs]

    def fetch(self, c):
        return Doc(self.source, c.doc_id, c.title, c.url, self.docs[c.doc_id])


def plan(**queries) -> Plan:
    return Plan(False, {"wiki": [], "nasa": [], "noaa": [], "ipcc": [], "kma_terms": [], **queries})


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = get_store("climate_docs", DeterministicFakeEmbedding(size=64), self.tmp.name)
        self.cache = connect_cache(":memory:")
        self.steps = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_collect(self, adapters, p, llm):
        with patch("rag.collect.ADAPTERS", adapters):
            return collect(llm, self.store, self.cache, "108", "열대야가 뭐야?", p, self.steps.append)

    def test_collect_indexes_selected_with_ids(self):
        wiki = FakeAdapter("wiki", {"wiki-1": "열대야는 밤에도 더운 현상이다.", "wiki-2": "관련 없는 영화 문서"})
        titles = self.run_collect({"wiki": wiki}, plan(wiki=["열대야"]), FakeLLM(['{"selected": [1]}']))
        self.assertEqual(titles, ["제목 wiki-1"])
        got = self.store.get(include=["metadatas"])
        self.assertEqual(got["ids"], ["108:wiki-1:0"])
        meta = got["metadatas"][0]
        self.assertEqual((meta["source_type"], meta["stn"], meta["query"]), ("wiki", "108", "열대야"))
        self.assertIn("collected_at", meta)

    def test_collect_skips_cached_query(self):
        wiki = FakeAdapter("wiki", {"wiki-1": "열대야는 밤에도 더운 현상이다."})
        self.run_collect({"wiki": wiki}, plan(wiki=["열대야"]), FakeLLM(['{"selected": [1]}']))
        self.run_collect({"wiki": wiki}, plan(wiki=["열대야"]), FakeLLM([]))
        self.assertEqual(wiki.searches, 1)  # 두 번째는 검색도 LLM 호출도 하지 않는다

    def test_collect_skips_failed_source(self):
        wiki = FakeAdapter("wiki", {"wiki-1": "열대야는 밤에도 더운 현상이다."})
        nasa = FakeAdapter("nasa", {}, fail=True)
        titles = self.run_collect({"wiki": wiki, "nasa": nasa}, plan(wiki=["열대야"], nasa=["tropical night"]),
                                  FakeLLM(['{"selected": [1]}']))
        self.assertEqual(titles, ["제목 wiki-1"])
        self.assertTrue(any("NASA" in s for s in self.steps))
        self.assertFalse(any("science.nasa.gov" in s or "?" in s for s in self.steps))  # 주소는 화면에 내지 않는다

    def test_chunk_size_from_config(self):
        long_text = "기상 현상 설명 문장입니다. " * 160  # 약 2,400자
        counts = []
        for size, doc_id in ((1000, "wiki-1"), (500, "wiki-2")):
            wiki = FakeAdapter("wiki", {doc_id: long_text})
            with patch.dict(CONFIG["rag"], {"chunk_size": size, "chunk_overlap": 100}):
                self.run_collect({"wiki": wiki}, plan(wiki=[f"검색어 {size}"]), FakeLLM(['{"selected": [1]}']))
            counts.append(len(self.store.get(where={"doc_id": doc_id})["ids"]))
        self.assertGreater(counts[1], counts[0])


class SearchDocsTest(unittest.TestCase):
    def test_search_scoped_to_station_or_common(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = get_store("climate_docs", DeterministicFakeEmbedding(size=64), tmp)
            store.add_texts(["열대야 설명", "열대야 설명 강릉판", "열대야: 특보 기준"],
                            ids=["108:wiki-1:0", "105:wiki-1:0", "common:kma_terms:x:0"],
                            metadatas=[{"source_type": "wiki", "stn": "108", "doc_id": "wiki-1"},
                                       {"source_type": "wiki", "stn": "105", "doc_id": "wiki-1"},
                                       {"source_type": "kma_terms", "stn": "common", "doc_id": "kma_terms-x"}])
            for search_type in ("similarity", "mmr"):
                with patch.dict(CONFIG["rag"], {"search_type": search_type}):
                    ids = [d.id for d in search_docs(store, "108", plan(wiki=["열대야"], kma_terms=["열대야"]))]
                self.assertEqual(sorted(ids), ["108:wiki-1:0", "common:kma_terms:x:0"], search_type)


if __name__ == "__main__":
    unittest.main()
