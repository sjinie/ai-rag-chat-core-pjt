import unittest

from rag.fixed_docs import split_glossary_runs, split_kma_terms

# IPCC AR6 WG1 Annex VII에서 pypdf visitor로 뽑은 실제 run. (쪽, 글꼴 종류, 글자)
# 용어는 BlackCn 글꼴("term"), 쪽 번호는 BoldCn("header"), 본문은 그 밖("body")
GLOSSARY_RUNS = [
    (3, "body", "."),
    (3, "term", "Albedo "),
    (3, "body", "The proportion of sunlight ("),
    (3, "body", " solar radiation"),
    (3, "body", " ) reflected by "),
    (3, "body", "a\xa0surface or object, often expressed as a percentage."),
    (4, "header", "2218"),
    (4, "term", "Annex VII Glossary"),
    (4, "term", "AVII"),
    (6, "term", "Carbon budget "),
    (6, "body", "Refers to two concepts in the literature: (i) "),
    (6, "body", "an assessment of carbon cycle "),
    (6, "body", "sources"),
    (31, "term", "Radiative forcing "),
    (31, "body", "The change in the net, downward minus "),
    (31, "body", "upward, radiative "),
    (31, "body", "flux"),
]

# 날씨누리 forecast03.jsp의 실제 표(폭염·열대야) + 주석 처리된 옛 행이 있는 표
KMA_HTML = """
<table class="table_information"><caption>기상특보종류와 발표기준을 주의보, 경보, 중대경보일 경우를 알려주는 표입니다.</caption>
<thead><tr><th scope="col">종류</th><th scope="col">주의보</th><th scope="col">경보</th><th scope="col">중대경보</th></tr></thead>
<tbody><tr><th scope="row">폭염</th><td class="tal_l_i">일 최고 체감온도 33℃ 이상이 2일 이상 지속될 것으로 예상될 때</td>
<td class="tal_l_i">일 최고 체감온도 35℃ 이상이 2일 이상 지속될 것으로 예상될 때</td>
<td class="tal_l_i">일 최고 체감온도 35℃ 이상이 2일 이상 관측된 지역에서 다음의 어느 하나에 해당하는 경우<br> 1) 일 최고 체감온도 38℃ 이상이 1일 이상 지속될 것으로 예상될 때<br> 2) 일 최고기온 39℃ 이상이 1일 이상 지속될 것으로 예상될 때</td></tr>
<tr><th scope="row">열대야</th><td class="tal_l_i">일 최고 체감온도 33℃ 이상이 2일 이상 지속될 것으로 예상되는 경우로서 해당 기간 밤 최저기온이 기상청장이 정하는 지역별 발효기준 값 이상일 것으로 예상될 때</td>
<td class="tal_l_i">-</td><td class="tal_l_i">-</td></tr></tbody></table>
<table><thead><tr><th scope="col">종류</th><th scope="col">주의보</th></tr></thead>
<tbody><!--<tr><th scope="row">폭염</th><td>옛 기준</td></tr>--><tr><th scope="row">황사</th><td>-</td></tr></tbody></table>
"""


class GlossaryTest(unittest.TestCase):
    def test_glossary_terms_split(self):
        terms = {term: (text, page) for term, text, page in split_glossary_runs(GLOSSARY_RUNS)}
        self.assertEqual(set(terms), {"Albedo", "Carbon budget", "Radiative forcing"})
        self.assertEqual(terms["Albedo"], ("The proportion of sunlight ( solar radiation ) reflected by "
                                           "a surface or object, often expressed as a percentage.", 3))
        self.assertEqual(terms["Radiative forcing"][1], 31)
        self.assertNotIn("2218", terms["Albedo"][0])  # 쪽 번호·머리글은 정의에 섞이지 않는다


class KmaTermsTest(unittest.TestCase):
    def test_kma_terms_split(self):
        terms = dict(split_kma_terms(KMA_HTML))
        self.assertEqual(set(terms), {"폭염", "열대야"})  # 주석 처리된 행과 내용이 '-'뿐인 행은 빠진다
        self.assertTrue(terms["폭염"].startswith("주의보: 일 최고 체감온도 33℃ 이상"))
        self.assertIn("중대경보: 일 최고 체감온도 35℃", terms["폭염"])
        self.assertIn("밤 최저기온", terms["열대야"])
        self.assertNotIn("경보: -", terms["열대야"])


if __name__ == "__main__":
    unittest.main()
