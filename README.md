# Nestack Webhook Delivery Engine

## 1. Overview

The Nestack Webhook Delivery Engine is a Python-based service that accepts webhook events through REST APIs, stores them in SQLite, and delivers them to customer-provided webhook URLs using a background worker.

The system supports automatic retries, HMAC-SHA256 request signatures, delivery-attempt tracking, and manual retries for dead events.

## 2. Technologies Used

- Python
- FastAPI
- SQLite
- Requests
- HMAC-SHA256
- Uvicorn

## 3. Project Setup

### Prerequisites

- Python 3.12 or later
- pip

### Installation

Clone or download the project and open its root directory.

Create and activate a virtual environment on Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
WEBHOOK_SECRET=replace_with_your_own_random_secret
PORT=8000
```

Generate a strong secret using:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated value into `.env`. Never commit this file to GitHub.

## 4. Running the Application

Open two terminals in the project directory.

### Terminal 1: Start the API server

```bash
python main.py
```

### Terminal 2: Start the background worker

```bash
python worker.py
```

The API documentation is available at:

`http://127.0.0.1:8000/docs`

The worker runs independently and checks for events that are ready for delivery.

## 5. API Endpoints

### Create an event

**POST `/events`**

Example request:

```json
{
  "type": "order.created",
  "payload": {
    "order_id": 123,
    "amount": 500
  },
  "webhook_url": "https://example.com/webhook"
}
```

Returns HTTP `201 Created` with the created event and its initial status.

### List events

**GET `/events`**

Returns all events, including their delivery status and attempt history.

### Get event details

**GET `/events/{id}`**

Returns the requested event and its delivery attempts. Returns `404` if the event does not exist.

### Manually retry a dead event

**POST `/events/{id}/retry`**

Requeues an event whose status is `dead`. The retry cycle starts again. Returns `400` if the event is not dead and `404` if it does not exist.

## 6. Event Statuses

- `pending`: Waiting for delivery.
- `delivered`: Successfully delivered with a 2xx HTTP response.
- `failed`: The latest delivery attempt failed, and another retry is scheduled.
- `dead`: All four attempts failed; automatic retries have stopped.

Each attempt records its timestamp, HTTP status, and outcome. The HTTP status is `null` when no HTTP response is received.

## 7. Retry Schedule

The system allows one initial attempt and up to three automatic retries.

| Attempt | When it occurs |
|---|---|
| 1 | Immediately after event ingestion |
| 2 | 30 seconds after the first failure |
| 3 | 5 minutes after the second failure |
| 4 | 30 minutes after the third failure |

If the fourth attempt fails, the event becomes `dead`.

The retry delays are configured in `delivery.py` using `RETRY_DELAYS = [30, 300, 1800]`.

## 8. Webhook Signature Verification

Each outgoing webhook request includes the `X-Webhook-Signature` header.

The signature is generated using HMAC-SHA256 with the shared `WEBHOOK_SECRET` and the exact serialized JSON request body.

Python verification example:

```python
import hashlib
import hmac
import os

secret = os.environ["WEBHOOK_SECRET"].encode("utf-8")
body = raw_request_body

expected = hmac.new(
    secret,
    body,
    hashlib.sha256
).hexdigest()

received = request.headers.get("X-Webhook-Signature", "")

is_valid = hmac.compare_digest(expected, received)
```

The receiver must verify the signature against the exact raw request-body bytes. Both sender and receiver must use the same secret.

## 9. Persistence and Restart Behavior

Events and delivery attempts are stored in SQLite, so they remain available after the API server or worker is restarted.

The API initializes the database when it starts. The worker reads pending events and due retries from the database.

A scheduled retry remains stored in `next_attempt_at` and becomes eligible when its scheduled time arrives. If the worker is stopped, retries are delayed until the worker runs again.

## 10. Project Structure

```text
nestack-webhook/
├── main.py
├── database.py
├── worker.py
├── delivery.py
├── security.py
├── requirements.txt
├── .env
├── .gitignore
└── README.md
```

## 11. Security Notes

- Keep `.env` and the webhook secret private.
- Use HTTPS for production webhook endpoints.
- Do not expose credentials in logs or source control.
- Validate and restrict webhook destinations appropriately before deploying publicly.