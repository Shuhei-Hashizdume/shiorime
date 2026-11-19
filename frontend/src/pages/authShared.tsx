// 新規登録・ログインで共通の部品と文（screens.md 10.）。

import { ArrowLeft } from "@phosphor-icons/react";
import { Link } from "react-router";

import { ApiError, NETWORK_ERROR, type FieldError } from "../api/client";
import { LogoHorizontal } from "../components/Logo";

export function AuthHeader({ title, lead }: { title: string; lead: string }) {
  return (
    <>
      <div className="topbar">
        <Link to="/welcome" className="icon-button" aria-label="戻る">
          <ArrowLeft size={24} aria-hidden="true" />
        </Link>
      </div>
      <LogoHorizontal />
      <h1 className="title">{title}</h1>
      <p className="lead">{lead}</p>
    </>
  );
}

export const MESSAGES = {
  emailRequired: "メールアドレスを入力してください",
  emailFormat: "メールアドレスの形式で入力してください",
  emailTooLong: "254文字以内で入力してください",
  emailTaken: "このメールアドレスは既に登録されています。ログインしてください。",
  passwordRequired: "パスワードを入力してください",
  passwordLength: "8〜128文字で入力してください",
  attributeRequired: "あてはまるものを1つ選んでください",
  agreeRequired: "同意すると登録できます",
  invalidCredentials: "メールアドレスまたはパスワードが正しくありません。",
  loginRateLimit: "ログインの試行回数が多すぎます。1分ほど待ってから、もう一度お試しください。",
  registerRateLimit: "新規登録の回数が多すぎます。しばらく時間をおいてから、もう一度お試しください。",
  network: "通信できませんでした。時間をおいてもう一度お試しください。",
} as const;

export const NOTICES = {
  expired: "ログインの有効期限が切れました。もう一度ログインしてください。",
  revoked: "パスワードが変更されたため、もう一度ログインしてください。",
  password_changed: "パスワードを変更しました。新しいパスワードでログインしてください。",
  withdrawn: "退会しました。ご利用ありがとうございました。",
} as const;

export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;
export const EMAIL_MAX = 254;

/** 欄ごとの誤り（サーバーの error.fields）を、画面の文に直す。 */
export function messageForField(error: FieldError): string {
  switch (error.field) {
    case "email":
      if (error.reason === "required") return MESSAGES.emailRequired;
      if (error.reason === "too_long") return MESSAGES.emailTooLong;
      return MESSAGES.emailFormat;
    case "password":
      if (error.reason === "required") return MESSAGES.passwordRequired;
      return MESSAGES.passwordLength;
    case "attribute":
      return MESSAGES.attributeRequired;
    case "agreed_to_terms":
      return MESSAGES.agreeRequired;
    default:
      return MESSAGES.network;
  }
}

/** 画面の上に出すエラーの文。欄の下に出すもの（422 など）は null。 */
export function bannerForError(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.code === NETWORK_ERROR) return MESSAGES.network;
  switch (error.code) {
    case "INVALID_CREDENTIALS":
      return MESSAGES.invalidCredentials;
    case "LOGIN_RATE_LIMIT":
      return MESSAGES.loginRateLimit;
    case "REGISTER_RATE_LIMIT":
      return MESSAGES.registerRateLimit;
    case "VALIDATION_ERROR":
    case "EMAIL_ALREADY_REGISTERED":
      return null;
    default:
      return MESSAGES.network;
  }
}
