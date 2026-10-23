import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from langchain_core.embeddings import DeterministicFakeEmbedding

from domain.weather_db import connect, save_baselines, save_obs
from rag.cache import connect_cache
from rag.evidence import Evidence, cited, merge
from rag.graph import Deps, build_graph
from rag.store import get_store
from tests.fakes import FakeLLM

NOW = datetime(2026, 10, 23, 15, 0)
TODAY = {"office": "109", "tmfc": "202610231100", "summary": "□ (종합) 오늘 맑음 ○ (오늘) 맑음",
         "body": "□ (종합) 오늘 맑음\n○ (오늘) 맑음\n○ (내일) 오후부터 비"}
OBS = {"ta_avg": 15.0, "ta_max": 21.0, "ta_min": 9.0, "hm_avg": 55.0, "ws_avg": 2.0, "rn_day": 0.0}
BASE = {"ta_avg": 14.0, "ta_max": 19.0, "ta_min": 9.0, "hm_avg": 63.0, "ws_avg": 2.0, "rn_day": 1.0,
        "ta_avg_sd": 2.0, "ta_max_sd": 2.0, "ta_min_sd": 2.0, "hm_avg_sd": 10.0, "ws_avg_sd": 0.5, "rn_day_sd": 3.0,
        "n": 150, "years": 10}
NO_PLAN = '{"need_cases": false, "queries": {}}'


class CountingAdapter:
    searches = 0

    def search(self, query, limit=5):
        CountingAdapter.searches += 1
        return []


class GraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        emb = DeterministicFakeEmbedding(size=64)
        stores = {name: get_store(name, emb, self.tmp.name)
                  for name in ("station_meta", "forecast_texts", "climate_docs", "live_forecasts")}
        stores["station_meta"].add_texts(["서울(108) 관측소 · 서울특별시 종로구"], ids=["108"],
                                         metadatas=[{"title": "서울(108) 지점 정보 · 최근 10년 기준값", "url": "u"}])
        stores["forecast_texts"].add_texts(["□ (종합) 오늘 맑음 ○ (오늘) 맑음", "□ (종합) 오늘 비"],
                                           ids=["fcst:109:20241023", "fcst:109:20231023"],
                                           metadatas=[{"office": "109", "date": "20241023", "title": "수도권 개황 2024", "url": "u"},
                                                      {"office": "109", "date": "20231023", "title": "수도권 개황 2023", "url": "u"}])
        db = connect(":memory:")
        save_obs(db, [{"stn": "108", "date": d, **OBS} for d in ("20241023", "20231023")])
        save_baselines(db, {"108": {(10, 23): BASE}})
        self.deps = lambda llm: Deps(llm=llm, station_meta=stores["station_meta"], forecast_texts=stores["forecast_texts"],
                                     climate_docs=stores["climate_docs"], live_forecasts=stores["live_forecasts"],
                                     db=db, cache=connect_cache(":memory:"),
                                     stations={"108": {"name": "서울", "fct_id": "11B10101"}}, on_step=lambda s: None)
        self.patches = [patch("rag.graph.fetch_latest_forecast", lambda office, now: TODAY),
                        patch("rag.graph.fetch_today_obs", lambda stn, today: OBS),
                        patch("rag.collect.ADAPTERS", {"wiki": CountingAdapter()})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_graph(self, llm, question="오늘 서울 어때?", force_cases=False):
        return build_graph(self.deps(llm)).invoke({"stn": "108", "question": question, "history": [], "now": NOW,
                                                   "force_cases": force_cases, "evidence": [], "steps": [], "answer": ""})

    def test_graph_has_two_nodes(self):
        nodes = set(build_graph(self.deps(FakeLLM([]))).get_graph().nodes) - {"__start__", "__end__"}
        self.assertEqual(nodes, {"retrieve", "generate"})

    def test_station_and_today_forecast_always_in_context(self):
        out = self.run_graph(FakeLLM([NO_PLAN, "맑습니다 [근거 2]"]))
        self.assertEqual([e.kind for e in out["evidence"]], ["지점 정보", "오늘 개황"])
        self.assertIn("최근 10년 기준값보다", out["evidence"][0].text)
        self.assertIn("(내일) 오후부터 비", out["evidence"][1].text)  # 이어지는 질문을 위해 개황 전체를 넘긴다
        self.assertEqual(out["answer"], "맑습니다 [근거 2]")

    def test_no_external_search_for_today_weather(self):
        CountingAdapter.searches = 0
        self.run_graph(FakeLLM([NO_PLAN, "답"]))
        self.assertEqual(CountingAdapter.searches, 0)

    def test_cases_added_when_needed(self):
        llm = FakeLLM(['{"need_cases": true, "queries": {}}', '{"selected": [1]}', "답 [근거 3]"])
        out = self.run_graph(llm)
        self.assertEqual([e.kind for e in out["evidence"]], ["지점 정보", "오늘 개황", "유사 사례"])
        self.assertIn("그날 실제 관측", out["evidence"][2].text)

    def test_force_cases_overrides_plan(self):
        out = self.run_graph(FakeLLM([NO_PLAN, '{"selected": [1]}', "답"]), force_cases=True)
        self.assertIn("유사 사례", [e.kind for e in out["evidence"]])

    def test_plan_failure_still_answers(self):
        out = self.run_graph(FakeLLM(["모름", "여전히 모름", "기본 근거로 답함"]))
        self.assertEqual(out["answer"], "기본 근거로 답함")
        self.assertEqual([e.kind for e in out["evidence"]], ["지점 정보", "오늘 개황"])


class EvidenceTest(unittest.TestCase):
    def test_cited_ignores_unknown_numbers(self):
        items = [Evidence("지점 정보", f"d{i}", f"t{i}", "u", "x") for i in (1, 2, 3)]
        self.assertEqual([(n, e.doc_id) for n, e in cited("맑음 [근거 2] 비 [근거 9]", items)], [(2, "d2")])
        self.assertEqual([n for n, _ in cited("[근거 1, 3]", items)], [1, 3])
        self.assertEqual(cited("근거 없음", items), [])

    def test_merge_drops_duplicate_doc_ids(self):
        a, b = Evidence("위키백과", "x", "t", "u", "1"), Evidence("NASA", "y", "t", "u", "2")
        self.assertEqual(merge([a, b], [a]), [a, b])


if __name__ == "__main__":
    unittest.main()
