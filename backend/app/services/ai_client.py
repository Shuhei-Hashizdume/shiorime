"""OpenAI とのやりとり（api.md 2-6・2-7）。

- AI には決まった形（JSON）で答えさせる（Structured Outputs）。受け取ったあと、形と長さを必ず確かめる。
- 自動の再試行は、ここ1か所で1回だけ行う（ライブラリの再試行はオフ）。
- テストでは偽物に置き換えるため、routers は get_ai_client() を Depends で受け取る。
"""

import logging
import time
from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar

import openai
from pydantic import BaseModel

from app.core.config import settings
from app.core.text import count_chars, normalize
from app.models.ai_proposal import PLANS_MAX, QUESTION_MAX_CHARS

logger = logging.getLogger(__name__)

PLAN_MAX_CHARS = 100
TIMEOUT_SECONDS = 30
RETRY_WAIT_SECONDS = 1.0
RETRY_AFTER_LIMIT_SECONDS = 5.0
QUESTION_MAX_OUTPUT_TOKENS = 300
PLANS_MAX_OUTPUT_TOKENS = 600


class AiError(Exception):
    """AI の呼び出しの失敗。retryable なら1回だけ自動で再試行する（api.md 2-6）。"""

    def __init__(self, reason: str, *, retryable: bool, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class InsightContext:
    """AI に送る情報（要件定義書 7.1「外部AIに送る情報」）。ページ番号・アカウントの情報は送らない。"""

    attribute: str
    book_title: str
    book_author: str | None
    quote: str | None
    body: str


class AiClient(Protocol):
    def generate_question(self, context: InsightContext) -> str: ...

    def generate_plans(self, context: InsightContext, question: str, answer: str) -> list[str]: ...


# ---- 返事の形と、受け取ったあとの確かめ（2-7） ----


class QuestionOutput(BaseModel):
    question: str


class PlanOutput(BaseModel):
    text: str


class PlansOutput(BaseModel):
    plans: list[PlanOutput]


def check_question(output: QuestionOutput) -> str:
    question = normalize(output.question)
    if question == "" or count_chars(question) > QUESTION_MAX_CHARS:
        raise AiError("invalid_output", retryable=True)
    return question


def check_plans(output: PlansOutput) -> list[str]:
    plans = [normalize(p.text) for p in output.plans]
    if not 1 <= len(plans) <= PLANS_MAX or any(p == "" or count_chars(p) > PLAN_MAX_CHARS for p in plans):
        raise AiError("invalid_output", retryable=True)
    return plans


# ---- 再試行（2-6） ----

T = TypeVar("T")


def call_with_retry(call: Callable[[], T], *, sleep: Callable[[float], None] = time.sleep) -> T:
    """1回呼び、一時的な失敗なら1回だけ再試行する。AI の呼び出しは最大2回。"""
    try:
        return call()
    except AiError as error:
        if not error.retryable:
            raise
        wait = RETRY_WAIT_SECONDS if error.retry_after is None else error.retry_after
        if wait > RETRY_AFTER_LIMIT_SECONDS:
            # 長く待つと、利用者の待ち時間の上限（約60秒）を超えるため
            raise
        logger.info("ai call failed (%s); retrying once", error.reason)
        sleep(wait)
        return call()


# ---- 本物 ----


def _retry_after(error: openai.APIStatusError) -> float | None:
    value = error.response.headers.get("retry-after") if error.response is not None else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _to_ai_error(error: Exception) -> AiError:
    """OpenAI の例外を、再試行するか・しないかに仕分ける（api.md 2-6 の表）。"""
    if isinstance(error, (openai.APITimeoutError, openai.APIConnectionError)):
        return AiError(type(error).__name__, retryable=True)
    if isinstance(error, openai.RateLimitError):
        code = getattr(error, "code", None)
        if code == "insufficient_quota":
            # 利用上限額・クレジット切れ。作る側が直すまで直らない
            logger.error("openai quota exceeded")
            return AiError("insufficient_quota", retryable=False)
        return AiError("rate_limited", retryable=True, retry_after=_retry_after(error))
    if isinstance(error, openai.InternalServerError):
        return AiError("server_error", retryable=True)
    if isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
        logger.error("openai rejected the api key or region: %s", type(error).__name__)
        return AiError(type(error).__name__, retryable=False)
    if isinstance(error, openai.APIStatusError):
        logger.error("openai request failed: status=%s", error.status_code)
        return AiError("bad_request", retryable=False)
    return AiError(type(error).__name__, retryable=False)


QUESTION_INSTRUCTIONS = """あなたは、読書で得た気づきを行動につなげる手助けをするコーチです。
利用者の気づきを読み、その人が自分の経験や本音に目を向けられるような、深掘りの質問を1つだけ作ってください。
- 質問は1つだけ。100文字程度の、やさしい日本語にする。
- はい・いいえで終わらない、自分の状況を具体的に思い出せる質問にする。
- 説教・評価・助言はしない。
- 利用者の属性に合った言葉づかいと場面を選ぶ。"""

PLANS_INSTRUCTIONS = """あなたは、読書で得た気づきを行動につなげる手助けをするコーチです。
利用者の気づき・あなたの質問・利用者の回答をもとに、実生活で試せる具体的な行動（次の一歩）を1〜3個作ってください。
- 1つは50文字程度の、やさしい日本語にする。
- 一般論ではなく、回答に書かれた本人の状況に合わせる。
- 今日か明日から始められる、小さく具体的な行動にする（「いつ・何を」がわかる）。
- 最も効果がありそうな順に並べる。"""


def _context_text(context: InsightContext) -> str:
    lines = [f"利用者の属性：{context.attribute}", f"本：{context.book_title}"]
    if context.book_author:
        lines.append(f"著者：{context.book_author}")
    if context.quote:
        lines.append(f"心に残った一文（引用）：{context.quote}")
    lines.append(f"気づき：{context.body}")
    return "\n".join(lines)


class OpenAiClient:
    def __init__(self) -> None:
        # ライブラリの自動の再試行はオフにし、こちらの1か所にまとめる（2-6）
        self._client = openai.OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            max_retries=0,
            timeout=TIMEOUT_SECONDS,
        )

    def _parse(self, instructions: str, user_input: str, output_type: type[BaseModel], max_tokens: int) -> BaseModel:
        options: dict = {}
        if settings.openai_reasoning_effort:
            options["reasoning"] = {"effort": settings.openai_reasoning_effort}
        try:
            response = self._client.responses.parse(
                model=settings.openai_model,
                instructions=instructions,
                input=user_input,
                text_format=output_type,
                max_output_tokens=max_tokens,
                # 利用者の文章を OpenAI 側に保存させない
                store=False,
                **options,
            )
        except openai.OpenAIError as error:
            raise _to_ai_error(error) from None

        if response.status == "incomplete":
            # 最大量で途中で切れた。形が違うのと同じく1回だけ再試行する（2-7）
            raise AiError("incomplete", retryable=True)
        for item in response.output:
            for content in getattr(item, "content", None) or []:
                if getattr(content, "type", None) == "refusal":
                    # AI が内容を理由に断った。同じ内容では同じ結果になるので再試行しない
                    raise AiError("refusal", retryable=False)
        parsed = response.output_parsed
        if parsed is None:
            raise AiError("invalid_output", retryable=True)
        return parsed

    def generate_question(self, context: InsightContext) -> str:
        output = self._parse(QUESTION_INSTRUCTIONS, _context_text(context), QuestionOutput, QUESTION_MAX_OUTPUT_TOKENS)
        assert isinstance(output, QuestionOutput)
        return check_question(output)

    def generate_plans(self, context: InsightContext, question: str, answer: str) -> list[str]:
        user_input = f"{_context_text(context)}\nあなたの質問：{question}\n利用者の回答：{answer}"
        output = self._parse(PLANS_INSTRUCTIONS, user_input, PlansOutput, PLANS_MAX_OUTPUT_TOKENS)
        assert isinstance(output, PlansOutput)
        return check_plans(output)


_client: OpenAiClient | None = None


def get_ai_client() -> AiClient:
    global _client
    if _client is None:
        _client = OpenAiClient()
    return _client
