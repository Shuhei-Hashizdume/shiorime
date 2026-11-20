// AI提案と、本日の残り回数の API（api.md 7-6・7-2）。

import { api } from "./client";

/** 画面の場面に合わせた7つの状態（api.md 7-6） */
export type ProposalStatus =
  | "generating_question"
  | "awaiting_answer"
  | "generating_plans"
  | "plan_failed"
  | "completed"
  | "question_failed"
  | "retry_limit_reached";

export type Proposal = {
  id: string;
  status: ProposalStatus;
  insight_id: string;
  insight: { book_title: string; page: number | null; quote: string | null; body: string };
  question: string | null;
  answer: string | null;
  plans: { text: string }[] | null;
  completed_at: string | null;
  retries_left: number;
};

export type AiUsage = { remaining_today: number; daily_limit: number; app_limit_reached: boolean };

export const ANSWER_MAX = 500;

const id = (value: string) => encodeURIComponent(value);

export const aiProposalsApi = {
  /** 受付番号（Idempotency-Key）を付けて始める。同じ番号で送り直すと、同じAI提案が返る（api.md 2-4） */
  start: (insightId: string, idempotencyKey: string) =>
    api.post<{ id: string }>(`/insights/${id(insightId)}/ai-proposals`, undefined, {
      "Idempotency-Key": idempotencyKey,
    }),
  get: (proposalId: string) => api.get<Proposal>(`/ai-proposals/${id(proposalId)}`),
  answer: (proposalId: string, answer: string) => api.post<void>(`/ai-proposals/${id(proposalId)}/answer`, { answer }),
  retry: (proposalId: string, answer: string) => api.post<void>(`/ai-proposals/${id(proposalId)}/retry`, { answer }),
  abandon: (proposalId: string) => api.post<void>(`/ai-proposals/${id(proposalId)}/abandon`),
  usage: () => api.get<AiUsage>("/me/ai-usage"),
};
