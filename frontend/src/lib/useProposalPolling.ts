// AI提案の状態を2秒ごとに問い合わせる部品（api.md 2-1・2-3）。AI提案の画面と気づきの詳細で共通に使う。
// - proposalId を null にすると止まる（結果が出たら、呼ぶ側が null にする）
// - タブが裏にある間は一時停止し、表に戻したら再開する
// - 念のため、始めてから3分で問い合わせをやめる（サーバーは2分で止まったとみなすため）

import { useEffect, useRef } from "react";

import { aiProposalsApi, type Proposal } from "../api/aiProposals";
import { ApiError } from "../api/client";

const INTERVAL_MS = 2000;
const LIMIT_MS = 3 * 60 * 1000;

export type PollUpdate = { kind: "proposal"; proposal: Proposal } | { kind: "gone" };

export function useProposalPolling(
  proposalId: string | null,
  onUpdate: (update: PollUpdate) => void,
  onUnauthorized: (error: unknown) => boolean,
) {
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;
  const onUnauthorizedRef = useRef(onUnauthorized);
  onUnauthorizedRef.current = onUnauthorized;

  useEffect(() => {
    if (!proposalId) return;
    const startedAt = Date.now();
    let stopped = false;
    let inFlight = false;
    let timer: number | undefined;

    function schedule() {
      if (stopped || inFlight || timer !== undefined) return;
      if (document.hidden || Date.now() - startedAt > LIMIT_MS) return;
      timer = window.setTimeout(tick, INTERVAL_MS);
    }

    async function tick() {
      timer = undefined;
      inFlight = true;
      try {
        const proposal = await aiProposalsApi.get(proposalId!);
        if (!stopped) onUpdateRef.current({ kind: "proposal", proposal });
      } catch (error) {
        if (stopped) return;
        if (onUnauthorizedRef.current(error)) {
          stopped = true;
          return;
        }
        if (error instanceof ApiError && error.status === 404) onUpdateRef.current({ kind: "gone" });
        // 通信の失敗は、次の問い合わせでもう一度試す
      } finally {
        inFlight = false;
      }
      schedule();
    }

    function handleVisibility() {
      if (!document.hidden) schedule();
    }

    document.addEventListener("visibilitychange", handleVisibility);
    schedule();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [proposalId]);
}
