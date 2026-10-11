
import json
from datetime import datetime, timedelta, timezone

import requests

from database import get_connection
from security import generate_signature


# Retry delays: 30 seconds, 5 minutes, 30 minutes
RETRY_DELAYS = [30, 300, 1800]

# Maximum time to wait for the webhook receiver
REQUEST_TIMEOUT = 10


def utc_now():
    return datetime.now(timezone.utc)


def to_iso(value):
    return value.isoformat()


def deliver_event(event):
    event_id = event["id"]

    # Prepare the JSON body sent to the receiver
    payload = {
        "id": event_id,
        "type": event["type"],
        "payload": json.loads(event["payload"]),
        "created_at": event["created_at"]
    }

    body = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False
    )

    attempted_at = to_iso(utc_now())
    http_status = None

    try:
        response = requests.post(
            event["webhook_url"],
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": generate_signature(body)
            },
            timeout=REQUEST_TIMEOUT
        )

        http_status = response.status_code

        if 200 <= response.status_code < 300:
            outcome = "success"
        else:
            outcome = "failed"

    except requests.RequestException as exc:
        print(f"Delivery error for event {event_id}: {exc}")
        outcome = "failed"

    # Record every delivery attempt
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO delivery_attempts
            (event_id, attempted_at, http_status, outcome)
            VALUES (?, ?, ?, ?)
            """,
            (event_id, attempted_at, http_status, outcome)
        )

        # Include this attempt in the current delivery cycle
        attempt_number = event["cycle_attempts"] + 1

        if outcome == "success":
            conn.execute(
                """
                UPDATE events
                SET status = 'delivered',
                    cycle_attempts = ?,
                    next_attempt_at = NULL,
                    locked_until = NULL
                WHERE id = ?
                """,
                (attempt_number, event_id)
            )

        elif attempt_number >= 4:
            # Initial attempt + 3 retries = 4 attempts
            conn.execute(
                """
                UPDATE events
                SET status = 'dead',
                    cycle_attempts = ?,
                    next_attempt_at = NULL,
                    locked_until = NULL
                WHERE id = ?
                """,
                (attempt_number, event_id)
            )

        else:
            # Schedule the next retry
            delay = RETRY_DELAYS[attempt_number - 1]
            next_attempt = to_iso(
                utc_now() + timedelta(seconds=delay)
            )

            conn.execute(
                """
                UPDATE events
                SET status = 'failed',
                    cycle_attempts = ?,
                    next_attempt_at = ?,
                    locked_until = NULL
                WHERE id = ?
                """,
                (attempt_number, next_attempt, event_id)
            )

    print(
        f"Event {event_id}: {outcome}, "
        f"HTTP status: {http_status}, "
        f"attempt: {attempt_number}"
    )
