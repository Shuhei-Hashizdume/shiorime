// ウェルカム（screens.md 11.）。ログインしていない人が最初に開く画面。

import { useState } from "react";
import { Link } from "react-router";

import { LegalSheet, type LegalKind } from "../components/LegalSheet";
import { LogoVertical } from "../components/Logo";
import { QuoteIcon } from "../components/QuoteIcon";

export default function Welcome() {
  const [legal, setLegal] = useState<LegalKind | null>(null);

  return (
    <main className="page welcome">
      <LogoVertical />

      <h1 className="catch">
        今夜の栞を、
        <br />
        明日の芽に。
      </h1>
      <p className="welcome-sub">
        心に残った気づきを書き留めると、
        <br />
        AIが問いかけ、次の一歩にしてくれます。
      </p>

      {/* 使い方の見本（文章は仮） */}
      <ol className="demo" aria-label="使い方の見本">
        <li className="demo-step">
          <p className="demo-who">あなたの気づき</p>
          <div className="demo-card">
            <div className="ribbon" aria-hidden="true" />
            <p className="demo-book">嫌われる勇気　P.142</p>
            <p className="quote">
              <QuoteIcon />
              他者の課題には踏み込まない
            </p>
            <p>上司の機嫌を自分の責任だと思い込んで、会議で黙ってしまう。</p>
          </div>
        </li>
        <li className="demo-step">
          <p className="demo-who">AIからの深掘り</p>
          <div className="demo-card ai">
            <p>黙ってしまう直前、頭の中ではどんな言葉が浮かんでいますか？</p>
          </div>
        </li>
        <li className="demo-step now">
          <p className="demo-who">次の一歩</p>
          <div className="demo-card">
            <ol className="demo-plan">
              <li>次の会議で、結論から一言だけ発言する</li>
              <li>発言したあとの気持ちを1行メモする</li>
            </ol>
          </div>
        </li>
      </ol>

      <div className="welcome-actions">
        <Link className="button button-primary" to="/register">
          はじめる（新規登録）
        </Link>
        <Link className="button button-secondary" to="/login">
          ログイン
        </Link>
      </div>

      <nav className="legal-links" aria-label="規約">
        <button type="button" className="text-link" onClick={() => setLegal("terms")}>
          利用規約
        </button>
        <button type="button" className="text-link" onClick={() => setLegal("privacy")}>
          プライバシーポリシー
        </button>
      </nav>

      {legal && <LegalSheet kind={legal} onClose={() => setLegal(null)} />}
    </main>
  );
}
