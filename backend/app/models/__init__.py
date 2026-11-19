# Alembic がテーブルの定義を見つけられるよう、テーブルのクラスはここで import する。
from app.models.base import Base

__all__ = ["Base"]
