
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from database import get_connection, init_db

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Nestack Webhook Delivery Engine",
    description="Webhook event ingestion, delivery, retries, and status tracking",
    version="1.0.0",
    lifespan=lifespan
)


class EventRequest(BaseModel):
    type: str = Field(min_length=1, max_length=200)
    payload: dict
    webhook_url: str = Field(min_length=1)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_attempts(conn, event_id):
    rows = conn.execute(
        """
        SELECT attempted_at, http_status, outcome
        FROM delivery_attempts
        WHERE event_id = ?
        ORDER BY id
        """,
        (event_id,)
    ).fetchall()

    return [dict(row) for row in rows]


def get_event(conn, event_id):
    row = conn.execute(
        "SELECT * FROM events WHERE id = ?",
        (event_id,)
    ).fetchone()

    if row is None:
        return None

    event = dict(row)

    return {
        "id": event["id"],
        "type": event["type"],
        "payload": json.loads(event["payload"]),
        "webhook_url": event["webhook_url"],
        "status": event["status"],
        "created_at": event["created_at"],
        "attempts": get_attempts(conn, event_id)
    }


@app.post("/events", status_code=status.HTTP_201_CREATED)
def create_event(request: EventRequest):
    parsed_url = urlparse(request.webhook_url)

    if (
        parsed_url.scheme not in ("http", "https")
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
    ):
        raise HTTPException(
            status_code=400,
            detail="webhook_url must be a valid HTTP or HTTPS URL"
        )

    created_at = utc_now()
    payload_json = json.dumps(
        request.payload,
        separators=(",", ":"),
        ensure_ascii=False
    )

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO events
            (type, payload, webhook_url, status,
             created_at, next_attempt_at, cycle_attempts)
            VALUES (?, ?, ?, 'pending', ?, ?, 0)
            """,
            (
                request.type,
                payload_json,
                request.webhook_url,
                created_at,
                created_at
            )
        )

        event_id = cursor.lastrowid
        event = get_event(conn, event_id)

    return event


@app.get("/events")
def list_events():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM events ORDER BY id DESC"
        ).fetchall()

        return [
            get_event(conn, row["id"])
            for row in rows
        ]


@app.get("/events/{event_id}")
def retrieve_event(event_id: int):
    with get_connection() as conn:
        event = get_event(conn, event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event not found"
        )

    return event


@app.post("/events/{event_id}/retry")
def retry_event(event_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Event not found"
            )

        if row["status"] != "dead":
            raise HTTPException(
                status_code=400,
                detail="Only dead events can be retried"
            )

        conn.execute(
            """
            UPDATE events
            SET status = 'pending',
                cycle_attempts = 0,
                next_attempt_at = ?,
                locked_until = NULL
            WHERE id = ?
            """,
            (utc_now(), event_id)
        )

        return get_event(conn, event_id)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
