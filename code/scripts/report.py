"""검증 스크립트가 docs/검증결과.md의 표시된 절만 바꿔 쓴다. 사람이 채운 다른 칸은 건드리지 않는다."""
from config import ROOT

DOC = ROOT / "docs" / "검증결과.md"


def write_section(name: str, markdown: str) -> None:
    begin, end = f"<!-- BEGIN:{name} -->", f"<!-- END:{name} -->"
    text = DOC.read_text(encoding="utf-8")
    if begin not in text or end not in text:
        raise SystemExit(f"{DOC}에 {begin} … {end} 표시가 없습니다.")
    head, rest = text.split(begin, 1)
    DOC.write_text(f"{head}{begin}\n{markdown.strip()}\n{end}{rest.split(end, 1)[1]}", encoding="utf-8")
    print(f"{DOC.name}의 '{name}' 절을 갱신했습니다.")


def cell(text: str) -> str:
    """표 칸 안에 들어가도록 줄바꿈과 | 를 바꾼다."""
    return text.replace("|", "\\|").replace("\n", "<br>")
