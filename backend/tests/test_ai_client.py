"""OpenAI とのやりとり（api.md 2-6・2-7）。

本物の OpenAI は呼ばず、ライブラリの `responses.parse` の部分だけを偽物に差し替えて、
返事の確かめ方と、失敗の仕分け（再試行するか・しないか）を確かめる。
"""

from types import SimpleNamespace

import httpx2
import openai
import pytest

from app.core.config import settings
from app.services import ai_client
from app.services.ai_client import (
    AiError,
    InsightContext,
    OpenAiClient,
    PlanOutput,
    PlansOutput,
    QuestionOutput,
    call_with_retry,
)

CONTEXT = InsightContext(
    attribute="社会人", book_title="嫌われる勇気", book_author="岸見一郎", quote="他者の課題には踏み込まない", body="本文"
)
REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/responses")


class FakeResponses:
    """`client.responses` の偽物。result に返すもの（返事か例外）を入れ、受け取った引数を覚える。"""

    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def response(parsed=None, *, status: str = "completed", refusal: bool = False):
    output = [SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="できません")])] if refusal else []
    return SimpleNamespace(status=status, output=output, output_parsed=parsed)


def client_returning(result) -> tuple[OpenAiClient, FakeResponses]:
    client = OpenAiClient()
    fake = FakeResponses(result)
    client._client = SimpleNamespace(responses=fake)
    return client, fake


def plans(*texts: str) -> PlansOutput:
    return PlansOutput(plans=[PlanOutput(text=t) for t in texts])


def raised(client_call) -> AiError:
    with pytest.raises(AiError) as info:
        client_call()
    return info.value


# ---- 正しい形の返事 ----


def test_question_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    # 手元の .env の値に左右されないよう、推論の量は「空」にしておく
    monkeypatch.setattr(settings, "openai_reasoning_effort", None)
    client, fake = client_returning(response(QuestionOutput(question="  どんな言葉が浮かびますか？ ")))

    assert client.generate_question(CONTEXT) == "どんな言葉が浮かびますか？"

    (call,) = fake.calls
    assert call["model"] == settings.openai_model
    assert call["text_format"] is QuestionOutput
    assert call["max_output_tokens"] == 300
    # 利用者の文章を OpenAI 側に保存させない
    assert call["store"] is False
    assert "気づき：本文" in call["input"]
    assert "reasoning" not in call


def test_plans_are_returned_in_order() -> None:
    client, fake = client_returning(response(plans("一つ目", "二つ目", "三つ目")))

    assert client.generate_plans(CONTEXT, "質問", "回答") == ["一つ目", "二つ目", "三つ目"]
    (call,) = fake.calls
    assert call["max_output_tokens"] == 600
    assert "あなたの質問：質問" in call["input"]
    assert "利用者の回答：回答" in call["input"]


def test_reasoning_effort_is_sent_only_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_reasoning_effort", "low")
    client, fake = client_returning(response(QuestionOutput(question="質問")))

    client.generate_question(CONTEXT)

    assert fake.calls[0]["reasoning"] == {"effort": "low"}


# ---- 形が決まりと違う返事（1回だけ再試行する失敗） ----


@pytest.mark.parametrize(
    "parsed",
    [QuestionOutput(question=""), QuestionOutput(question="   "), QuestionOutput(question="あ" * 201), None],
    ids=["empty", "blank", "too_long", "unparsed"],
)
def test_invalid_question_is_retryable_error(parsed) -> None:
    client, _ = client_returning(response(parsed))

    error = raised(lambda: client.generate_question(CONTEXT))

    assert error.reason == "invalid_output"
    assert error.retryable


def test_question_of_200_chars_is_accepted() -> None:
    client, _ = client_returning(response(QuestionOutput(question="あ" * 200)))

    assert client.generate_question(CONTEXT) == "あ" * 200


