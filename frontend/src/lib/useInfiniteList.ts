// カーソルで続きを読む一覧（本棚・気づき一覧・本ごとの気づき一覧）の共通の部品。
// 一番下までスクロールしたら、次を自動で読み込む。

import { useCallback, useEffect, useRef, useState } from "react";

type Page<T> = { items: T[]; next_cursor: string | null };

export function useInfiniteList<T>(
  fetchPage: (cursor: string | null) => Promise<Page<T>>,
  onError: (error: unknown) => boolean,
) {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [moreState, setMoreState] = useState<"idle" | "loading" | "error">("idle");
  const requestId = useRef(0);

  const reload = useCallback(async () => {
    const id = ++requestId.current;
    setState("loading");
    setItems([]);
    setCursor(null);
    setMoreState("idle");
    try {
      const page = await fetchPage(null);
      if (id !== requestId.current) return;
      setItems(page.items);
      setCursor(page.next_cursor);
      setState("ready");
    } catch (error) {
      if (id !== requestId.current || onError(error)) return;
      setState("error");
    }
  }, [fetchPage, onError]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const loadMore = useCallback(async () => {
    if (!cursor || moreState === "loading") return;
    const id = requestId.current;
    setMoreState("loading");
    try {
      const page = await fetchPage(cursor);
      if (id !== requestId.current) return;
      setItems((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
      setMoreState("idle");
    } catch (error) {
      if (id !== requestId.current || onError(error)) return;
      setMoreState("error");
    }
  }, [cursor, fetchPage, moreState, onError]);

  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !cursor || moreState !== "idle" || state !== "ready") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) void loadMore();
      },
      { rootMargin: "200px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [cursor, moreState, state, loadMore]);

  return {
    items,
    state,
    moreState,
    reload,
    retryMore: () => setMoreState("idle"),
    sentinel,
  };
}
