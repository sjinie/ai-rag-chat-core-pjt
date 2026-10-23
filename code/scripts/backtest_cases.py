"""유사 사례 사후 검증 (ADR 0001). LLM을 부르지 않는다.

    cd code
    python -m scripts.backtest_cases

2025년 개황 가운데 관할 지방청마다 무작위 30일(시드 0)을 뽑아, 그날 개황과 비슷했던 과거 5일(앞뒤 3일 제외)의
대표 지점 최고기온 평균이 실제 최고기온에 얼마나 가까운지를 '그날 최근 10년 기준값'과 비교한다.
비 온 날(1mm 이상) 맞힘률도 비교한다. 유사 사례는 과반이 비 온 날이면 '비', 기준값은 일강수량 기준값 1mm 이상이면 '비'.
"""
import random
from datetime import datetime, timedelta
from statistics import mean

from domain.cases import case_candidates
from domain.stations import OFFICES
from domain.weather_db import connect, get_baseline, get_obs
from rag.store import get_store
from scripts.report import write_section

YEAR, PER_OFFICE, TOP, GAP = "2025", 30, 5, 3
REPRESENTATIVE = {"109": "108"}  # 수도권기상청은 같은 번호의 관측 지점이 없어 서울로 둔다


def nearby(day: str) -> frozenset[str]:
    d = datetime.strptime(day, "%Y%m%d")
    return frozenset((d + timedelta(days=k)).strftime("%Y%m%d") for k in range(-GAP, GAP + 1))


def main() -> None:
    store, db, rng = get_store("forecast_texts"), connect(), random.Random(0)
    lines = ["| 관할 지방청 (대표 지점) | 표본 | 최고기온 오차: 유사 사례 | 유사 사례(편차 보정) | 기준값 | "
             "비 맞힘: 유사 사례 | 기준값 | 항상 '비 없음' |",
             "|---|---|---|---|---|---|---|---|"]
    totals = {"case": [], "adj": [], "base": [], "case_hit": 0, "base_hit": 0, "dry_hit": 0}
    for office, office_name in OFFICES.items():
        stn = REPRESENTATIVE.get(office, office)
        got = store.get(where={"office": office}, include=["documents", "metadatas"])
        days = sorted((m["date"], doc) for doc, m in zip(got["documents"], got["metadatas"]) if m["date"].startswith(YEAR))
        errors_case, errors_adj, errors_base, hit_case, hit_base, hit_dry = [], [], [], 0, 0, 0
        for day, summary in rng.sample(days, PER_OFFICE):
            actual, base = get_obs(db, stn, [day]), get_baseline(db, stn, day[4:])
            if not actual or actual[0]["ta_max"] is None or not base:
                continue
            cases = case_candidates(store, db, stn, office, summary, TOP, exclude_dates=nearby(day))
            highs = [c.obs["ta_max"] for c in cases if c.obs["ta_max"] is not None]
            if not highs:
                continue
            # 편차 보정: 사례들이 '그날 기준값'보다 얼마나 높고 낮았는지를 오늘 기준값에 더한다 (화면이 보여 주는 방식, Q14)
            deviations = [c.obs["ta_max"] - get_baseline(db, stn, c.date[4:])["ta_max"]
                          for c in cases if c.obs["ta_max"] is not None]
            truth = actual[0]
            errors_case.append(abs(mean(highs) - truth["ta_max"]))
            errors_adj.append(abs(base["ta_max"] + mean(deviations) - truth["ta_max"]))
            errors_base.append(abs(base["ta_max"] - truth["ta_max"]))
            rained = (truth["rn_day"] or 0) >= 1
            hit_case += (sum((c.obs["rn_day"] or 0) >= 1 for c in cases) * 2 > len(cases)) == rained
            hit_base += ((base["rn_day"] or 0) >= 1) == rained
            hit_dry += not rained
        n = len(errors_case)
        lines.append(f"| {office_name} ({stn}) | {n} | {mean(errors_case):.2f}℃ | {mean(errors_adj):.2f}℃ | "
                     f"{mean(errors_base):.2f}℃ | {hit_case / n:.0%} | {hit_base / n:.0%} | {hit_dry / n:.0%} |")
        for key, values in (("case", errors_case), ("adj", errors_adj), ("base", errors_base)):
            totals[key] += values
        totals["case_hit"] += hit_case
        totals["base_hit"] += hit_base
        totals["dry_hit"] += hit_dry
        print(f"  {office_name}: 표본 {n}")
    n = len(totals["case"])
    lines.append(f"| **전체** | {n} | **{mean(totals['case']):.2f}℃** | **{mean(totals['adj']):.2f}℃** | "
                 f"**{mean(totals['base']):.2f}℃** | **{totals['case_hit'] / n:.0%}** | **{totals['base_hit'] / n:.0%}** | "
                 f"**{totals['dry_hit'] / n:.0%}** |")
    temp = "편차 보정한 유사 사례가 기준값보다 실제에 가깝다" if mean(totals["adj"]) < mean(totals["base"]) \
        else "편차 보정한 유사 사례도 기준값보다 낫지 않다"
    rain = "유사 사례가 '항상 비 없음'보다 비를 더 잘 맞힌다" if totals["case_hit"] > totals["dry_hit"] \
        else "유사 사례가 '항상 비 없음'보다 비를 더 잘 맞히지 못한다"
    better = f"최고기온은 {temp}. 비는 {rain}"
    write_section("backtest", "\n".join([
        f"방법: 2025년 개황 중 관할 지방청마다 무작위 {PER_OFFICE}일(시드 0). 같은 지방청 개황 유사도 상위 {TOP}일(앞뒤 {GAP}일 제외)의 "
        "대표 지점 관측을 그날 실제 관측과 비교. 프롬프트2 선별 없이 순수 유사도만 사용. "
        "기준값(2016~2025)에는 검증 날짜 자체도 들어 있어 기준값 쪽에 약간 유리하다.", "",
        *lines, "", f"결론: **{better}**."]))


if __name__ == "__main__":
    main()
