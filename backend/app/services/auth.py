"""新規登録・ログイン（api.md 7-1）。"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.core.security import hash_password, verify_dummy_password, verify_password
from app.models import User, UserAttribute
from app.services import rate_limit


def register(
    db: Session,
    *,
    email: str,
    password: str,
    attribute: UserAttribute,
    client_ip: str,
) -> User:
    # 登録できた分と「既に登録されています」を数える。入力の誤り（422）はここまで来ないので数えない。
    rate_limit.reserve(db, rate_limit.REGISTER, client_ip)

    password_hash = hash_password(password)

    # 「同じメールアドレスがないか確かめる → 作る」を1回の命令で行う。
    # 同時に2つ届いても、一意制約で片方だけが作られる（notes.md 2章）。
    user = db.scalars(
        insert(User)
        .values(
            email=email,
            password_hash=password_hash,
            attribute=attribute.value,
            terms_agreed_at=clock.now(),
        )
        .on_conflict_do_nothing(index_elements=[User.email])
        .returning(User)
    ).one_or_none()

    if user is None:
        db.rollback()
        raise AppError(409, "EMAIL_ALREADY_REGISTERED", "このメールアドレスは既に登録されています")

    db.commit()
    return user


def login(db: Session, *, email: str, password: str, client_ip: str) -> User:
    # パスワードを確かめる前に、回数制限を確かめる（総当たりと重い計算をさせられるのを防ぐ）
    attempt_id = rate_limit.reserve(db, rate_limit.LOGIN, client_ip)

    user = db.scalars(select(User).where(User.email == email)).one_or_none()

    if user is None:
        # ユーザーがいなくても同じ重さの計算をして、返事の速さで登録済みかを知られないようにする
        verify_dummy_password(password)
        raise _invalid_credentials()

    if not verify_password(password, user.password_hash):
        raise _invalid_credentials()

    # 成功は数えない
    rate_limit.release(db, attempt_id)
    return user


def _invalid_credentials() -> AppError:
    # どちらが違うかは伝えない（要件定義書）
    return AppError(401, "INVALID_CREDENTIALS", "メールアドレスかパスワードが違います")
