import tempfile
import unittest
from unittest.mock import patch

from rag.evidence import Evidence, cited, merge
from rag.graph import build_graph
from tests.fakes import FakeLLM
from tests.fixtures import NO_PLAN, NOW, OBS, PLACE_PLAN, TODAY, make_deps


class CountingAdapter:
    searches = 0

    def search(self, query, limit=5):
        CountingAdapter.searches += 1
        return []


class GraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patches = [patch("rag.graph.fetch_latest_forecast", lambda office, now: TODAY),
                        patch("rag.graph.fetch_today_obs", lambda stn, today: OBS),
                        patch("rag.collect.ADAPTERS", {"wiki": CountingAdapter()})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_graph(self, llm, question="오늘 서울 어때?", force_cases=False, place_resolved=False):
        return build_graph(make_deps(self.tmp.name, llm)).invoke(
            {"stn": "108", "question": question, "history": [], "now": NOW, "force_cases": force_cases,
             "place_resolved": place_resolved, "evidence": [], "steps": [], "answer": "", "candidates": []})

    def test_graph_has_two_nodes(self):
        nodes = set(build_graph(make_deps(self.tmp.name, FakeLLM([]))).get_graph().nodes) - {"__start__", "__end__"}
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

    def test_place_description_returns_candidates_without_answer(self):
        llm = FakeLLM([PLACE_PLAN, '{"selected": [1, 2]}'])
        out = self.run_graph(llm, question="겨울에 아주 춥고 산이 많은 곳은 여름에 어때?")
        self.assertEqual(len(out["candidates"]), 2)
        self.assertEqual(out["answer"], "")
        self.assertEqual(len(llm.calls), 2)  # 프롬프트1과 지점 선별만. 답변 LLM은 부르지 않는다

    def test_resolved_place_answers_normally(self):
        out = self.run_graph(FakeLLM([PLACE_PLAN, "대관령 여름 답"]), place_resolved=True)
        self.assertEqual(out["candidates"], [])
        self.assertEqual(out["answer"], "대관령 여름 답")

    def test_kma_failure_still_answers(self):
        def fail(*args):
            raise RuntimeError("fct_afs_ds.php 연결 실패: ReadTimeout")
        with patch("rag.graph.fetch_latest_forecast", fail), patch("rag.graph.fetch_today_obs", fail):
            out = self.run_graph(FakeLLM([NO_PLAN, "지점 정보로 답함 [근거 1]"]))
        self.assertEqual(out["answer"], "지점 정보로 답함 [근거 1]")
        self.assertEqual([e.kind for e in out["evidence"]], ["지점 정보"])
        self.assertIn("오늘 개황을 받지 못했습니다", out["steps"])
        self.assertIn("오늘 관측을 받지 못했습니다", out["steps"])

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
