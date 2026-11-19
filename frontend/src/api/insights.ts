// 気づき一覧・本ごとの気づき一覧・気づきの API（api.md 7-4・7-5）。

import { api } from "./client";

export type GroupSort = "recent" | "many" | "few";

export const SORT_OPTIONS: { key: GroupSort; label: string; description: string }[] = [
  { key: "recent", label: "最近書いた順", description: "最後に気づきを書いた本から" },
  { key: "many", label: "気づきが多い順", description: "気づきをたくさん書いた本から" },
  { key: "few", label: "気づきが少ない順", description: "まだ気づきのない本から" },
];

export type InsightGroup = {
  id: string;
  title: string;
  cover_url: string | null;
  insight_count: number;
  last_written_at: string | null;
  deleted: boolean;
};

export type InsightGroupDetail = InsightGroup & { author: string | null };

export type InsightCard = {
  id: string;
  page: number | null;
  quote: string | null;
  body: string;
  next_step_count: number;
  created_at: string;
};

export type InsightDetail = {
  id: string;
  page: number | null;
  quote: string | null;
  body: string;
  created_at: string;
  book: { id: string; title: string; author: string | null; cover_url: string | null };
  latest_proposal: { id: string; completed_at: string; plans: { text: string }[] } | null;
  pending_proposal: { id: string; status: "processing" | "failed" } | null;
};

export type InsightInput = { page: number | null; quote: string | null; body: string };

export const BODY_MAX = 1000;
export const QUOTE_MAX = 300;
export const PAGE_MIN = 1;
export const PAGE_MAX = 9999;

const id = (value: string) => encodeURIComponent(value);

export const insightsApi = {
  groups: (sort: GroupSort, cursor: string | null) => {
    const params = new URLSearchParams({ sort });
    if (cursor) params.set("cursor", cursor);
    return api.get<{ items: InsightGroup[]; next_cursor: string | null }>(`/insight-groups?${params}`);
  },
  group: (groupId: string) => api.get<InsightGroupDetail>(`/insight-groups/${id(groupId)}`),
  cards: (groupId: string, cursor: string | null) =>
    api.get<{ items: InsightCard[]; next_cursor: string | null }>(
      `/insight-groups/${id(groupId)}/insights${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
  get: (insightId: string) => api.get<InsightDetail>(`/insights/${id(insightId)}`),
  create: (body: InsightInput & { book_id: string }) => api.post<{ id: string }>("/insights", body),
  update: (insightId: string, body: InsightInput) => api.patch<void>(`/insights/${id(insightId)}`, body),
  remove: (insightId: string) => api.delete<void>(`/insights/${id(insightId)}`),
};
