import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import review as review_module  # noqa: E402


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.replies.pop(0) if self.replies else ""
        message = types.SimpleNamespace(type="text", text=text)
        return types.SimpleNamespace(content=[message])


GOOD_REPLY = json.dumps(
    {
        "deadline_day": 21,
        "tasks": [
            {
                "id": "T1",
                "name": "Book the hall",
                "owner": "Ann",
                "duration_days": 3,
                "depends_on": [],
                "quote": "Ann books the hall, which takes three days.",
            }
        ],
        "findings": [],
    }
)


def test_review_plan_returns_scripted_reply_text():
    client = FakeClient([GOOD_REPLY])
    reply = review_module.review_plan("plan text", client=client)
    assert json.loads(reply)["deadline_day"] == 21
    call = client.calls[0]
    assert "plan text" in call["messages"][0]["content"]
    assert call["max_tokens"] == review_module.MAX_TOKENS


def test_review_plan_appends_corrective_text():
    client = FakeClient(["{}"])
    review_module.review_plan("plan text", client=client, corrective="quote was wrong")
    assert "quote was wrong" in client.calls[0]["messages"][0]["content"]
