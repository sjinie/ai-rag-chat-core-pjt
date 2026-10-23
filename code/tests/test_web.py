import unittest
from unittest.mock import patch

import requests

from rag.html_text import html_to_text
from rag.web import BlockedHost, get
from tests.fakes import FakeResponse, FakeSession

WIKI = "https://ko.wikipedia.org/w/api.php"


@patch("rag.web.time.sleep", lambda s: None)
class WebTest(unittest.TestCase):
    def test_disallowed_host_blocked(self):
        session = FakeSession([])
        with self.assertRaises(BlockedHost):
            get("https://evil.example/x", session=session)
        self.assertEqual(session.calls, [])  # 요청 자체가 나가지 않아야 한다

    def test_redirect_to_disallowed_host_blocked(self):
        session = FakeSession([FakeResponse(302, "", {"Location": "https://evil.example/"})])
        with self.assertRaises(BlockedHost):
            get(WIKI, session=session)
        self.assertEqual(len(session.calls), 1)

    def test_retry_after_429_then_ok(self):
        session = FakeSession([FakeResponse(429, "", {"Retry-After": "1"}), FakeResponse(200, "본문")])
        self.assertEqual(get(WIKI, session=session).text, "본문")
        self.assertEqual(len(session.calls), 2)

    def test_error_message_has_no_query(self):
        err = requests.ConnectionError("Max retries exceeded with url: /w/api.php?authKey=SECRET")
        session = FakeSession([err] * 4)
        with self.assertRaises(RuntimeError) as ctx:
            get(WIKI, params={"authKey": "SECRET"}, session=session)
        self.assertNotIn("SECRET", str(ctx.exception))
        self.assertNotIn("?", str(ctx.exception))
        self.assertEqual(len(session.calls), 4)

    def test_html_to_text_drops_scripts(self):
        self.assertEqual(html_to_text("<nav>메뉴</nav><p>본문</p><script>x</script>"), "본문")


if __name__ == "__main__":
    unittest.main()
