"""テストの準備。

テストは開発用のデータベースとは別の、テスト用のデータベース（shiorime_test）を使う。
app を読み込む前に環境変数を差し替えるので、この部分はファイルの一番上に置く。
"""

import os

os.environ["POSTGRES_DB"] = os.environ.get("TEST_POSTGRES_DB", "shiorime_test")

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _create_test_database() -> None:
    """テスト用のデータベースがなければ作る。"""
    conninfo = settings.database_url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(conninfo, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (settings.postgres_db,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{settings.postgres_db}"')


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    """テストの最初に1回、テスト用のデータベースに本物と同じマイグレーションを当てる。"""
    _create_test_database()
    config = Config(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    """テストごとに全部のテーブルを空にする。テストどうしが影響しないようにするため。"""
    yield
    table_names = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_names} CASCADE"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    # Cookie に Secure を付けているので、https で呼ばないと Cookie が送り返されない
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


# ---- 本棚のテストで使うもの ----

from app.services.google_books import get_google_books  # noqa: E402
from tests.fakes import FakeGoogleBooks  # noqa: E402


@pytest.fixture
def google_books() -> Iterator[FakeGoogleBooks]:
    """Google Books を偽物に置き換える（テストでは本物を呼ばない）。"""
    fake = FakeGoogleBooks()
    app.dependency_overrides[get_google_books] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_google_books, None)


def _logged_in_client(email: str) -> TestClient:
    c = TestClient(app, base_url="https://testserver")
    c.__enter__()
    response = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse", "attribute": "working", "agreed_to_terms": True},
        headers={"X-Forwarded-For": f"198.51.100.{abs(hash(email)) % 250}"},
    )
    assert response.status_code == 201, response.text
    return c


@pytest.fixture
def user_client() -> Iterator[TestClient]:
    """ログイン済みの利用者"""
    c = _logged_in_client("reader@example.com")
    yield c
    c.__exit__(None, None, None)


@pytest.fixture
def other_client() -> Iterator[TestClient]:
    """別の利用者（他人のデータを見られないかの確認に使う）"""
    c = _logged_in_client("other@example.com")
    yield c
    c.__exit__(None, None, None)


# ---- AI提案のテストで使うもの ----

from app.services import ai_client as ai_client_module  # noqa: E402
from tests.fakes import FakeAi  # noqa: E402


@pytest.fixture
def ai(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeAi]:
    """OpenAI を偽物に置き換える（テストでは本物を呼ばない）。再試行の前の待ち時間も0秒にする。"""
    fake = FakeAi()
    monkeypatch.setattr(ai_client_module, "RETRY_WAIT_SECONDS", 0)
    app.dependency_overrides[ai_client_module.get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(ai_client_module.get_ai_client, None)
