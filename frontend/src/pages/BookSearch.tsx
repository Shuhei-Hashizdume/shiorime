// 本の検索・登録（screens.md 2.、api.md 7-3・4章）。

import { ArrowLeft, ArrowSquareOut, Check, MagnifyingGlass, XCircle } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router";

import { booksApi, type CatalogItem, type ReadingStatus } from "../api/books";
import { ApiError } from "../api/client";
import { useUnauthorized } from "../auth/useUnauthorized";
import { BookCover } from "../components/BookCover";
import { ErrorBanner } from "../components/Feedback";
import { TextField } from "../components/Fields";
import { Sheet } from "../components/Sheet";
import { StatusChoice } from "../components/StatusChoice";
import { useToast } from "../components/Toast";
import { normalize } from "../lib/text";
import { bookFormErrorsFromServer, validateBookForm, type BookFormErrors } from "./bookForm";

type SearchState =
  | { kind: "idle" }
  | { kind: "searching" }
  | { kind: "results"; items: CatalogItem[]; nextOffset: number | null; q: string }
  | { kind: "error"; message: string; offerManual: boolean };

const SEARCH_ERRORS: Record<string, { message: string; offerManual: boolean }> = {
  BOOK_SEARCH_LIMIT: {
    message: "本の検索が混み合っています。時間をおいてお試しいただくか、手入力で追加してください。",
    offerManual: true,
  },
  SEARCH_RATE_LIMIT: { message: "検索の回数が多すぎます。1分ほど待ってから、もう一度お試しください。", offerManual: false },
};
const SEARCH_FAILED = { message: "本を検索できませんでした。時間をおいてもう一度お試しください。", offerManual: false };

