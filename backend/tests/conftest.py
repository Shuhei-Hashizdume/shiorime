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
