"""HTML → 본문 텍스트. 표준 html.parser만 쓴다."""
from html.parser import HTMLParser

SKIP = {"script", "style", "nav", "header", "footer", "noscript", "svg"}
BLOCK = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "dd", "dt", "table"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip_depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip_depth += 1
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """메뉴·스크립트를 뺀 본문. 블록 요소마다 줄을 바꾸고 빈 줄은 하나로 줄인다."""
    parser = _Extractor()
    parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)
