from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def now() -> datetime:
    """今の日時（UTC）。テストで時刻を差し替えられるよう、日時はここからだけ取る。"""
    return datetime.now(UTC)


def jst_date(moment: datetime) -> date:
    """その瞬間の日本時間の日付。AI の回数の「今日」だけは日本時間で判断する（CLAUDE.md）。"""
    return moment.astimezone(JST).date()
