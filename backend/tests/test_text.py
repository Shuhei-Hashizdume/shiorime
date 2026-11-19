"""文字の数え方（api.md 5-1）。"""

from typing import Annotated

import pytest
from pydantic import AfterValidator, BaseModel, ValidationError

from app.core.text import count_chars, normalize, text_validator


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("気づき", 3),
        ("😀", 1),
        ("👨‍👩‍👧", 1),  # 家族の絵文字（中身は5つ）
        ("が", 1),  # 分かれた形の濁点（か＋゛）
        ("", 0),
    ],
)
def test_count_chars_counts_what_you_see(value: str, expected: int) -> None:
    assert count_chars(value) == expected


def test_normalize_strips_and_joins_dakuten() -> None:
    assert normalize("  が  ") == "が"


class Note(BaseModel):
    body: Annotated[str, AfterValidator(text_validator(10))]


def _reason(value: str) -> tuple[str, dict]:
    with pytest.raises(ValidationError) as exc_info:
        Note(body=value)
    error = exc_info.value.errors()[0]
    return error["type"], error.get("ctx", {})


def test_text_at_limit_is_ok() -> None:
    assert Note(body="あ" * 10).body == "あ" * 10


def test_text_over_limit_is_too_long() -> None:
    assert _reason("あ" * 11) == ("too_long", {"limit": 10})


def test_emoji_counted_as_one_each() -> None:
    # 😀 は JavaScript の .length では2だが、見た目は1文字
    assert Note(body="😀" * 10).body == "😀" * 10


def test_family_emoji_within_codepoint_limit() -> None:
    # 家族の絵文字は中身が5つ。上限10文字なら中身は40まで → 8個（中身40）は通る
    assert Note(body="👨‍👩‍👧" * 8).body == "👨‍👩‍👧" * 8


def test_whitespace_only_is_required() -> None:
    assert _reason("   ")[0] == "required"


def test_surrounding_whitespace_is_removed_before_counting() -> None:
    assert Note(body="  " + "あ" * 10 + "  ").body == "あ" * 10


def test_zalgo_text_is_stopped_by_codepoint_limit() -> None:
    # 見た目1文字に記号を大量に重ねる（見た目は1文字でも中身が多すぎる）
    zalgo = "a" + "́" * 50
    assert count_chars(zalgo) == 1
    assert _reason(zalgo)[0] == "too_long"
