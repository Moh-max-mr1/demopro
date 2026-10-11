
import hashlib
import hmac
import os

from dotenv import load_dotenv

load_dotenv()


def generate_signature(body: str) -> str:
    secret = os.getenv("WEBHOOK_SECRET")

    if not secret:
        raise RuntimeError("WEBHOOK_SECRET is not configured")

    digest = hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return digest


def verify_signature(body: str, received_signature: str) -> bool:
    if not isinstance(received_signature, str):
        return False

    expected = generate_signature(body)

    return hmac.compare_digest(expected, received_signature)
