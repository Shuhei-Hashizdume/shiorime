// プロフィール（screens.md 9.、api.md 7-2）。
// メールアドレス・属性は、アプリを開いたときに取った自分の情報（GET /me）を使う。
// 残り回数は開くたびに取り直す。表示の切り替えとログアウトは、読み込めなくても使える。

import { CaretRight } from "@phosphor-icons/react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { aiProposalsApi, type AiUsage } from "../api/aiProposals";
import { api, ApiError, ATTRIBUTE_LABELS, meApi, type Attribute } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useUnauthorized } from "../auth/useUnauthorized";
import { ErrorBanner } from "../components/Feedback";
import { PasswordField } from "../components/Fields";
import { LegalSheet, type LegalKind } from "../components/LegalSheet";
import { Sheet } from "../components/Sheet";
import { useToast } from "../components/Toast";
import { countChars, normalize } from "../lib/text";
import { applyTheme, readTheme, type ThemeChoice } from "../lib/theme";
import { MESSAGES, PASSWORD_MAX, PASSWORD_MIN } from "./authShared";

type SheetKind = "attribute" | "password" | "withdraw" | LegalKind | null;
type UsageState = { kind: "loading" } | { kind: "ready"; usage: AiUsage } | { kind: "error" };

const THEMES: { key: ThemeChoice; label: string }[] = [
  { key: "auto", label: "自動" },
  { key: "dark", label: "夜" },
  { key: "light", label: "朝" },
];

const RATE_LIMIT_TEXT = "パスワードの入力の失敗が続いたため、しばらく操作できません。1時間ほど待ってからお試しください。";

