import unittest
from datetime import date, datetime
from unittest.mock import patch

from domain.kma import fetch_latest_forecast, fetch_today_obs, live_forecast_doc
from domain.stations import anomaly_sentence, classify


def block(office: str, tmfc: str, body: str) -> str:
    return f"$0#{office}#{tmfc}#{tmfc}#2#예보관#\n$1#\n{body}#\n$2#\n#\n$3#\n#\n=\n"


class FakeKma:
    """request_kma 대체. 요청 파라미터를 기록하고, 구간 안의 발표분만 돌려준다."""

    def __init__(self, issues: dict[str, str]):
        self.issues, self.requests = issues, []

    def __call__(self, path, params):
        self.requests.append(params)
        lo, hi = params["tmfc1"], params["tmfc2"]
        return "#START7777\n" + "".join(block("156", t, b) for t, b in self.issues.items() if lo <= t <= hi)


BODY = "□ (종합) 오늘 오후부터 비\n  ○ (오늘) 흐림, 오후부터 비\n  ○ (내일) 맑음"


class LatestForecastTest(unittest.TestCase):
    def test_latest_forecast_picks_latest_issue(self):
        kma = FakeKma({"202610240500": BODY, "202610241100": BODY.replace("흐림", "구름많음")})
        with patch("domain.kma.request_kma", kma):
            f = fetch_latest_forecast("156", datetime(2026, 10, 24, 15, 0))
        self.assertEqual(f["tmfc"], "202610241100")
        self.assertEqual(f["summary"], "□ (종합) 오늘 오후부터 비 ○ (오늘) 구름많음, 오후부터 비")

    def test_latest_forecast_before_5am_uses_previous_day(self):
        kma = FakeKma({"202610231700": BODY, "202610231100": BODY})
        with patch("domain.kma.request_kma", kma):
            f = fetch_latest_forecast("156", datetime(2026, 10, 24, 3, 0))
        self.assertEqual((kma.requests[0]["tmfc1"], kma.requests[0]["tmfc2"]), ("202610231700", "202610231700"))
        self.assertEqual(f["tmfc"], "202610231700")

    def test_latest_forecast_falls_back_when_today_not_out(self):
        kma = FakeKma({"202610231700": BODY})  # 05:02인데 오늘 05시분이 아직 안 올라옴
        with patch("domain.kma.request_kma", kma):
            f = fetch_latest_forecast("156", datetime(2026, 10, 24, 5, 2))
        self.assertEqual(f["tmfc"], "202610231700")

    def test_live_forecast_doc_title_shows_issue_time(self):
        doc_id, text, meta = live_forecast_doc({"office": "156", "tmfc": "202610231700", "body": BODY,
                                               "summary": "요약"}, "광주지방기상청")
        self.assertEqual((doc_id, text), ("live:156:202610231700", "요약"))
        self.assertEqual(meta["title"], "광주지방기상청 단기예보 개황 · 2026-10-23 17시 발표")


class TodayObsTest(unittest.TestCase):
    def test_today_obs_parses_comma_format(self):
        # 실제 2026-10-22 서울 일자료(하루가 끝나기 전): 최고·최저만 있고 평균·습도·풍속은 결측
        row = ("20261022,108,-9.0,-9,29,3.6,1006,25,6.1,1035,-99.0,13.2,1141,5.2,716,-99.0,-99.0,-0.5,-9.0,32.0,"
               "1145,-9.0,-9.0,-9.0,-9.00,-9.0,-9.0,1029.2,958,1025.9,11,-9.0,-9.0,11.0,-9.0,-9.00,-9.00,-9,-9.0,"
               "-9.0,-9.00,-9.0,-9,-9.0,-9,-9.0,-9,-9.0,-9,-9.0,-9,-99.0,-99.0,-99.0,-99.0,-99.0,")
        with patch("domain.kma.request_kma", lambda path, params: f"#START7777\n# 머리글\n{row}\n#7777END\n"):
            obs = fetch_today_obs("108", date(2026, 10, 22))
        self.assertEqual((obs["ta_max"], obs["ta_min"]), (13.2, 5.2))
        self.assertIsNone(obs["ta_avg"])
        self.assertIsNone(obs["hm_avg"])


class AnomalyTest(unittest.TestCase):
    def test_classify_thresholds(self):
        self.assertEqual(classify(10, 14, 2), "매우 낮음")
        self.assertEqual(classify(12, 14, 2), "낮음")
        self.assertEqual(classify(13, 14, 2), "비슷")
        self.assertEqual(classify(16.5, 14, 2), "높음")
        self.assertEqual(classify(18.5, 14, 2), "매우 높음")
        self.assertEqual(classify(None, 14, 2), "자료 없음")
        self.assertEqual(classify(15, 14, 0), "높음")  # 표준편차 0이면 부호만 본다

    def test_anomaly_sentence_rain_none(self):
        obs = {"ta_avg": 9.0, "ta_max": 15.1, "ta_min": 4.0, "hm_avg": None, "ws_avg": 2.0, "rn_day": 0.0}
        base = {"ta_avg": 14.1, "ta_max": 19.3, "ta_min": 9.6, "hm_avg": 63.2, "ws_avg": 2.0, "rn_day": 1.2,
                "ta_avg_sd": 2.9, "ta_max_sd": 2.0, "ta_min_sd": 3.4, "hm_avg_sd": 10.6, "ws_avg_sd": 0.6, "rn_day_sd": 5.4}
        s = anomaly_sentence(obs, base)
        self.assertIn("최고기온 15.1℃(최근 10년 기준값보다 4.2℃ 낮음, 매우 낮음)", s)
        self.assertIn("상대습도 자료 없음", s)
        self.assertIn("비 없음", s)


if __name__ == "__main__":
    unittest.main()
