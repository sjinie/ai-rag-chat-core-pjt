import tempfile
import unittest

from langchain_core.embeddings import DeterministicFakeEmbedding

from domain.cases import Case, case_candidates, select_cases
from domain.weather_db import connect, save_baselines, save_obs
from rag.cache import connect_cache, get_selection
from rag.store import get_store
from tests.fakes import FakeLLM

OBS = {"ta_avg": 12.0, "ta_max": 17.0, "ta_min": 8.0, "hm_avg": 60.0, "ws_avg": 2.0, "rn_day": 0.0}
BASE = {(10, d): {"ta_avg": 14.0, "ta_max": 19.0, "ta_min": 9.0, "hm_avg": 63.0, "ws_avg": 2.0, "rn_day": 1.0,
                  "ta_avg_sd": 2.0, "ta_max_sd": 2.0, "ta_min_sd": 2.0, "hm_avg_sd": 10.0, "ws_avg_sd": 0.5,
                  "rn_day_sd": 3.0, "n": 150, "years": 10} for d in range(1, 32)}


class CasesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows는 Chroma 파일이 열려 있어 지울 수 없다
        self.store = get_store("forecast_texts", DeterministicFakeEmbedding(size=64), self.tmp.name)
        texts = {("156", "20241101"): "광주 아침까지 비", ("156", "20241102"): "광주 맑음",
                 ("156", "20241103"): "광주 오후 비", ("109", "20241101"): "수도권 아침까지 비",
                 ("109", "20241102"): "수도권 맑음", ("109", "20241103"): "수도권 흐림"}
        self.store.add_texts(list(texts.values()), ids=[f"fcst:{o}:{d}" for o, d in texts],
                             metadatas=[{"office": o, "date": d, "title": f"{o} 개황 {d}", "url": "u"} for o, d in texts])
        self.db = connect(":memory:")
        save_obs(self.db, [{"stn": "156", "date": d, **OBS} for d in ("20241102", "20241103")])  # 11월 1일 관측은 없음
        save_baselines(self.db, {"156": {(11, d): v for (_, d), v in BASE.items() if d <= 30}})
        self.cache = connect_cache(":memory:")

    def tearDown(self):
        self.tmp.cleanup()

    def test_candidates_same_office_only(self):
        # 질문 문장이 109 개황과 똑같아도(필터가 없으면 1순위) 156 지방청 개황만 나와야 한다
        found = case_candidates(self.store, self.db, "156", "156", "수도권 아침까지 비", n=3)
        self.assertEqual(sorted(c.doc_id for c in found), ["fcst:156:20241102", "fcst:156:20241103"])

    def test_candidates_skip_missing_obs(self):
        # 질문 문장과 똑같은 11월 1일 개황이 1순위지만 그날 관측이 없어 빠지고 나머지 두 날로 채운다
        found = case_candidates(self.store, self.db, "156", "156", "광주 아침까지 비", n=2)
        self.assertEqual(sorted(c.date for c in found), ["20241102", "20241103"])
        self.assertIn("최근 10년 기준값보다", found[0].sentence)

    def test_candidates_exclude_dates(self):
        found = case_candidates(self.store, self.db, "156", "156", "광주 맑음", n=3, exclude_dates=frozenset({"20241102"}))
        self.assertEqual([c.date for c in found], ["20241103"])


def case(n: int) -> Case:
    return Case(f"fcst:156:2024110{n}", f"2024110{n}", f"개황 {n}", "u", "오늘 문단", OBS, f"문장 {n}")


class SelectCasesTest(unittest.TestCase):
    def setUp(self):
        self.cache = connect_cache(":memory:")
        self.candidates = [case(1), case(2), case(3)]

    def test_select_uses_cache(self):
        llm = FakeLLM(['{"selected": [2]}'])
        first = select_cases(llm, self.cache, "156", "202610231100", "오늘 개황", self.candidates, max_n=5)
        again = select_cases(llm, self.cache, "156", "202610231100", "오늘 개황", self.candidates, max_n=5)
        self.assertEqual([c.doc_id for c in first], ["fcst:156:20241102"])
        self.assertEqual(again, first)
        self.assertEqual(len(llm.calls), 1)  # 두 번째는 LLM을 부르지 않는다

    def test_select_respects_max(self):
        llm = FakeLLM(['{"selected": [3, 1, 2]}'])
        picked = select_cases(llm, self.cache, "156", "t", "오늘 개황", self.candidates, max_n=2)
        self.assertEqual([c.doc_id for c in picked], ["fcst:156:20241103", "fcst:156:20241101"])

    def test_select_parse_failure_not_cached(self):
        llm = FakeLLM(["모르겠다", "그래도 모르겠다"])
        self.assertEqual(select_cases(llm, self.cache, "156", "t", "오늘 개황", self.candidates, max_n=5), [])
        self.assertIsNone(get_selection(self.cache, "156", "t"))


if __name__ == "__main__":
    unittest.main()
