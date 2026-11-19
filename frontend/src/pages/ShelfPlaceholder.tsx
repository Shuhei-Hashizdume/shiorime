// 本棚の仮の画面。機能2（本棚）で本物に置き換える。
// ログアウトはプロフィール（機能5）に置く決まりだが、それまで確かめられるよう、ここに仮で置く。

import { useState } from "react";
import { useNavigate } from "react-router";

import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { LogoHorizontal } from "../components/Logo";

export default function ShelfPlaceholder() {
  const { state, logOut } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  async function handleLogout() {
    setBusy(true);
    try {
      await api.post("/auth/logout");
    } finally {
      logOut();
      navigate("/login", { replace: true });
    }
  }

  return (
    <main className="page placeholder">
      <LogoHorizontal />
      <h1 className="title">本棚</h1>
      <p>本棚の画面は、機能2で作ります。</p>
      {state.status === "user" && <p>ログイン中：{state.user.email}</p>}
      <button type="button" className="button button-secondary" onClick={handleLogout} disabled={busy}>
        ログアウト（仮）
      </button>
    </main>
  );
}
