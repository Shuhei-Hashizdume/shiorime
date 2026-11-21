// ログイン状態（api.md 3章）。
// 画面を開いたときに1回だけ GET /me を呼び、200 ならログイン中、401 なら未ログインとして扱う。
// ログインしているかを判断するのは常にサーバーで、ここでの出し分けは見た目のためだけ。

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, ApiError, type Me } from "../api/client";

/** ログイン画面の上に出すお知らせ（screens.md 10.） */
export type LoginNotice = "expired" | "revoked" | "password_changed" | "withdrawn";

type AuthState =
  | { status: "loading" }
  /** left：ログアウト・パスワードの変更・退会で、自分で選んで抜けた（ログイン画面に戻り先を付けない） */
  | { status: "guest"; notice: LoginNotice | null; left?: boolean }
  | { status: "user"; user: Me };

type AuthContextValue = {
  state: AuthState;
  /** ログイン・新規登録に成功したとき */
  logIn: (user: Me) => void;
  /** ログアウトしたとき・401 が返ったとき。自分で選んで抜けたときは left を true にする */
  logOut: (notice?: LoginNotice | null, left?: boolean) => void;
  /** お知らせを1回出したら消す */
  clearNotice: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function noticeFromError(error: unknown): LoginNotice | null {
  if (error instanceof ApiError) {
    if (error.code === "TOKEN_EXPIRED") return "expired";
    if (error.code === "TOKEN_REVOKED") return "revoked";
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    api
      .get<Me>("/me")
      .then((user) => {
        if (!cancelled) setState({ status: "user", user });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: "guest", notice: noticeFromError(error) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const logIn = useCallback((user: Me) => setState({ status: "user", user }), []);
  const logOut = useCallback(
    (notice: LoginNotice | null = null, left = false) => setState({ status: "guest", notice, left }),
    [],
  );
  const clearNotice = useCallback(
    () => setState((prev) => (prev.status === "guest" && prev.notice ? { ...prev, notice: null } : prev)),
    [],
  );

  const value = useMemo(() => ({ state, logIn, logOut, clearNotice }), [state, logIn, logOut, clearNotice]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth は AuthProvider の中で使う");
  return value;
}