export default function BookSearch() {
  const navigate = useNavigate();
  const location = useLocation();
  const onUnauthorized = useUnauthorized();
  const showToast = useToast();
  const fromShelf = (location.state as { fromShelf?: boolean } | null)?.fromShelf === true;

  const [query, setQuery] = useState("");
  const [state, setState] = useState<SearchState>({ kind: "idle" });
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  const [selected, setSelected] = useState<CatalogItem | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus({ preventScroll: true });
  }, []);

  function goBack() {
    // 本棚から来たときは、ブラウザの戻ると同じにする（選んでいた切り替え・スクロールの位置のまま戻る）
    if (fromShelf) navigate(-1);
    else navigate("/");
  }

  function searchError(error: unknown) {
    const code = error instanceof ApiError ? error.code : "";
    return SEARCH_ERRORS[code] ?? SEARCH_FAILED;
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    const q = normalize(query);
    if (q === "") return;
    inputRef.current?.blur(); // スマートフォンのキーボードを閉じて、結果を見やすくする
    setState({ kind: "searching" });
    setMoreError(null);
    try {
      const result = await booksApi.search(q, 0);
      setState({ kind: "results", items: result.items, nextOffset: result.next_offset, q });
    } catch (error) {
      if (onUnauthorized(error)) return;
      setState({ kind: "error", ...searchError(error) });
    }
  }

  async function handleMore() {
    if (state.kind !== "results" || state.nextOffset === null || loadingMore) return;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const result = await booksApi.search(state.q, state.nextOffset);
      setState({ ...state, items: [...state.items, ...result.items], nextOffset: result.next_offset });
    } catch (error) {
      if (onUnauthorized(error)) return;
      setMoreError(searchError(error).message);
    } finally {
      setLoadingMore(false);
    }
  }

  function handlePick(item: CatalogItem) {
    if (item.shelf_book_id) navigate(`/books/${item.shelf_book_id}`);
    else setSelected(item);
  }

  function handleAdded(bookId: string) {
    showToast("本棚に追加しました");
    // 履歴の検索画面を本の詳細で置き換え、本の詳細の戻るで本棚に戻るようにする（screens.md 3.）
    navigate(`/books/${bookId}`, { replace: true });
  }

  function handleAlreadyOnShelf(bookId: string) {
    navigate(`/books/${bookId}`, { replace: true, state: { alreadyOnShelf: true } });
  }

  const manualHint = (
    <div className="manual-hint">
      <button type="button" className="button button-secondary" onClick={() => setManualOpen(true)}>
        手入力で追加する
      </button>
      <p className="hint">※検索で見つからない本は、タイトルと著者を入力して追加できます。</p>
    </div>
  );

  return (
    <main className="page page-with-tabs">
      <div className="topbar">
        <button type="button" className="icon-button" aria-label="戻る" onClick={goBack}>
          <ArrowLeft size={24} aria-hidden="true" />
        </button>
        <h1 className="topbar-title">本を追加</h1>
      </div>

      <form role="search" onSubmit={handleSearch} className="search-form">
        <div className="input-wrap search-box">
          <MagnifyingGlass size={20} aria-hidden="true" className="search-icon" />
          <input
            ref={inputRef}
            className="input"
            type="search"
            enterKeyHint="search"
            placeholder="タイトルで検索"
            aria-label="タイトルで検索"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button
              type="button"
              className="icon-button"
              aria-label="消す"
              onClick={() => {
                setQuery("");
                inputRef.current?.focus();
              }}
            >
              <XCircle size={22} weight="fill" aria-hidden="true" />
            </button>
          )}
        </div>
      </form>

      {state.kind === "idle" && (
        <>
          <p className="state-text">本のタイトルや著者名を入れて、キーボードの「検索」を押してください。</p>
          {manualHint}
        </>
      )}

      {state.kind === "searching" && (
        <ul className="result-list" aria-busy="true" aria-label="検索中">
          {Array.from({ length: 5 }, (_, i) => (
            <li key={i} className="result-row">
              <div className="skeleton result-cover" />
              <div className="result-skeleton-text">
                <div className="skeleton skeleton-line" />
                <div className="skeleton skeleton-line short" />
              </div>
            </li>
          ))}
        </ul>
      )}

      {state.kind === "error" && (
        <>
          <ErrorBanner>{state.message}</ErrorBanner>
          {manualHint}
        </>
      )}

      {state.kind === "results" && state.items.length === 0 && (
        <div className="state-box">
          <h2 className="state-title">見つかりませんでした</h2>
          <p>言葉を短くしたり、著者名で探したりすると見つかることがあります。</p>
          {manualHint}
        </div>
      )}

      {state.kind === "results" && state.items.length > 0 && (
        <>
          <div className="result-head">
            <h2 className="result-heading">検索結果</h2>
            {/* 公開前に Google が配っている画像に差し替える（api.md 4-3） */}
            <span className="powered-by">Powered by Google</span>
          </div>
          <ul className="result-list">
            {state.items.map((item) => (
              <li key={item.google_volume_id} className="result-row">
                <button type="button" className="result-main" onClick={() => handlePick(item)}>
                  <BookCover url={item.cover_url} className="result-cover" />
                  <span className="result-text">
                    <span className="result-title">{item.title}</span>
                    {item.authors && <span className="result-meta">{item.authors}</span>}
                    {item.published_year && <span className="result-meta">{item.published_year}年</span>}
                    {item.shelf_book_id && (
                      <span className="on-shelf">
                        <Check size={12} weight="bold" aria-hidden="true" />
                        本棚にあります
                      </span>
                    )}
                  </span>
                </button>
                {item.info_link && (
                  <a className="google-link" href={item.info_link} target="_blank" rel="noopener noreferrer">
                    Google Books で見る
                    <ArrowSquareOut size={12} aria-hidden="true" />
                  </a>
                )}
              </li>
            ))}
          </ul>
          {moreError && <ErrorBanner>{moreError}</ErrorBanner>}
          {state.nextOffset !== null && (
            <button
              type="button"
              className="button button-secondary more-button"
              onClick={() => void handleMore()}
              disabled={loadingMore}
            >
              もっと見る
            </button>
          )}
          {manualHint}
        </>
      )}

      {selected && (
        <CatalogAddSheet
          item={selected}
          onClose={() => setSelected(null)}
          onAdded={handleAdded}
          onAlreadyOnShelf={handleAlreadyOnShelf}
          onUnauthorized={onUnauthorized}
        />
      )}
      {manualOpen && (
        <ManualAddSheet
          initialTitle={normalize(query)}
          onClose={() => setManualOpen(false)}
          onAdded={handleAdded}
          onUnauthorized={onUnauthorized}
        />
      )}
    </main>
  );
}

