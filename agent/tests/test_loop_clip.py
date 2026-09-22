"""A tool result clipped for the log says so."""
from __future__ import annotations

from rimagent.loop import LOG_CLIP, clip


def test_short_text_is_untouched():
    assert clip("abc") == "abc"


def test_text_at_the_limit_is_untouched():
    s = "x" * LOG_CLIP
    assert clip(s) == s


def test_longer_text_is_marked_so_the_log_does_not_look_malformed():
    s = '{"a": "' + "x" * (LOG_CLIP + 500) + '"}'
    out = clip(s)
    assert out.startswith(s[:LOG_CLIP])
    assert "log clipped" in out
    assert "the model was given the full result" in out
