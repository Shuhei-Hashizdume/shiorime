// 本の詳細（screens.md 3.、api.md 7-3）。

import { ArrowLeft, CaretRight, DotsThreeVertical, Plus } from "@phosphor-icons/react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { booksApi, type BookDetail as Book, type ReadingStatus } from "../api/books";
import { ApiError } from "../api/client";
import { useUnauthorized } from "../auth/useUnauthorized";
import { BookCover } from "../components/BookCover";
import { ErrorBanner, InfoBanner } from "../components/Feedback";
import { TextField } from "../components/Fields";
import { Sheet } from "../components/Sheet";
import { StatusChoice } from "../components/StatusChoice";
import { useToast } from "../components/Toast";
import { normalize } from "../lib/text";
import { bookFormErrorsFromServer, validateBookForm, type BookFormErrors } from "./bookForm";

type LoadState = { kind: "loading" } | { kind: "ready"; book: Book } | { kind: "not_found" } | { kind: "error" };
type OpenSheet = "menu" | "edit" | "delete" | null;

const STATUS_TOASTS: Record<ReadingStatus, string> = {
  finished: "読了にしました（本棚の「読了」に移りました）",
  reading: "読書中にしました",
};

export default function BookDetail() {
  const { bookId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const onUnauthorized = useUnauthorized();
  const showToast = useToast();
  // 既に本棚にある本を追加しようとして移ってきたとき（screens.md 2.・3.）
  const [alreadyOnShelf] = useState(
    () => (location.state as { alreadyOnShelf?: boolean } | null)?.alreadyOnShelf === true,
  );

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [statusSaving, setStatusSaving] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<OpenSheet>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      setState({ kind: "ready", book: await booksApi.get(bookId) });
    } catch (error) {
      if (onUnauthorized(error)) return;
      // 削除済み・他人の本・存在しない ID・ID の形が違う、はどれも同じ表示にする
      if (error instanceof ApiError && (error.status === 404 || error.status === 422)) setState({ kind: "not_found" });
      else setState({ kind: "error" });
    }
  }, [bookId, onUnauthorized]);

  useEffect(() => {
    void load();
  }, [load]);

  function goBack() {
    // アプリの中から来たときは前の画面へ。URL を直接開いたときは本棚へ
    if (location.key !== "default") navigate(-1);
    else navigate("/");
  }

  async function changeStatus(next: ReadingStatus) {
    if (state.kind !== "ready" || statusSaving || state.book.status === next) return;
    const before = state.book;
    // すぐ表示を変え、失敗したら元に戻す（画面の表示と保存の内容をずらさないため）
    setState({ kind: "ready", book: { ...before, status: next } });
    setStatusSaving(true);
    setStatusError(null);
    try {
      const saved = await booksApi.updateStatus(before.id, next);
      setState({ kind: "ready", book: saved });
      showToast(STATUS_TOASTS[next]);
    } catch (error) {
      setState({ kind: "ready", book: before });
      if (onUnauthorized(error)) return;
      if (error instanceof ApiError && error.status === 404) setState({ kind: "not_found" });
      else setStatusError("読書ステータスを変更できませんでした。もう一度お試しください。");
    } finally {
      setStatusSaving(false);
    }
  }

  return (
    <main className="page page-with-tabs">
      <div className="topbar topbar-between">
        <button type="button" className="icon-button" aria-label="戻る" onClick={goBack}>
          <ArrowLeft size={24} aria-hidden="true" />
        </button>
        {state.kind === "ready" && (
          <button type="button" className="icon-button" aria-label="メニュー" onClick={() => setSheet("menu")}>
            <DotsThreeVertical size={24} weight="bold" aria-hidden="true" />
          </button>
        )}
      </div>

      {state.kind === "loading" && (
        <div className="book-hero" aria-busy="true" aria-label="読み込み中">
          <div className="skeleton detail-cover" />
          <div className="skeleton skeleton-line" style={{ width: "60%", marginTop: 16 }} />
          <div className="skeleton skeleton-pill" />
        </div>
      )}

      {state.kind === "not_found" && (
        <div className="state-box">
          <h1 className="state-title">この本は見つかりませんでした</h1>
          <Link to="/" className="button button-secondary">
            本棚へ戻る
          </Link>
        </div>
      )}

      {state.kind === "error" && (
        <div className="state-box">
          <p>本を読み込めませんでした。時間をおいてもう一度お試しください。</p>
          <button type="button" className="button button-secondary" onClick={() => void load()}>
            もう一度読み込む
          </button>
        </div>
      )}

      {state.kind === "ready" && (
        <>
          {alreadyOnShelf && <InfoBanner>この本は既に本棚にあります</InfoBanner>}
          <div className="book-hero">
            <BookCover url={state.book.cover_url} className="detail-cover" />
            <h1 className="detail-title">{state.book.title}</h1>
            {state.book.author && <p className="detail-author">{state.book.author}</p>}
          </div>

          <StatusChoice value={state.book.status} onChange={(s) => void changeStatus(s)} disabled={statusSaving} />
          {statusError && <ErrorBanner>{statusError}</ErrorBanner>}

          <section className="card insight-summary" aria-label="この本の気づき">
            <div className="insight-summary-head">
              <h2 className="card-title">この本の気づき</h2>
              <span className="count">{state.book.insight_count}件</span>
            </div>
            {state.book.insight_count > 0 ? (
              <Link to={`/insight-groups/${state.book.id}`} className="row-link">
                この本の気づきを見る
                <CaretRight size={18} aria-hidden="true" />
              </Link>
            ) : (
              <p className="card-note">心に残った一文や、読んで考えたことを書き留めてみましょう。</p>
            )}
          </section>

          <Link to={`/insights/new?book=${state.book.id}`} className="button button-primary write-button">
            <Plus size={20} weight="bold" aria-hidden="true" />
            気づきを書く
          </Link>
        </>
      )}

      {state.kind === "ready" && sheet === "menu" && (
        <Sheet title="本のメニュー" onClose={() => setSheet(null)} variant="auto" showHeader={false}>
          <div className="menu-list">
            {state.book.google_volume_id === null && (
              <button type="button" className="menu-item" onClick={() => setSheet("edit")}>
                本の情報を編集
              </button>
            )}
            <button type="button" className="menu-item danger" onClick={() => setSheet("delete")}>
              本棚から削除
            </button>
            <button type="button" className="menu-item" onClick={() => setSheet(null)}>
              キャンセル
            </button>
          </div>
        </Sheet>
      )}

      {state.kind === "ready" && sheet === "edit" && (
        <EditSheet
          book={state.book}
          onClose={() => setSheet(null)}
          onSaved={(book) => {
            setState({ kind: "ready", book });
            setSheet(null);
            showToast("本の情報を変更しました");
          }}
          onNotFound={() => {
            setSheet(null);
            setState({ kind: "not_found" });
          }}
          onUnauthorized={onUnauthorized}
        />
      )}

      {state.kind === "ready" && sheet === "delete" && (
        <DeleteSheet
          book={state.book}
          onClose={() => setSheet(null)}
          onDeleted={(showDone) => {
            if (showDone) showToast("本棚から削除しました");
            navigate("/", { replace: true });
          }}
          onUnauthorized={onUnauthorized}
        />
      )}
    </main>
  );
}

