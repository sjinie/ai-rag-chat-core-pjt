"""고정 문서(IPCC 용어집 PDF, 기상청 날씨누리 용어 표)를 용어 하나 단위로 자른다."""
from html.parser import HTMLParser

from pypdf import PdfReader

GLOSSARY_HEADERS = {"Annex VII Glossary", "AVII"}  # 쪽마다 용어 글꼴로 찍히는 머리글


def read_glossary_runs(path) -> list[tuple[int, str, str]]:
    """PDF 글자 조각을 (쪽, 종류, 글자)로. 용어는 BlackCn 글꼴, 쪽 번호는 BoldCn 글꼴이다."""
    runs = []
    for no, page in enumerate(PdfReader(path).pages, 1):
        def visit(text, cm, tm, font, size, no=no):
            name = str((font or {}).get("/BaseFont", ""))
            runs.append((no, "term" if "BlackCn" in name else "header" if "BoldCn" in name else "body", text))
        page.extract_text(visitor_text=visit)
    return runs


def split_glossary_runs(runs: list[tuple[int, str, str]]) -> list[tuple[str, str, int]]:
    """(용어, 정의, 용어가 시작한 쪽). 첫 용어 앞의 글과 머리글·쪽 번호는 버린다."""
    entries, term, parts, page, last_kind = [], "", [], 0, ""

    def close():
        text = " ".join(" ".join(parts).split())
        if term and text:
            entries.append((term, text, page))

    for no, kind, text in runs:
        if not text.strip() or kind == "header" or (kind == "term" and text.strip() in GLOSSARY_HEADERS):
            continue
        if kind == "term" and last_kind == "term":
            term = f"{term} {text.strip()}"  # 한 용어가 글자 조각 여러 개로 나뉜 경우
        elif kind == "term":
            close()
            term, parts, page = text.strip(), [], no
        else:
            parts.append(text)
        last_kind = kind
    close()
    return entries


class _Tables(HTMLParser):
    """표마다 머리글(thead)과 본문 행을 모은다. 주석 처리된 행은 HTMLParser가 건너뛴다."""

    def __init__(self):
        super().__init__()
        self.tables, self.in_head, self.row, self.cell = [], False, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append({"labels": [], "rows": []})
        elif tag == "thead":
            self.in_head = True
        elif tag == "tr":
            self.row = []
        elif tag in ("th", "td"):
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag == "thead":
            self.in_head = False
        elif tag in ("th", "td") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.tables:
            if self.in_head:
                self.tables[-1]["labels"] = self.row
            else:
                self.tables[-1]["rows"].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def split_kma_terms(html: str) -> list[tuple[str, str]]:
    """표의 첫 칸을 용어로, 나머지 칸을 '머리글: 내용 / …'으로 묶는다. 내용이 '-'뿐인 칸은 뺀다."""
    parser = _Tables()
    parser.feed(html)
    entries = []
    for table in parser.tables:
        labels = table["labels"][1:]
        for row in table["rows"]:
            if not row:
                continue
            values = row[1:]
            parts = [f"{label}: {v}" if label else v
                     for label, v in zip(labels + [""] * len(values), values) if v and v != "-"]
            if parts:
                entries.append((row[0], " / ".join(parts)))
    return entries
