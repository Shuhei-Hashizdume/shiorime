// まだ作っていない画面の仮の表示。機能3（気づき）・機能5（プロフィール）で本物に置き換える。

import { useState } from "react";
import { useNavigate } from "react-router";

import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function InsightsPlaceholder() {
  return (
    <main className="page page-with-tabs placeholder">
      <h1 className="title">気づき</h1>
      <p>気づきの画面は、機能3で作ります。</p>
    </main>
  );
}

export function ProfilePlaceholder() {
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
    <main className="page page-with-tabs placeholder">
      <h1 className="title">プロフィール</h1>
      <p>プロフィールの画面は、機能5で作ります。</p>
      {state.status === "user" && <p>ログイン中：{state.user.email}</p>}
      {/* ログアウトの場所は決まりのとおりプロフィール。画面は機能5で作り直す */}
      <button type="button" className="button button-secondary" onClick={handleLogout} disabled={busy}>
        ログアウト
      </button>
    </main>
  );
}
