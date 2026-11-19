from datetime import UTC, datetime


def now() -> datetime:
    """今の日時（UTC）。テストで時刻を差し替えられるよう、日時はここからだけ取る。"""
    return datetime.now(UTC)
