"""プロフィール：属性の変更・パスワードの変更・退会（api.md 7-2）。

パスワードの変更と退会は、今のパスワードを打ち直してもらう。打ち間違い（失敗）は、
変更と退会を合わせて利用者ごとに1時間5回まで（api.md 5-2）。成功は数えない。
"""

import logging
import uuid

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.models import User, UserAttribute
from app.services import rate_limit

logger = logging.getLogger(__name__)


def change_attribute(db: Session, user: User, attribute: UserAttribute) -> User:
    user.attribute = attribute.value
    db.commit()
    return user


def _reserve_password_confirm(db: Session, user_id: uuid.UUID) -> uuid.UUID:
    """パスワードを確かめる前に、回数制限を確かめて1回分を押さえる（ログインと同じ考え方）。"""
    try:
        return rate_limit.reserve(db, rate_limit.PASSWORD_CONFIRM, str(user_id))
    except AppError:
        # 乗っ取りを試されている可能性があるので、警告として残す（全端末のログアウトはしない）
        logger.warning("password confirm rate limit reached: user=%s", user_id)
        raise


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    user_id = user.id
    attempt_id = _reserve_password_confirm(db, user_id)

    if not verify_password(current_password, user.password_hash):
        # 失敗は数えたまま残す。401 にしないのは、画面が「ログインが切れた」と取り違えないため
        raise AppError(400, "CURRENT_PASSWORD_INCORRECT", "今のパスワードが正しくありません")

    # 本人と確かめられたので、ここから先は回数に数えない
    rate_limit.release(db, attempt_id)

    # 今と同じかは、今のパスワードが正しいとわかってから判定する（先に判定すると手がかりを与えるため）
    if new_password == current_password:
        raise AppError(400, "SAME_AS_CURRENT_PASSWORD", "今と同じパスワードは使えません")

    # バージョン番号を上げて、今までの JWT をすべて使えなくする（全端末でログアウト）
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(password_hash=hash_password(new_password), token_version=User.token_version + 1)
    )
    db.commit()


def withdraw(db: Session, user: User, password: str) -> None:
    user_id = user.id
    attempt_id = _reserve_password_confirm(db, user_id)

    if not verify_password(password, user.password_hash):
        raise AppError(400, "PASSWORD_INCORRECT", "パスワードが正しくありません")

    rate_limit.release(db, attempt_id)
    # 本・気づき・AI提案・個人の AI の回数は、データベースの決まり（ON DELETE CASCADE）で一緒に消える。
    # アプリ全体の回数（app_ai_usages）は誰のものかを持たないので減らない（database.md 3-6）
    db.execute(delete(User).where(User.id == user_id))
    db.commit()
