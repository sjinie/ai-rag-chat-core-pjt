"""Streamlit 화면 동작 확인. 실제 app.py를 AppTest로 돌리고, LLM·스토어·기상청 호출만 가짜로 바꾼다."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

import service
from tests.fakes import FakeLLM
from tests.fixtures import NO_PLAN, NOW, OBS, TODAY, make_deps

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class AppTestCase(unittest.TestCase):
    def setUp(self):
        st.cache_resource.clear()  # 앞 테스트의 Service가 남지 않게
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patches = [patch("rag.graph.fetch_latest_forecast", lambda office, now: TODAY),
                        patch("rag.graph.fetch_today_obs", lambda stn, today: OBS),
                        patch("service.now", lambda: NOW),
                        patch("service.check_ready", lambda: []),
                        patch("service.collection_counts", lambda: {})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def start(self, llm) -> AppTest:
        fake = service.Service(make_deps(self.tmp.name, llm))
        self.patches.append(patch("service.create", lambda: fake))
        self.patches[-1].start()
        return AppTest.from_file(APP, default_timeout=60).run()

    def chat_markdown(self, at) -> str:
        return " ".join(m.value for msg in at.chat_message for m in msg.markdown)

    def test_missing_setup_shows_only_guidance(self):
        with patch("service.check_ready", lambda: ["GMS_KEY가 설정되지 않았습니다."]):
            at = AppTest.from_file(APP, default_timeout=60).run()
        self.assertIn("GMS_KEY가 설정되지 않았습니다.", at.error[0].value)
        self.assertEqual(len(at.chat_input), 0)
        self.assertEqual(len(at.exception), 0)

    def test_plain_and_rag_answer_separately(self):
        at = self.start(FakeLLM(["단순 답입니다"]))
        at.chat_input(key="plain_in").set_value("오늘 서울 비 와?").run()
        self.assertIn("단순 답입니다", self.chat_markdown(at))
        self.assertEqual(at.session_state.histories["108"]["rag"], [])
        self.assertEqual(len(at.exception), 0)

    def test_rag_location_switches_station(self):
        at = self.start(FakeLLM([NO_PLAN, "강릉은 맑습니다 [근거 2]"]))
        at.chat_input(key="rag_in").set_value("강릉 날씨 어때?").run()
        self.assertEqual(at.session_state.stn, "105")
        self.assertEqual(at.selectbox(key="stn").value, "105")
        self.assertIn("강릉은 맑습니다", self.chat_markdown(at))
        self.assertEqual(at.session_state.histories["105"]["rag"][-1]["cited"][0][1], "오늘 개황")
        self.assertEqual(at.session_state.histories.get("108", {"rag": []})["rag"], [])  # 서울 대화와 섞이지 않는다

    def test_ambiguous_location_waits_for_choice(self):
        at = self.start(FakeLLM([NO_PLAN, "고창 답 [근거 1]"]))
        at.chat_input(key="rag_in").set_value("고창 날씨").run()
        self.assertEqual(sorted(b.key for b in at.button if b.key and b.key.startswith("cand_")), ["cand_172", "cand_251"])
        self.assertNotIn("고창 답", self.chat_markdown(at))  # 고르기 전에는 답하지 않는다
        at.button(key="cand_251").click().run()
        self.assertEqual(at.session_state.stn, "251")
        self.assertIn("고창 답", self.chat_markdown(at))

    def test_uncited_answer_shows_notice(self):
        at = self.start(FakeLLM([NO_PLAN, "근거 문서에서 확인되지 않습니다."]))
        at.chat_input(key="rag_in").set_value("내일 우주 날씨는?").run()
        self.assertIn("ⓘ 답변에 인용된 근거가 없습니다.", [c.value for c in at.caption])


if __name__ == "__main__":
    unittest.main()
