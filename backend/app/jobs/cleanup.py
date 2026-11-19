"""worker：5分おきに後片付けを動かし続ける（api.md 2-8）。

起動：python -m app.jobs.cleanup
"""

import logging
import signal
import threading

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 5 * 60

stop_event = threading.Event()


def run_cleanup() -> None:
    # 止まった AI提案の片付けは、機能5で services の関数を呼ぶ形にする。
    logger.info("cleanup: nothing to do yet")


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
