import unittest

from domain.stations import climate_traits, match_stations

# fetch_stations()의 실제 값 일부
STATIONS = {
    "104": {"name": "북강릉", "address": "강원특별자치도 강릉시 사천면 방동리"},
    "105": {"name": "강릉", "address": "강원특별자치도 강릉시 용강동"},
    "108": {"name": "서울", "address": "서울특별시 종로구 송월동"},
    "172": {"name": "고창", "address": "전북특별자치도 고창군 대산면 매산리"},
    "217": {"name": "정선군", "address": "강원특별자치도 정선군 정선읍 애산리"},
    "251": {"name": "고창군", "address": "전북특별자치도 고창군 고창읍 덕산리"},
    "295": {"name": "남해", "address": "경상남도 남해군 이동면 다정리"},
    "106": {"name": "동해", "address": "강원특별자치도 동해시 용정동"},
    "201": {"name": "강화", "address": "인천광역시 강화군 불은면 삼성리"},
    "216": {"name": "태백", "address": "강원특별자치도 태백시 황지동"},
    "236": {"name": "부여", "address": "충청남도 부여군 부여읍 가탑리"},
}


def year_rows(year: int, hot: int, tropical: int, rain_total: float) -> list[dict]:
    """1년 365일. 앞 hot일은 최고 34℃, 앞 tropical일은 최저 26℃, 1월 1일에 rain_total mm."""
    rows = []
    for i in range(365):
        rows.append({"date": f"{year}{i:04d}", "stn": "1", "ta_avg": 20.0, "ta_max": 34.0 if i < hot else 25.0,
                     "ta_min": 26.0 if i < tropical else 10.0, "hm_avg": 60.0, "ws_avg": 2.0,
                     "rn_day": rain_total if i == 0 else 0.0})
    return rows


class TraitsTest(unittest.TestCase):
    def test_traits_hot_and_rainy(self):
        rows = year_rows(2016, 15, 13, 1600.0) + year_rows(2017, 15, 12, 1600.0)  # 2년: 폭염 30일, 열대야 25일
        text = " ".join(climate_traits(rows, {"name": "부산", "height": 50.0, "mountain": False}))
        for word in ("폭염 잦음", "연 15.0일", "열대야 잦음", "연 12.5일", "다우지", "평지"):
            self.assertIn(word, text)
        for word in ("한파 잦음", "소우지", "산지", "섬"):
            self.assertNotIn(word, text)

    def test_traits_mountain_island(self):
        rows = year_rows(2016, 0, 0, 900.0)
        text = " ".join(climate_traits(rows, {"name": "대관령", "height": 772.4, "mountain": True}))
        for word in ("산지", "고지대", "소우지"):
            self.assertIn(word, text)
        self.assertIn("섬", " ".join(climate_traits(rows, {"name": "울릉도", "height": 221.1, "mountain": False})))


class MatchTest(unittest.TestCase):
    def test_match_by_name_and_district(self):
        self.assertEqual(match_stations("강릉 날씨", STATIONS), ["105"])  # 강릉시 주소인 북강릉보다 이름 일치 우선
        self.assertEqual(match_stations("북강릉은 어때?", STATIONS), ["104"])  # 긴 이름 안의 '강릉'은 따로 세지 않음
        self.assertEqual(match_stations("정선 비 와?", STATIONS), ["217"])
        self.assertEqual(match_stations("종로구 오늘 추워?", STATIONS), ["108"])  # 이름이 없으면 시·군·구

    def test_match_ignores_names_inside_other_words(self):
        # 최종 리뷰에서 실제 97개 지점으로 지점이 바뀌던 문장들
        for text in ("남해안에 비 많이 와?", "동해안 너울 조심해야 해?", "한파가 강화된다는데 내일 추워?",
                     "태백산맥 때문에 푄 현상이 생겨?", "부여된 특보 있어?"):
            self.assertEqual(match_stations(text, STATIONS), [], text)
        self.assertEqual(match_stations("남해는 오늘 어때?", STATIONS), ["295"])  # 조사가 붙은 지명은 그대로
        self.assertEqual(match_stations("강화 날씨", STATIONS), ["201"])

    def test_match_ambiguous_and_none(self):
        self.assertEqual(match_stations("고창", STATIONS), ["172", "251"])
        self.assertEqual(match_stations("강남구", STATIONS), [])


if __name__ == "__main__":
    unittest.main()
