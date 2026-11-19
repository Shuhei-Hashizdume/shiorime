// 新規登録（screens.md 10.、api.md 7-1）。

import { Check } from "@phosphor-icons/react";
import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { api, ApiError, ATTRIBUTE_LABELS, type Attribute, type Me } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { withNext } from "../auth/next";
import { ErrorBanner, FieldErrorText } from "../components/Feedback";
import { PasswordField, TextField } from "../components/Fields";
import { LegalSheet, type LegalKind } from "../components/LegalSheet";
import { countChars, normalize } from "../lib/text";
import {
  AuthHeader,
  bannerForError,
  EMAIL_MAX,
  MESSAGES,
  messageForField,
  PASSWORD_MAX,
  PASSWORD_MIN,
} from "./authShared";

type Field = "email" | "password" | "attribute" | "agreed_to_terms";
type Errors = Partial<Record<Field, string>>;

const ATTRIBUTES = Object.keys(ATTRIBUTE_LABELS) as Attribute[];

// ボタンを押したときの確かめ。サーバーでも同じ内容を確かめる。
function validate(email: string, password: string, attribute: Attribute | null, agreed: boolean): Errors {
  const errors: Errors = {};
  if (email === "") errors.email = MESSAGES.emailRequired;
  else if (countChars(email) > EMAIL_MAX) errors.email = MESSAGES.emailTooLong;
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = MESSAGES.emailFormat;

  const passwordLength = countChars(password);
  if (password === "") errors.password = MESSAGES.passwordRequired;
  else if (passwordLength < PASSWORD_MIN || passwordLength > PASSWORD_MAX) errors.password = MESSAGES.passwordLength;

  if (!attribute) errors.attribute = MESSAGES.attributeRequired;
  if (!agreed) errors.agreed_to_terms = MESSAGES.agreeRequired;
  return errors;
}

export default function Register() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = searchParams.get("next");
  const { logIn } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [attribute, setAttribute] = useState<Attribute | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [legal, setLegal] = useState<LegalKind | null>(null);

  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const attributeRef = useRef<HTMLInputElement>(null);
  const agreeRef = useRef<HTMLInputElement>(null);

  function focusFirstError(found: Errors) {
    const order: [Field, HTMLInputElement | null][] = [
      ["email", emailRef.current],
      ["password", passwordRef.current],
      ["attribute", attributeRef.current],
      ["agreed_to_terms", agreeRef.current],
    ];
    order.find(([field]) => found[field])?.[1]?.focus();
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;

    const normalizedEmail = normalize(email).toLowerCase();
    const normalizedPassword = normalize(password);
    const found = validate(normalizedEmail, normalizedPassword, attribute, agreed);
    setErrors(found);
    setBanner(null);
    if (Object.keys(found).length > 0) {
      focusFirstError(found);
      return;
    }

    setSubmitting(true);
    try {
      const user = await api.post<Me>("/auth/register", {
        email: normalizedEmail,
        password: normalizedPassword,
        attribute,
        agreed_to_terms: agreed,
      });
      logIn(user);
      // 新しいアカウントには本も気づきもないので、next は使わず本棚へ（api.md 3-5）
      navigate("/", { replace: true });
    } catch (error) {
      setSubmitting(false);
      if (error instanceof ApiError && error.code === "EMAIL_ALREADY_REGISTERED") {
        const taken = { email: MESSAGES.emailTaken };
        setErrors(taken);
        focusFirstError(taken);
        return;
      }
      if (error instanceof ApiError && error.code === "VALIDATION_ERROR") {
        const fromServer: Errors = {};
        for (const fieldError of error.fields) {
          fromServer[fieldError.field as Field] ??= messageForField(fieldError);
        }
        setErrors(fromServer);
        focusFirstError(fromServer);
        return;
      }
      setBanner(bannerForError(error));
    }
  }

  return (
    <main className="page">
      <AuthHeader title="はじめる" lead="アカウントを作って、気づきを残しましょう。" />
      {banner && <ErrorBanner>{banner}</ErrorBanner>}

      <form className="form" onSubmit={handleSubmit} noValidate>
        <TextField
          ref={emailRef}
          label="メールアドレス"
          type="email"
          inputMode="email"
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />
        <PasswordField
          ref={passwordRef}
          label="パスワード"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint="8〜128文字（前後の空白は取り除かれます）"
          error={errors.password}
        />

        <fieldset className="field-group" style={{ border: 0, padding: 0, margin: "16px 0 0" }}>
          <legend className="label" style={{ padding: 0 }}>
            あなたについて（AI提案に使います）
          </legend>
          <div
            className={`chips${errors.attribute ? " invalid" : ""}`}
            aria-describedby={errors.attribute ? "attribute-error" : undefined}
          >
            {ATTRIBUTES.map((value, index) => (
              <label className="chip" key={value}>
                <input
                  ref={index === 0 ? attributeRef : undefined}
                  type="radio"
                  name="attribute"
                  value={value}
                  checked={attribute === value}
                  onChange={() => setAttribute(value)}
                />
                <span>{ATTRIBUTE_LABELS[value]}</span>
              </label>
            ))}
          </div>
          {errors.attribute && <FieldErrorText id="attribute-error">{errors.attribute}</FieldErrorText>}
        </fieldset>

        <div className="agree">
          <span className={`checkbox${errors.agreed_to_terms ? " invalid" : ""}`}>
            <input
              ref={agreeRef}
              id="agree"
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              aria-describedby={errors.agreed_to_terms ? "agree-error" : undefined}
            />
            <span className="box" aria-hidden="true">
              {agreed && <Check size={16} weight="bold" />}
            </span>
          </span>
          <span>
            <button type="button" className="text-link" onClick={() => setLegal("terms")}>
              利用規約
            </button>
            と
            <button type="button" className="text-link" onClick={() => setLegal("privacy")}>
              プライバシーポリシー
            </button>
            に<label htmlFor="agree">同意します</label>
          </span>
        </div>
        {errors.agreed_to_terms && <FieldErrorText id="agree-error">{errors.agreed_to_terms}</FieldErrorText>}

        <button type="submit" className="button button-primary" style={{ marginTop: 24 }} disabled={submitting}>
          はじめる
        </button>
      </form>

      <p className="switch-auth">
        アカウントをお持ちの方は <Link to={withNext("/login", next)}>ログイン</Link>
      </p>

      {legal && <LegalSheet kind={legal} onClose={() => setLegal(null)} />}
    </main>
  );
}
