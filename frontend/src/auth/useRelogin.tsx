// 書いている途中でログインの期限が切れた場合（api.md 3-6）。
// 文を書く画面（気づきの作成・編集、AI提案の回答・送り直し）で、保存・送信に
// 401（TOKEN_EXPIRED・TOKEN_REVOKED）が返ったら、画面を移らずにその場でログインのシートを出す。
// ログインに成功したら、押そうとしていた保存・送信を自動で1回送り直す。書いた文は画面に残したまま。
//
// 使い方：
//   const relogin = useRelogin("ログインして保存する");
//   catch (error) { if (relogin.handle(error, () => save())) return; ... }
//   return <>{...}{relogin.sheet}</>;

import { useCallback, useRef, useState, type FormEvent, type ReactNode } from "react";

import { api, ApiError, type Me } from "../api/client";
import { ErrorBanner, InfoBanner } from "../components/Feedback";
import { PasswordField, TextField } from "../components/Fields";
import { Sheet } from "../components/Sheet";
import { normalize } from "../lib/text";
import { bannerForError, MESSAGES } from "../pages/authShared";
import { useAuth } from "./AuthContext";

type Reason = "TOKEN_EXPIRED" | "TOKEN_REVOKED";

const TITLES: Record<Reason, string> = {
  TOKEN_EXPIRED: "ログインの有効期限が切れました",
  TOKEN_REVOKED: "パスワードが変更されたため、もう一度ログインしてください",
};

export function useRelogin(submitLabel: string): {
  /** 期限切れ・パスワード変更の 401 ならシートを出して true。それ以外は false（呼ぶ側でふだんどおり扱う） */
  handle: (error: unknown, retry: () => void) => boolean;
  sheet: ReactNode;
} {
  const [reason, setReason] = useState<Reason | null>(null);
  const retryRef = useRef<(() => void) | null>(null);

  const handle = useCallback((error: unknown, retry: () => void) => {
    if (!(error instanceof ApiError) || error.status !== 401) return false;
    if (error.code !== "TOKEN_EXPIRED" && error.code !== "TOKEN_REVOKED") return false;
    retryRef.current = retry;
    setReason(error.code);
    return true;
  }, []);

  const sheet = reason ? (
    <ReloginSheet
      title={TITLES[reason]}
      submitLabel={submitLabel}
      onClose={() => setReason(null)}
      onLoggedIn={() => {
        setReason(null);
        retryRef.current?.();
      }}
    />
  ) : null;

  return { handle, sheet };
}

type Errors = { email?: string; password?: string };

function ReloginSheet({
  title,
  submitLabel,
  onClose,
  onLoggedIn,
}: {
  title: string;
  submitLabel: string;
  onClose: () => void;
  onLoggedIn: () => void;
}) {
  const { logIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const normalizedEmail = normalize(email).toLowerCase();
    const normalizedPassword = normalize(password);
    const found: Errors = {};
    if (normalizedEmail === "") found.email = MESSAGES.emailRequired;
    if (normalizedPassword === "") found.password = MESSAGES.passwordRequired;
    setErrors(found);
    setBanner(null);
    if (found.email || found.password) return;

    setSubmitting(true);
    try {
      // ふだんと同じログイン・同じ回数制限（サーバー側の追加はない）
      const user = await api.post<Me>("/auth/login", { email: normalizedEmail, password: normalizedPassword });
      logIn(user);
      onLoggedIn();
    } catch (error) {
      setSubmitting(false);
      setBanner(bannerForError(error) ?? MESSAGES.network);
    }
  }

  return (
    <Sheet title={title} onClose={onClose} variant="auto">
      <form className="form" onSubmit={handleSubmit} noValidate>
        <InfoBanner>書いた内容はこの画面に残っています。ログインすると、そのまま保存します。</InfoBanner>
        {banner && <ErrorBanner>{banner}</ErrorBanner>}
        <TextField
          label="メールアドレス"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          data-autofocus
        />
        <PasswordField
          label="パスワード"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
        />
        <div className="sheet-actions">
          <button type="submit" className="button button-primary" disabled={submitting}>
            {submitLabel}
          </button>
          <button type="button" className="button button-secondary" onClick={onClose}>
            キャンセル
          </button>
        </div>
      </form>
    </Sheet>
  );
}