export default function Profile() {
  const { state, logIn, logOut } = useAuth();
  const navigate = useNavigate();
  const onUnauthorized = useUnauthorized();
  const [usage, setUsage] = useState<UsageState>({ kind: "loading" });
  const [theme, setTheme] = useState<ThemeChoice>(readTheme);
  const [sheet, setSheet] = useState<SheetKind>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  const loadUsage = useCallback(async () => {
    setUsage({ kind: "loading" });
    try {
      setUsage({ kind: "ready", usage: await aiProposalsApi.usage() });
    } catch (error) {
      if (onUnauthorized(error)) return;
      setUsage({ kind: "error" });
    }
  }, [onUnauthorized]);

  useEffect(() => {
    void loadUsage();
  }, [loadUsage]);

  if (state.status !== "user") return null;
  const user = state.user;

  function chooseTheme(choice: ThemeChoice) {
    setTheme(choice);
    applyTheme(choice);
  }

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await api.post("/auth/logout");
    } catch {
      // 通信できなくても、この端末ではログアウトした扱いにする
    }
    logOut();
    navigate("/login", { replace: true });
  }

  return (
    <main className="page page-with-tabs profile">
      <h1 className="title page-title">プロフィール</h1>

      <h2 className="group-label">アカウント</h2>
      <div className="settings">
        <div className="settings-item">
          <span>メールアドレス</span>
          <span className="settings-value ellipsis">{user.email}</span>
        </div>
        <button type="button" className="settings-item" onClick={() => setSheet("attribute")}>
          <span>属性</span>
          <span className="settings-value">
            {ATTRIBUTE_LABELS[user.attribute]}
            <CaretRight size={16} aria-hidden="true" />
          </span>
        </button>
        <button type="button" className="settings-item" onClick={() => setSheet("password")}>
          <span>パスワードを変更</span>
          <CaretRight size={16} aria-hidden="true" className="settings-caret" />
        </button>
      </div>

      <h2 className="group-label">表示</h2>
      <div className="settings">
        <div className="theme-choice" role="radiogroup" aria-label="表示">
          {THEMES.map((t) => (
            <button
              key={t.key}
              type="button"
              role="radio"
              aria-checked={theme === t.key}
              className={`theme-option${theme === t.key ? " on" : ""}`}
              onClick={() => chooseTheme(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="theme-note">自動：端末の設定（ダークモード）に合わせます</p>
      </div>

      <h2 className="group-label">今日のAI提案</h2>
      <div className="settings settings-text">
        {usage.kind === "loading" && <div className="skeleton skeleton-line" aria-label="読み込み中" />}
        {usage.kind === "error" && (
          <div>
            <p>プロフィールを読み込めませんでした。時間をおいてもう一度お試しください。</p>
            <button type="button" className="button button-secondary profile-retry" onClick={() => void loadUsage()}>
              もう一度読み込む
            </button>
          </div>
        )}
        {usage.kind === "ready" &&
          (usage.usage.app_limit_reached && usage.usage.remaining_today > 0 ? (
            <p>
              本日はAI提案の受付を終了しました。明日0時に再開します。
              <small>（気づきの登録は何件でもできます）</small>
            </p>
          ) : (
            <p>
              本日あと{usage.usage.remaining_today}回
              <small>毎日0時に回復します（気づきの登録は何件でもできます）</small>
            </p>
          ))}
      </div>

      <h2 className="group-label">その他</h2>
      <div className="settings">
        <button type="button" className="settings-item" onClick={() => setSheet("terms")}>
          <span>利用規約</span>
          <CaretRight size={16} aria-hidden="true" className="settings-caret" />
        </button>
        <button type="button" className="settings-item" onClick={() => setSheet("privacy")}>
          <span>プライバシーポリシー</span>
          <CaretRight size={16} aria-hidden="true" className="settings-caret" />
        </button>
      </div>

      {/* 押し間違いを防ぐため、ほかの設定と離して一番下に置く */}
      <div className="settings settings-bottom">
        <button type="button" className="settings-item" onClick={() => void handleLogout()} disabled={loggingOut}>
          <span>ログアウト</span>
        </button>
        <button type="button" className="settings-item danger" onClick={() => setSheet("withdraw")}>
          <span>退会する</span>
        </button>
      </div>

      {sheet === "attribute" && (
        <AttributeSheet
          current={user.attribute}
          onClose={() => setSheet(null)}
          onSaved={(updated) => logIn(updated)}
          onUnauthorized={onUnauthorized}
        />
      )}
      {sheet === "password" && (
        <PasswordSheet
          onClose={() => setSheet(null)}
          onDone={() => {
            logOut("password_changed");
            navigate("/login", { replace: true });
          }}
          onUnauthorized={onUnauthorized}
        />
      )}
      {sheet === "withdraw" && (
        <WithdrawSheet
          onClose={() => setSheet(null)}
          onDone={() => {
            logOut("withdrawn");
            navigate("/login", { replace: true });
          }}
          onUnauthorized={onUnauthorized}
        />
      )}
      {(sheet === "terms" || sheet === "privacy") && <LegalSheet kind={sheet} onClose={() => setSheet(null)} />}
    </main>
  );
}

function AttributeSheet({
  current,
  onClose,
  onSaved,
  onUnauthorized,
}: {
  current: Attribute;
  onClose: () => void;
  onSaved: (user: Awaited<ReturnType<typeof meApi.updateAttribute>>) => void;
  onUnauthorized: (error: unknown) => boolean;
}) {
  const showToast = useToast();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function choose(attribute: Attribute) {
    if (saving) return;
    if (attribute === current) return onClose();
    setSaving(true);
    setError(null);
    try {
      onSaved(await meApi.updateAttribute(attribute));
      showToast("属性を変更しました");
      onClose();
    } catch (err) {
      setSaving(false);
      if (onUnauthorized(err)) return;
      setError("変更できませんでした。もう一度お試しください。");
    }
  }

  return (
    <Sheet title="属性" onClose={onClose} variant="auto">
      <p className="confirm-text">AI提案を、あなたの毎日に合った内容にするために使います。</p>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="menu-list" role="radiogroup" aria-label="属性">
        {(Object.keys(ATTRIBUTE_LABELS) as Attribute[]).map((key) => (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={key === current}
            className={`menu-item attribute-option${key === current ? " on" : ""}`}
            onClick={() => void choose(key)}
            disabled={saving}
          >
            {ATTRIBUTE_LABELS[key]}
          </button>
        ))}
      </div>
      <div className="sheet-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          キャンセル
        </button>
      </div>
    </Sheet>
  );
}

type PasswordErrors = { current?: string; next?: string };

function PasswordSheet({
  onClose,
  onDone,
  onUnauthorized,
}: {
  onClose: () => void;
  onDone: () => void;
  onUnauthorized: (error: unknown) => boolean;
}) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [errors, setErrors] = useState<PasswordErrors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    const found: PasswordErrors = {};
    if (normalize(current) === "") found.current = MESSAGES.passwordRequired;
    const nextCount = countChars(normalize(next));
    if (nextCount === 0) found.next = MESSAGES.passwordRequired;
    else if (nextCount < PASSWORD_MIN || nextCount > PASSWORD_MAX) found.next = MESSAGES.passwordLength;
    setErrors(found);
    setBanner(null);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    try {
      await meApi.changePassword(current, next);
      onDone();
    } catch (err) {
      setSaving(false);
      if (onUnauthorized(err)) return;
      const code = err instanceof ApiError ? err.code : "";
      if (code === "CURRENT_PASSWORD_INCORRECT") setErrors({ current: "今のパスワードが正しくありません" });
      else if (code === "SAME_AS_CURRENT_PASSWORD") setErrors({ next: "今と同じパスワードは使えません" });
      else if (code === "PASSWORD_CONFIRM_RATE_LIMIT") setErrors({ current: RATE_LIMIT_TEXT });
      else if (code === "VALIDATION_ERROR" && err instanceof ApiError) {
        setErrors({
          current: err.fields.some((f) => f.field === "current_password") ? MESSAGES.passwordRequired : undefined,
          next: err.fields.some((f) => f.field === "new_password") ? MESSAGES.passwordLength : undefined,
        });
      } else setBanner("変更できませんでした。時間をおいてもう一度お試しください。");
    }
  }

  return (
    <Sheet title="パスワードを変更" onClose={onClose} variant="auto">
      <form className="form" onSubmit={handleSubmit} noValidate>
        {banner && <ErrorBanner>{banner}</ErrorBanner>}
        <PasswordField
          label="今のパスワード"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          error={errors.current}
          data-autofocus
        />
        <PasswordField
          label="新しいパスワード"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          error={errors.next}
          hint="8〜128文字（前後の空白は取り除かれます）"
        />
        <p className="confirm-text">変更すると、すべての端末からログアウトします。新しいパスワードでログインし直してください。</p>
        <div className="sheet-actions">
          <button type="submit" className="button button-primary" disabled={saving}>
            変更する
          </button>
          <button type="button" className="button button-secondary" onClick={onClose}>
            キャンセル
          </button>
        </div>
      </form>
    </Sheet>
  );
}

function WithdrawSheet({
  onClose,
  onDone,
  onUnauthorized,
}: {
  onClose: () => void;
  onDone: () => void;
  onUnauthorized: (error: unknown) => boolean;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    setBanner(null);
    if (normalize(password) === "") {
      setError(MESSAGES.passwordRequired);
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await meApi.withdraw(password);
      onDone();
    } catch (err) {
      setSaving(false);
      if (onUnauthorized(err)) return;
      const code = err instanceof ApiError ? err.code : "";
      if (code === "PASSWORD_INCORRECT") setError("パスワードが正しくありません");
      else if (code === "PASSWORD_CONFIRM_RATE_LIMIT") setError(RATE_LIMIT_TEXT);
      else if (code === "VALIDATION_ERROR") setError(MESSAGES.passwordRequired);
      else setBanner("退会できませんでした。時間をおいてもう一度お試しください。");
    }
  }

  return (
    <Sheet title="退会しますか？" onClose={onClose} variant="auto">
      <form className="form" onSubmit={handleSubmit} noValidate>
        <p className="confirm-text">本・気づき・次の一歩（AI提案）など、すべてのデータが削除され、元に戻せません。</p>
        {banner && <ErrorBanner>{banner}</ErrorBanner>}
        <PasswordField
          label="確認のため、パスワードを入力してください"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={error ?? undefined}
          data-autofocus
        />
        <div className="sheet-actions">
          <button type="submit" className="button button-danger" disabled={saving}>
            退会する
          </button>
          <button type="button" className="button button-secondary" onClick={onClose}>
            キャンセル
          </button>
        </div>
      </form>
    </Sheet>
  );
}
