// 本棚（screens.md 1.、api.md 7-3）。

import { Check, Plus } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import { booksApi, STATUS_LABELS, type BookListItem, type ReadingStatus } from "../api/books";
import { useUnauthorized } from "../auth/useUnauthorized";
import { BookCover } from "../components/BookCover";
import { Mark } from "../components/Logo";

type Filter = ReadingStatus | "all";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "reading", label: "読書中" },
  { key: "finished", label: "読了" },
  { key: "all", label: "すべて" },
];

type LoadState = "loading" | "ready" | "error";

function parseFilter(value: string | null): Filter {
  return value === "finished" || value === "all" ? value : "reading";
}

export default function Shelf() {
  const [searchParams, setSearchParams] = useSearchParams();
  // 選んだ切り替えは URL に入れる。戻るボタンで戻ったとき、選んでいた切り替えのまま戻るため
  const filter = parseFilter(searchParams.get("status"));
  const onUnauthorized = useUnauthorized();
  const location = useLocation();
  // 本の追加の画面から戻るとき、選んでいた切り替えのまま戻るため
  const fromShelf = { fromShelf: true, back: location.pathname + location.search };

  const [books, setBooks] = useState<BookListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [hasAnyBook, setHasAnyBook] = useState(true);
  const [cursor, setCursor] = useState<string | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [moreState, setMoreState] = useState<"idle" | "loading" | "error">("idle");
  const requestId = useRef(0);

  const loadFirst = useCallback(async () => {
    const id = ++requestId.current;
    setState("loading");
    setBooks([]);
    setCursor(null);
    setMoreState("idle");
    try {
      const status = filter === "all" ? null : filter;
      const page = await booksApi.list(status, null);
      // 「本がまだない」と「選んだ切り替えの本がない」を見分けるため、0冊のときは全部の冊数も確かめる
      let anyBook = page.total > 0;
      if (!anyBook && status) anyBook = (await booksApi.list(null, null)).total > 0;
      if (id !== requestId.current) return;
      setBooks(page.items);
      setTotal(page.total);
      setCursor(page.next_cursor);
      setHasAnyBook(anyBook);
      setState("ready");
    } catch (error) {
      if (id !== requestId.current || onUnauthorized(error)) return;
      setState("error");
    }
  }, [filter, onUnauthorized]);

  useEffect(() => {
    void loadFirst();
  }, [loadFirst]);

  const loadMore = useCallback(async () => {
    if (!cursor || moreState === "loading") return;
    const id = requestId.current;
    setMoreState("loading");
    try {
      const page = await booksApi.list(filter === "all" ? null : filter, cursor);
      if (id !== requestId.current) return;
      setBooks((prev) => [...prev, ...page.items]);
      setTotal(page.total);
      setCursor(page.next_cursor);
      setMoreState("idle");
    } catch (error) {
      if (id !== requestId.current || onUnauthorized(error)) return;
      setMoreState("error");
    }
  }, [cursor, filter, moreState, onUnauthorized]);

  // 一覧の下までスクロールしたら、次の30冊を自動で読み込む
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !cursor || moreState !== "idle") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) void loadMore();
    }, { rootMargin: "200px" });
    observer.observe(el);
    return () => observer.disconnect();
  }, [cursor, moreState, loadMore]);

  function selectFilter(next: Filter) {
    setSearchParams(next === "reading" ? {} : { status: next }, { replace: true });
  }

  const showControls = state !== "ready" || hasAnyBook;
  const showFab = state === "ready" && books.length > 0;

  return (
    <main className="page page-with-tabs">
      <div className="shelf-head">
        <h1 className="title">本棚</h1>
        {state === "ready" && hasAnyBook && <span className="count">{total}冊</span>}
      </div>

      {showControls && (
        <div className="segments" role="group" aria-label="読書ステータスで絞り込む">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className={`segment${filter === key ? " on" : ""}`}
              aria-pressed={filter === key}
              onClick={() => selectFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {state === "loading" && (
        <div className="book-grid" aria-busy="true" aria-label="読み込み中">
          {Array.from({ length: 9 }, (_, i) => (
            <div key={i}>
              <div className="skeleton skeleton-cover" />
              <div className="skeleton skeleton-line" />
            </div>
          ))}
        </div>
      )}

      {state === "error" && (
        <div className="state-box">
          <p>本棚を読み込めませんでした。時間をおいてもう一度お試しください。</p>
          <button type="button" className="button button-secondary" onClick={() => void loadFirst()}>
            もう一度読み込む
          </button>
        </div>
      )}

      {state === "ready" && !hasAnyBook && (
        <div className="empty">
          <Mark size={96} />
          <h2>最初の1冊を、本棚に。</h2>
          <p>いま読んでいる本や、気になっている本を追加しましょう。</p>
          <Link to="/books/add" state={fromShelf} className="button button-primary">
            本を追加する
          </Link>
        </div>
      )}

      {state === "ready" && hasAnyBook && books.length === 0 && (
        <div className="empty">
          <h2>{STATUS_LABELS[filter as ReadingStatus] ?? "すべて"}の本はありません</h2>
          {filter === "reading" && <p>読み終えた本は「読了」で見られます。</p>}
          <Link to="/books/add" state={fromShelf} className="button button-primary">
            本を追加する
          </Link>
        </div>
      )}

      {state === "ready" && books.length > 0 && (
        <>
          <ul className="book-grid">
            {books.map((book) => (
              <li key={book.id}>
                <Link to={`/books/${book.id}`} className="book-tile">
                  <BookCover url={book.cover_url} />
                  <span className="book-tile-title">{book.title}</span>
                  <span className="book-tile-status">
                    {book.status === "finished" && <Check size={12} weight="bold" aria-hidden="true" />}
                    {STATUS_LABELS[book.status]}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <div ref={sentinel} />
          {moreState === "loading" && <p className="more-status">読み込み中…</p>}
          {moreState === "error" && (
            <div className="state-box">
              <p>読み込めませんでした</p>
              <button type="button" className="button button-secondary" onClick={() => setMoreState("idle")}>
                もう一度読み込む
              </button>
            </div>
          )}
        </>
      )}

      {showFab && (
        <Link to="/books/add" state={fromShelf} className="fab">
          <Plus size={20} weight="bold" aria-hidden="true" />
          本を追加
        </Link>
      )}
    </main>
  );
}
