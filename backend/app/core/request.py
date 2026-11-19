from starlette.requests import Request


def get_client_ip(request: Request) -> str:
    """接続元の IP を返す（回数制限に使う。api.md 5-2）。

    本番では FastAPI へは Caddy からしか届かない。Caddy は、利用者が送ってきた
    X-Forwarded-For を信用せず、実際の接続元の IP を入れ直して渡すので、その最後の値を使う。
    Caddy を通らない開発中の直接の呼び出しでは、TCP の接続元を使う。
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"
