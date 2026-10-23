import os
import tempfile
import unittest
from unittest.mock import patch

import service
from tests.fakes import FakeLLM
from tests.fixtures import NO_PLAN, NOW, OBS, PLACE_PLAN, TODAY, make_deps


class CheckReadyTest(unittest.TestCase):
    def test_check_ready_reports_missing_key_without_value(self):
        with patch.dict(os.environ, {"GMS_KEY": "", "KMA_API_KEY": "SECRET-KMA-123"}):
            problems = " ".join(service.check_ready())
        self.assertIn("GMS_KEY", problems)
        self.assertNotIn("SECRET-KMA-123", problems)
        self.assertNotIn("KMA_API_KEY", problems)  # 있는 키는 문제 목록에 없다

    def test_check_ready_requires_wiki_contact(self):
        # User-Agent 연락처 없이 외부 출처를 부르면 NF2006 위반이고 위키백과 한도가 분당 10회로 줄어든다
        with patch.dict(os.environ, {"WIKI_CONTACT": ""}):
            self.assertIn("WIKI_CONTACT", " ".join(service.check_ready()))


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patches = [patch("rag.graph.fetch_latest_forecast", lambda office, now: TODAY),
                        patch("rag.graph.fetch_today_obs", lambda stn, today: OBS),
                        patch("service.fetch_today_obs", lambda stn, today: OBS),
                        patch("service.now", lambda: NOW)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def svc(self, llm) -> service.Service:
        return service.Service(make_deps(self.tmp.name, llm))

    def test_plain_chat_sends_only_system_and_history(self):
        llm = FakeLLM(["단순 답"])
        history = [{"role": "user", "content": "오늘 비 와?"}]
        self.assertEqual(self.svc(llm).plain_chat(history), "단순 답")
        sent = llm.calls[0]
        self.assertEqual([m["role"] for m in sent], ["system", "user"])
        self.assertNotIn("서울", " ".join(m["content"] for m in sent))  # 지점·날짜는 사용자가 말해야만 안다

    def test_ask_returns_only_cited(self):
        llm = FakeLLM(['{"need_cases": true, "queries": {}}', '{"selected": [1]}', "평소보다 따뜻합니다 [근거 1]"])
        answer = self.svc(llm).ask("108", "오늘 서울 따뜻해?", [])
        self.assertEqual(answer.text, "평소보다 따뜻합니다 [근거 1]")
        self.assertEqual([(n, e.kind) for n, e in answer.cited], [(1, "지점 정보")])
        self.assertTrue(answer.has_cases)  # 인용은 안 됐지만 유사 사례 근거가 문맥에 들어갔다

    def test_today_report_table_rows(self):
        rows, answer = self.svc(FakeLLM([NO_PLAN, '{"selected": [1]}', "리포트 [근거 3]"])).today_report("108")
        self.assertEqual([r["항목"] for r in rows], ["평균기온", "최고기온", "최저기온", "상대습도", "평균풍속", "강수량"])
        by = {r["항목"]: r for r in rows}
        # 하루가 끝나기 전 값이라는 것이 표에 드러나야 한다
        self.assertEqual((by["최고기온"]["오늘 관측(지금까지)"], by["최고기온"]["최근 10년 기준값"], by["최고기온"]["차이"]),
                         (21.0, 19.0, 2.0))
        self.assertEqual(by["최고기온"]["판정"], "높음")    # z = 2/2 = 1.0
        self.assertEqual(by["상대습도"]["판정"], "비슷")    # z = -8/10
        self.assertTrue(answer.has_cases)

    def test_today_report_survives_kma_failure(self):
        def fail(*args):
            raise RuntimeError("kma_sfcdd.php 연결 실패: ReadTimeout")
        with patch("service.fetch_today_obs", fail):
            rows, _ = self.svc(FakeLLM([NO_PLAN, '{"selected": [1]}', "리포트"])).today_report("108")
        self.assertEqual(rows[1]["판정"], "자료 없음")

    def test_history_citations_stripped(self):
        # 이전 답의 [근거 2]는 그때의 번호다. 그대로 넘기면 이번 답이 옛 번호를 베껴 엉뚱한 문서를 가리킬 수 있다
        llm = FakeLLM([NO_PLAN, "답"])
        history = [{"role": "user", "content": "오늘 어때?"}, {"role": "assistant", "content": "맑습니다 [근거 2, 3]."}]
        self.svc(llm).ask("108", "내일은?", history)
        for call in llm.calls:
            sent_history = [m["content"] for m in call[1:-1]]
            self.assertEqual(sent_history, ["오늘 어때?", "맑습니다."])

    def test_ask_returns_place_candidates(self):
        answer = self.svc(FakeLLM([PLACE_PLAN, '{"selected": [1, 2]}'])).ask("108", "산이 많은 곳 여름 날씨는?", [])
        self.assertEqual(len(answer.candidates), 2)
        self.assertEqual(answer.text, "")

    def test_explore_returns_selected_stations(self):
        llm = FakeLLM(['{"selected": [1]}'])
        found = self.svc(llm).explore("서울특별시 종로구")
        self.assertEqual(len(found), 1)
        self.assertIn(found[0], {"108", "105", "172", "251"})  # 유사도 1순위 지점의 번호를 돌려준다
        self.assertIn("조건", llm.calls[0][-1]["content"])

    def test_resolve_location(self):
        self.assertEqual(self.svc(FakeLLM([])).resolve_location("강릉 날씨"), ["105"])


if __name__ == "__main__":
    unittest.main()
