"""文字の数え方と、入力の文字のそろえ方（api.md 5-1）。

文字数は見た目の1文字（書記素クラスタ）で数える。数える関数は count_chars の1つだけにし、
気づき・引用・回答・タイトル・著者・パスワードなど、すべての入力で使う。
"""

import unicodedata
from collections.abc import Callable

import regex
from pydantic_core import PydanticCustomError

# 中身の量（コードポイントの数）の上限は、見た目の上限の4倍（api.md 5-1、database.md 2-3）
CODEPOINT_FACTOR = 4

_GRAPHEME = regex.compile(r"\X")


def count_chars(value: str) -> int:
    """見た目の文字数（書記素クラスタの数）を返す。例："👨‍👩‍👧" は 1、"が"（か＋゛）は 1。"""
    return len(_GRAPHEME.findall(value))


def normalize(value: str) -> str:
    """前後の空白を除き、Unicode の NFC にそろえる。保存もこの形で行う。"""
    return unicodedata.normalize("NFC", value.strip())


def _check_codepoints(value: str, max_chars: int) -> None:
    if len(value) > max_chars * CODEPOINT_FACTOR:
        raise PydanticCustomError("too_long", "{limit}文字以内で入力してください", {"limit": max_chars})


def text_validator(max_chars: int) -> Callable[[str], str]:
    """空でない文字の欄（気づき・タイトルなど）の確かめ。Pydantic の AfterValidator に渡す。"""

    def validate(value: str) -> str:
        value = normalize(value)
        if value == "":
            raise PydanticCustomError("required", "入力してください")
        _check_codepoints(value, max_chars)
        if count_chars(value) > max_chars:
            raise PydanticCustomError("too_long", "{limit}文字以内で入力してください", {"limit": max_chars})
        return value

    return validate


def length_range_validator(min_chars: int, max_chars: int) -> Callable[[str], str]:
    """長さに下限と上限がある欄（パスワードなど）の確かめ。範囲外は out_of_range。"""

    def validate(value: str) -> str:
        value = normalize(value)
        if value == "":
            raise PydanticCustomError("required", "入力してください")
        ctx = {"min": min_chars, "max": max_chars}
        if len(value) > max_chars * CODEPOINT_FACTOR:
            raise PydanticCustomError("out_of_range", "{min}〜{max}文字で入力してください", ctx)
        if not min_chars <= count_chars(value) <= max_chars:
            raise PydanticCustomError("out_of_range", "{min}〜{max}文字で入力してください", ctx)
        return value

    return validate


def required_text(value: str) -> str:
    """上限は決めず、空でないことだけを確かめる欄（ログインのパスワードなど）。"""
    value = normalize(value)
    if value == "":
        raise PydanticCustomError("required", "入力してください")
    return value
