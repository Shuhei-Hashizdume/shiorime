import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, MetaData, Text, Uuid
from sqlalchemy.orm import DeclarativeBase

# 制約とインデックスの名前の付け方をそろえる。
# 名前が決まっていないと、あとで制約を消す・付け直すマイグレーションが書けないため。
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Python の型 → データベースの型（database.md 2章）
    # 文字は text、日時は timestamptz、ID は uuid
    type_annotation_map = {
        str: Text(),
        datetime: DateTime(timezone=True),
        date: Date(),
        uuid.UUID: Uuid(),
    }
