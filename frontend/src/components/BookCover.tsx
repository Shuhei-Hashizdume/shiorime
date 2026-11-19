// 本の表紙。表紙がない本・手入力の本・読み込めなかった表紙は、アプリのアイコンと同じ絵にする（要件定義書 5.2）。

import { useState } from "react";

import { Mark } from "./Logo";

export function BookCover({ url, className = "" }: { url: string | null; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (!url || failed) {
    return (
      <div className={`cover cover-icon ${className}`} aria-hidden="true">
        <Mark size={48} />
      </div>
    );
  }
  return (
    <img
      className={`cover ${className}`}
      src={url}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}
