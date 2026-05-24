"""
Temporary investigation helper for the MESH sandbox.
Delete after Phase 0 discovery is complete.
"""
import hashlib
import hmac
import sys
import uuid
from datetime import datetime, timezone


def build_auth_header(mailbox_id: str, password: str, shared_key: str) -> str:
    nonce = str(uuid.uuid4())
    nonce_count = "1"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    raw = f"{mailbox_id}:{nonce}:{nonce_count}:{password}:{timestamp}"
    digest = hmac.new(
        shared_key.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"NHSMESH {mailbox_id}:{nonce}:{nonce_count}:{timestamp}:{digest}"


if __name__ == "__main__":
    mailbox = sys.argv[1] if len(sys.argv) > 1 else "SENDER_MAILBOX"
    print(build_auth_header(mailbox, "password", "TestKey"))