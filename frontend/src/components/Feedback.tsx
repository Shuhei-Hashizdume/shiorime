// エラーとお知らせの表示（visual.md 3章：色だけで伝えず、記号と文を添える）。

import { Info, WarningCircle } from "@phosphor-icons/react";
import type { ReactNode } from "react";

export function FieldErrorText({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p className="field-error" id={id}>
      <WarningCircle size={16} aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

/** 画面の上のエラー（夕焼けの枠） */
export function ErrorBanner({ children }: { children: ReactNode }) {
  return (
    <div className="banner banner-error" role="alert">
      <WarningCircle size={18} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

/** 画面の上のお知らせ（灯りの色の枠） */
export function InfoBanner({ children }: { children: ReactNode }) {
  return (
    <div className="banner banner-info" role="status">
      <Info size={18} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

/**
 * 見出しと説明のあるお知らせ（api.md 2-4）。
 * calm：決まりどおりに止まった（回数・上限・処理中）／error：本当に失敗した（夕焼けの枠）
 */
export function Notice({ tone, title, children }: { tone: "calm" | "error"; title: string; children: ReactNode }) {
  const Icon = tone === "error" ? WarningCircle : Info;
  return (
    <div className={`notice notice-${tone}`} role={tone === "error" ? "alert" : "status"}>
      <Icon size={18} aria-hidden="true" />
      <div>
        <b className="notice-title">{title}</b>
        <p>{children}</p>
      </div>
    </div>
  );
}
