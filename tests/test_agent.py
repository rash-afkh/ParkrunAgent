"""Offline tests for agent helpers (no LLM call)."""

from parkrun_agent.agent.agent import _message_text


class _Msg:
    def __init__(self, content):
        self.content = content


def test_message_text_plain_string():
    assert _message_text(_Msg("  hello  ")) == "hello"


def test_message_text_drops_thinking_blocks():
    content = [
        {"type": "thinking", "thinking": "", "signature": "abc"},
        {"type": "text", "text": "Run at Bushy parkrun."},
    ]
    assert _message_text(_Msg(content)) == "Run at Bushy parkrun."


def test_message_text_joins_multiple_text_blocks():
    content = [{"type": "text", "text": "One."}, {"type": "text", "text": "Two."}]
    assert _message_text(_Msg(content)) == "One.\nTwo."
