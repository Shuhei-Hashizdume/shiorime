// ログイン（screens.md 10.、api.md 7-1・3-5）。

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";

import { api, type Me } from "../api/client";
import { useAuth, type LoginNotice } from "../auth/AuthContext";
import { safeNext, withNext } from "../auth/next";
import { ErrorBanner, InfoBanner } from "../components/Feedback";
import { PasswordField, TextField } from "../components/Fields";
import { normalize } from "../lib/text";
import { AuthHeader, bannerForError, MESSAGES, NOTICES } from "./authShared";

type Errors = { email?: string; password?: string };

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const next = searchParams.get("next");
  const { state, logIn, clearNotice } = useAuth();

  // お知らせは、画面を開いたときに1回だけ出す。
  // 出どころは、開いたときの GET /me（期限切れなど）か、ほかの画面からの移動（パスワードの変更・退会）。
  const [notice] = useState<LoginNotice | null>(
    () =>
      (location.state as { notice?: LoginNotice } | null)?.notice ??
      (state.status === "guest" ? state.notice : null),
  );
  useEffect(() => {
    clearNotice();
  }, [clearNotice]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

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
    if (found.email) return emailRef.current?.focus();
    if (found.password) return passwordRef.current?.focus();

    setSubmitting(true);
    try {
      const user = await api.post<Me>("/auth/login", { email: normalizedEmail, password: normalizedPassword });
      logIn(user);
      navigate(safeNext(next), { replace: true });
    } catch (error) {
      setSubmitting(false);
      setBanner(bannerForError(error) ?? MESSAGES.network);
    }
  }

  return (
    <main className="page">
      <AuthHeader title="ログイン" lead="おかえりなさい。" />
      {banner ? <ErrorBanner>{banner}</ErrorBanner> : notice && <InfoBanner>{NOTICES[notice]}</InfoBanner>}

      <form className="form" onSubmit={handleSubmit} noValidate>
        <TextField
          ref={emailRef}
          label="メールアドレス"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />
        <PasswordField
          ref={passwordRef}
          label="パスワード"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
        />
        <button type="submit" className="button button-primary" style={{ marginTop: 24 }} disabled={submitting}>
          ログイン
        </button>
      </form>

      <p className="switch-auth">
        はじめての方は <Link to={withNext("/register", next)}>新規登録</Link>
      </p>
    </main>
  );
}
