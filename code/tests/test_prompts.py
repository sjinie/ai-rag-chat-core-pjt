import unittest

from domain.prompts import Plan, answer_messages, ask_json, parse_plan, parse_selected, plan_messages
from tests.fakes import FakeLLM

EMPTY = {"wiki": [], "nasa": [], "noaa": [], "ipcc": [], "kma_terms": []}


class PlanTest(unittest.TestCase):
    def test_parse_plan_valid(self):
        text = '```json\n{"need_cases": true, "queries": {"wiki": ["열대야"], "nasa": [], "unknown": ["x"]}}\n```'
        self.assertEqual(parse_plan(text), Plan(True, {**EMPTY, "wiki": ["열대야"]}))

    def test_parse_plan_reads_place_description(self):
        plan = parse_plan('{"need_cases": false, "queries": {}, "place": "겨울에 아주 춥고 산이 많은 곳"}')
        self.assertEqual(plan.place, "겨울에 아주 춥고 산이 많은 곳")
        self.assertEqual(parse_plan('{"need_cases": false, "queries": {}}').place, "")  # 없으면 빈 문자열
        self.assertIsNone(parse_plan('{"need_cases": false, "queries": {}, "place": ["산"]}'))

    def test_parse_plan_caps_two_queries(self):
        plan = parse_plan('{"need_cases": false, "queries": {"wiki": ["a", "b", "c"]}}')
        self.assertEqual(plan.queries["wiki"], ["a", "b"])

    def test_parse_plan_rejects_wrong_shape(self):
        self.assertIsNone(parse_plan('{"need_cases": "yes", "queries": {}}'))
        self.assertIsNone(parse_plan('{"queries": {"wiki": "열대야"}}'))

    def test_parse_plan_falls_back(self):
        llm = FakeLLM(["모르겠어요", "여전히 아님"])
        self.assertIsNone(ask_json(llm, [{"role": "user", "content": "q"}], parse_plan))
        self.assertEqual(len(llm.calls), 2)

    def test_ask_json_recovers_on_retry(self):
        llm = FakeLLM(["설명부터 할게요", '{"need_cases": true, "queries": {}}'])
        self.assertEqual(ask_json(llm, [{"role": "user", "content": "q"}], parse_plan), Plan(True, EMPTY))
        self.assertIn("JSON", llm.calls[1][-1]["content"])  # 두 번째 요청은 JSON만 다시 달라고 한다

    def test_plan_prompt_mentions_languages(self):
        system = plan_messages("서울(108)", "2026-10-23", "오늘 맑음", "열대야 기준이 뭐야?", [])[0]["content"]
        self.assertIn("영어", system)
        self.assertIn("한국어", system)


class SelectTest(unittest.TestCase):
    def test_parse_selected_filters_invalid(self):
        self.assertEqual(parse_selected('{"selected": [1, 7, "x"]}', {1, 2}), [1])
        self.assertIsNone(parse_selected("1번이요", {1, 2}))


class AnswerTest(unittest.TestCase):
    def test_answer_messages_keep_history_and_evidence(self):
        history = [{"role": "user", "content": "이전 질문"}, {"role": "assistant", "content": "이전 답"}]
        msgs = answer_messages("내일은?", "[근거 1] (지점 정보) 서울\n최고 20℃", history)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1:3], history)
        self.assertIn("[근거 1] (지점 정보) 서울", msgs[-1]["content"])
        self.assertIn("내일은?", msgs[-1]["content"])


if __name__ == "__main__":
    unittest.main()
