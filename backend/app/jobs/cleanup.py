"""worker：5分おきに後片付けを動かし続ける（api.md 2-8）。

起動：python -m app.jobs.cleanup
"""

import logging
import signal
import threading

from app.core import clock
from app.db import SessionLocal
from app.services import ai_proposals

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 5 * 60

stop_event = threading.Event()


def run_cleanup() -> None:
    # API のその場の判定と同じ関数を呼ぶ（api.md 2-8）
    now = clock.now()
    with SessionLocal() as db:
        result = ai_proposals.cleanup(db, now)
        rate_limit_events = ai_proposals.cleanup_rate_limit_events(db, now)
    logger.info(
        "cleanup: question_failed=%s plans_reset=%s retry_limit=%s deleted=%s rate_limit_events=%s",
        result.question_failed,
        result.plans_reset,
        result.retry_limit,
        result.deleted,
        rate_limit_events,
    )


def handle_stop(signum: int, frame: object) -> None:
    stop_event.set()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # docker compose stop が送る SIGTERM を受けたら、待つのをやめて終わる。
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    logger.info("cleanup worker started")
    while not stop_event.is_set():
        try:
            run_cleanup()
        except Exception:
            # 1回失敗しても worker は止めず、次の回でやり直す。
            logger.exception("cleanup failed")
        stop_event.wait(INTERVAL_SECONDS)
    logger.info("cleanup worker stopped")


if __name__ == "__main__":
    main()
