// 本棚の API（api.md 7-3）。

import { api } from "./client";

export type ReadingStatus = "reading" | "finished";

export const STATUS_LABELS: Record<ReadingStatus, string> = {
  reading: "読書中",
  finished: "読了",
};

export type BookListItem = {
  id: string;
  title: string;
  cover_url: string | null;
  status: ReadingStatus;
};

export type BookList = {
  items: BookListItem[];
  total: number;
  next_cursor: string | null;
};

export type BookDetail = {
  id: string;
  title: string;
  author: string | null;
  cover_url: string | null;
  status: ReadingStatus;
  google_volume_id: string | null;
  insight_count: number;
};

export type CatalogItem = {
  google_volume_id: string;
  title: string;
  authors: string | null;
  published_year: number | null;
  cover_url: string | null;
  info_link: string | null;
  shelf_book_id: string | null;
};

export type CatalogSearchResult = {
  items: CatalogItem[];
  next_offset: number | null;
};

export const TITLE_MAX = 200;
export const AUTHOR_MAX = 100;

export const booksApi = {
  list: (status: ReadingStatus | null, cursor: string | null) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (cursor) params.set("cursor", cursor);
    const query = params.toString();
    return api.get<BookList>(`/books${query ? `?${query}` : ""}`);
  },
  get: (id: string) => api.get<BookDetail>(`/books/${encodeURIComponent(id)}`),
  createManual: (body: { title: string; author: string | null; status: ReadingStatus }) =>
    api.post<{ id: string }>("/books", body),
  createFromCatalog: (body: { google_volume_id: string; status: ReadingStatus }) =>
    api.post<{ id: string }>("/books/from-catalog", body),
  update: (id: string, body: { title?: string; author?: string | null }) =>
    api.patch<BookDetail>(`/books/${encodeURIComponent(id)}`, body),
  updateStatus: (id: string, status: ReadingStatus) =>
    api.put<BookDetail>(`/books/${encodeURIComponent(id)}/status`, { status }),
  remove: (id: string) => api.delete<void>(`/books/${encodeURIComponent(id)}`),
  search: (q: string, offset: number) =>
    api.get<CatalogSearchResult>(`/catalog/search?q=${encodeURIComponent(q)}&offset=${offset}`),
};
