
import time
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

from database import get_connection
from delivery import deliver_event, to_iso, utc_now


POLL_INTERVAL = 1
LOCK_SECONDS = 30


def claim_next_event():
    now = utc_now()
    now_text = to_iso(now)
    lock_until = to_iso(
        now + timedelta(seconds=LOCK_SECONDS)
    )

    with get_connection() as conn:
        # Prevent two workers from claiming the same event
        conn.execute("BEGIN IMMEDIATE")

        event = conn.execute(
            """
            SELECT *
            FROM events
            WHERE status IN ('pending', 'failed')
              AND next_attempt_at IS NOT NULL
              AND next_attempt_at <= ?
              AND (locked_until IS NULL OR locked_until <= ?)
            ORDER BY next_attempt_at, id
            LIMIT 1
            """,
            (now_text, now_text)
        ).fetchone()

        if event is None:
            return None

        result = conn.execute(
            """
            UPDATE events
            SET locked_until = ?
            WHERE id = ?
              AND status IN ('pending', 'failed')
              AND (locked_until IS NULL OR locked_until <= ?)
            """,
            (lock_until, event["id"], now_text)
        )

        if result.rowcount != 1:
            return None

        return dict(event)


def start_worker():
    print("Webhook delivery worker started")

    while True:
        try:
            event = claim_next_event()

            if event is None:
                time.sleep(POLL_INTERVAL)
                continue

            deliver_event(event)

        except KeyboardInterrupt:
            print("Worker stopped")
            break

        except Exception as exc:
            print(f"Worker error: {exc}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    start_worker()