function EditSheet({
  book,
  onClose,
  onSaved,
  onNotFound,
  onUnauthorized,
}: {
  book: Book;
  onClose: () => void;
  onSaved: (book: Book) => void;
  onNotFound: () => void;
  onUnauthorized: (error: unknown) => boolean;
}) {
  // 今の値を最初から入れておく
  const [title, setTitle] = useState(book.title);
  const [author, setAuthor] = useState(book.author ?? "");
  const [errors, setErrors] = useState<BookFormErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const t = normalize(title);
    const a = normalize(author);
    const found = validateBookForm(t, a);
    setErrors(found);
    setError(null);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      onSaved(await booksApi.update(book.id, { title: t, author: a || null }));
    } catch (err) {
      setSubmitting(false);
      if (onUnauthorized(err)) return;
      if (err instanceof ApiError && err.status === 404) return onNotFound();
      const fieldErrors = err instanceof ApiError ? bookFormErrorsFromServer(err) : null;
      if (fieldErrors) setErrors(fieldErrors);
      else setError("保存できませんでした。もう一度お試しください。");
    }
  }

  return (
    <Sheet title="本の情報を編集" onClose={onClose} variant="auto">
      <form onSubmit={handleSubmit} noValidate>
        <TextField label="タイトル（必須）" value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} data-autofocus />
        <TextField label="著者（任意）" value={author} onChange={(e) => setAuthor(e.target.value)} error={errors.author} />
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="sheet-actions">
          <button type="submit" className="button button-primary" disabled={submitting}>
            保存する
          </button>
          <button type="button" className="button button-ghost" onClick={onClose}>
            キャンセル
          </button>
        </div>
      </form>
    </Sheet>
  );
}

function DeleteSheet({
  book,
  onClose,
  onDeleted,
  onUnauthorized,
}: {
  book: Book;
  onClose: () => void;
  onDeleted: (showDone: boolean) => void;
  onUnauthorized: (error: unknown) => boolean;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setSubmitting(true);
    setError(null);
    try {
      await booksApi.remove(book.id);
      onDeleted(true);
    } catch (err) {
      setSubmitting(false);
      if (onUnauthorized(err)) return;
      // すでに削除されていた（404）なら、したかった「本がない状態」になっているので、エラーにせず本棚へ
      if (err instanceof ApiError && err.status === 404) return onDeleted(false);
      setError("削除できませんでした。もう一度お試しください。");
    }
  }

  return (
    <Sheet title="この本を本棚から削除しますか？" onClose={onClose} variant="auto" showHeader={false}>
      <div className="confirm">
        <p className="confirm-title">この本を本棚から削除しますか？</p>
        <p className="confirm-text">この本の気づきは、気づき一覧に残ります。</p>
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="sheet-actions">
          <button type="button" className="button button-danger" onClick={() => void handleDelete()} disabled={submitting}>
            削除する
          </button>
          <button type="button" className="button button-ghost" onClick={onClose}>
            キャンセル
          </button>
        </div>
      </div>
    </Sheet>
  );
}