// ---- 本棚に追加（検索結果から） ----

function CatalogAddSheet({
  item,
  onClose,
  onAdded,
  onAlreadyOnShelf,
  onUnauthorized,
}: {
  item: CatalogItem;
  onClose: () => void;
  onAdded: (bookId: string) => void;
  onAlreadyOnShelf: (bookId: string) => void;
  onUnauthorized: (error: unknown) => boolean;
}) {
  const [status, setStatus] = useState<ReadingStatus>("reading");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd() {
    setSubmitting(true);
    setError(null);
    try {
      const { id } = await booksApi.createFromCatalog({ google_volume_id: item.google_volume_id, status });
      onAdded(id);
    } catch (err) {
      setSubmitting(false);
      if (onUnauthorized(err)) return;
      if (err instanceof ApiError && err.code === "BOOK_ALREADY_ON_SHELF" && typeof err.details.book_id === "string") {
        onAlreadyOnShelf(err.details.book_id);
        return;
      }
      if (err instanceof ApiError && err.code === "BOOK_SEARCH_LIMIT") {
        // 押した本を見失わないよう、シートは閉じない（api.md 4-5）
        setError(SEARCH_ERRORS.BOOK_SEARCH_LIMIT.message);
        return;
      }
      setError("本棚に追加できませんでした。もう一度お試しください。");
    }
  }

  return (
    <Sheet title="本棚に追加" onClose={onClose} variant="auto">
      <div className="sheet-book">
        <BookCover url={item.cover_url} className="sheet-cover" />
        <div>
          <p className="sheet-book-title">{item.title}</p>
          {item.authors && <p className="result-meta">{item.authors}</p>}
          {item.published_year && <p className="result-meta">{item.published_year}年</p>}
        </div>
      </div>
      <StatusChoice value={status} onChange={setStatus} disabled={submitting} />
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="sheet-actions">
        <button type="button" className="button button-primary" onClick={() => void handleAdd()} disabled={submitting}>
          本棚に追加する
        </button>
        <button type="button" className="button button-ghost" onClick={onClose}>
          キャンセル
        </button>
      </div>
    </Sheet>
  );
}

// ---- 手入力で追加 ----

function ManualAddSheet({
  initialTitle,
  onClose,
  onAdded,
  onUnauthorized,
}: {
  initialTitle: string;
  onClose: () => void;
  onAdded: (bookId: string) => void;
  onUnauthorized: (error: unknown) => boolean;
}) {
  // タイトルには、検索した言葉を最初から入れておく
  const [title, setTitle] = useState(initialTitle);
  const [author, setAuthor] = useState("");
  const [status, setStatus] = useState<ReadingStatus>("reading");
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
      const { id } = await booksApi.createManual({ title: t, author: a || null, status });
      onAdded(id);
    } catch (err) {
      setSubmitting(false);
      if (onUnauthorized(err)) return;
      const fieldErrors = err instanceof ApiError ? bookFormErrorsFromServer(err) : null;
      if (fieldErrors) setErrors(fieldErrors);
      else setError("本棚に追加できませんでした。もう一度お試しください。");
    }
  }

  return (
    <Sheet title="手入力で追加" onClose={onClose} variant="auto">
      <form onSubmit={handleSubmit} noValidate>
        <div className="sheet-manual-head">
          <BookCover url={null} className="sheet-cover" />
        </div>
        <TextField label="タイトル（必須）" value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} data-autofocus />
        <TextField label="著者（任意）" value={author} onChange={(e) => setAuthor(e.target.value)} error={errors.author} />
        <StatusChoice value={status} onChange={setStatus} disabled={submitting} />
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="sheet-actions">
          <button type="submit" className="button button-primary" disabled={submitting}>
            本棚に追加する
          </button>
          <button type="button" className="button button-ghost" onClick={onClose}>
            キャンセル
          </button>
        </div>
      </form>
    </Sheet>
  );
}
