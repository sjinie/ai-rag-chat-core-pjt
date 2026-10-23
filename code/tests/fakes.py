"""테스트용 가짜 객체. 네트워크·LLM·임베딩 비용 없이 실제 코드 경로를 돈다."""
from types import SimpleNamespace


class FakeLLM:
    """invoke할 때마다 responses를 차례로 돌려주고, 받은 메시지를 calls에 쌓는다."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(content=self.responses.pop(0))


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", headers: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = headers or {}

    def json(self):
        import json
        return json.loads(self.text)


class FakeSession:
    """get 호출마다 responses를 차례로 돌려준다. 예외 객체면 던진다."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
