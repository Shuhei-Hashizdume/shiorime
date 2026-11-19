// ログイン後の戻り先（api.md 3-5）。
// アプリの中のパス（"/" で始まり "//" で始まらないもの）だけを受け付け、外部のサイトへ移されるのを防ぐ。

const AUTH_PATHS = ["/login", "/register", "/welcome"];

export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return "/";
  }
  const path = next.split(/[?#]/)[0];
  if (AUTH_PATHS.includes(path)) {
    return "/";
  }
  return next;
}

/** ログイン画面と新規登録画面を行き来するとき、next を付けたまま持ち回る。 */
export function withNext(path: string, next: string | null): string {
  return next ? `${path}?next=${encodeURIComponent(next)}` : path;
}
