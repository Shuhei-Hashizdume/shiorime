// ログインが必要な画面で API が 401 を返したら、ログインが切れたとして扱う（api.md 7-2）。
// ログイン状態を「未ログイン」にすると、RequireAuth がログイン画面（戻り先付き）へ移す。

import { useCallback } from "react";

import { ApiError } from "../api/client";
import { useAuth } from "./AuthContext";

export function useUnauthorized(): (error: unknown) => boolean {
  const { logOut } = useAuth();
  return useCallback(
    (error: unknown) => {
      if (!(error instanceof ApiError) || error.status !== 401) return false;
      logOut(error.code === "TOKEN_EXPIRED" ? "expired" : error.code === "TOKEN_REVOKED" ? "revoked" : null);
      return true;
    },
    [logOut],
  );
}
