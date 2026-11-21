// 画面の移り方（api.md 3-2・3-4）。

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useAuth } from "./AuthContext";
import { withNext } from "./next";

/** ログインが必要な画面。未ログインならログイン画面へ（戻り先を付ける）。 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const location = useLocation();

  if (state.status === "loading") return null;
  if (state.status === "guest") {
    const here = location.pathname + location.search;
    // トップを開いた未ログインの人はウェルカムへ。ただし期限切れなどで既に使っている人とわかっていればログインへ
    if (location.pathname === "/") {
      return <Navigate to={state.notice ? "/login" : "/welcome"} replace />;
    }
    // パスワードの変更・退会は自分で選んで抜けたので、戻り先を付けない（次にログインする人が元の画面へ飛ばないように）
    if (state.notice === "password_changed" || state.notice === "withdrawn") return <Navigate to="/login" replace />;
    return <Navigate to={withNext("/login", here)} replace />;
  }
  return <>{children}</>;
}

/** ウェルカム・ログイン・新規登録。ログイン中なら本棚へ（履歴は置き換える）。 */
export function GuestOnly({ children }: { children: ReactNode }) {
  const { state } = useAuth();

  if (state.status === "loading") return null;
  if (state.status === "user") return <Navigate to="/" replace />;
  return <>{children}</>;
}
