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