@pytest.mark.parametrize(
    "parsed",
    [plans(), plans("1", "2", "3", "4"), plans("あ" * 101), plans("正しい", "")],
    ids=["zero", "four", "too_long", "one_blank"],
)
def test_invalid_plans_are_retryable_error(parsed: PlansOutput) -> None:
    client, _ = client_returning(response(parsed))

    error = raised(lambda: client.generate_plans(CONTEXT, "質問", "回答"))

    assert error.reason == "invalid_output"
    assert error.retryable


def test_incomplete_response_is_retryable_error() -> None:
    client, _ = client_returning(response(None, status="incomplete"))

    error = raised(lambda: client.generate_question(CONTEXT))

    assert error.reason == "incomplete"
    assert error.retryable


def test_refusal_is_not_retried() -> None:
    client, _ = client_returning(response(None, refusal=True))

    error = raised(lambda: client.generate_plans(CONTEXT, "質問", "回答"))

    assert error.reason == "refusal"
    assert not error.retryable


# ---- OpenAI の失敗の仕分け（api.md 2-6 の表） ----


def status_error(cls, status: int, *, code: str | None = None, headers: dict[str, str] | None = None):
    body = {"code": code} if code else None
    return cls("失敗", response=httpx2.Response(status, request=REQUEST, headers=headers), body=body)


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (openai.APITimeoutError(request=REQUEST), True),
        (openai.APIConnectionError(request=REQUEST), True),
        (status_error(openai.InternalServerError, 503), True),
        (status_error(openai.RateLimitError, 429, code="rate_limit_exceeded"), True),
        (status_error(openai.RateLimitError, 429, code="insufficient_quota"), False),
        (status_error(openai.AuthenticationError, 401), False),
        (status_error(openai.PermissionDeniedError, 403), False),
        (status_error(openai.BadRequestError, 400), False),
    ],
    ids=["timeout", "connection", "server_error", "rate_limit", "quota", "auth", "region", "bad_request"],
)
def test_openai_errors_are_classified(error: Exception, retryable: bool) -> None:
    client, _ = client_returning(error)

    assert raised(lambda: client.generate_question(CONTEXT)).retryable is retryable


def test_rate_limit_keeps_retry_after() -> None:
    client, _ = client_returning(status_error(openai.RateLimitError, 429, headers={"retry-after": "2"}))

    assert raised(lambda: client.generate_question(CONTEXT)).retry_after == 2.0


def test_library_retries_are_turned_off() -> None:
    client = OpenAiClient()

    assert client._client.max_retries == 0
    assert client._client.timeout == 30


# ---- 自動の再試行（1回だけ） ----


class Calls:
    """呼ぶたびに results から1つずつ返す（例外なら投げる）"""

    def __init__(self, *results) -> None:
        self.results = list(results)
        self.count = 0

    def __call__(self):
        self.count += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_temporary_failure_is_retried_once_after_1_second() -> None:
    call = Calls(AiError("server_error", retryable=True), "成功")
    waits: list[float] = []

    assert call_with_retry(call, sleep=waits.append) == "成功"
    assert call.count == 2
    assert waits == [ai_client.RETRY_WAIT_SECONDS]


def test_second_temporary_failure_is_not_retried_again() -> None:
    call = Calls(AiError("server_error", retryable=True), AiError("server_error", retryable=True), "呼ばれない")

    with pytest.raises(AiError):
        call_with_retry(call, sleep=lambda _: None)
    assert call.count == 2


def test_permanent_failure_is_not_retried() -> None:
    call = Calls(AiError("insufficient_quota", retryable=False), "呼ばれない")
    waits: list[float] = []

    with pytest.raises(AiError):
        call_with_retry(call, sleep=waits.append)
    assert call.count == 1
    assert waits == []


def test_waits_as_told_by_retry_after() -> None:
    call = Calls(AiError("rate_limited", retryable=True, retry_after=3), "成功")
    waits: list[float] = []

    assert call_with_retry(call, sleep=waits.append) == "成功"
    assert waits == [3]


def test_does_not_retry_when_told_to_wait_over_5_seconds() -> None:
    call = Calls(AiError("rate_limited", retryable=True, retry_after=6), "呼ばれない")

    with pytest.raises(AiError):
        call_with_retry(call, sleep=lambda _: None)
    assert call.count == 1
