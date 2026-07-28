"""
Upload constants.

Single source of truth for photo upload limits, shared across:
  - app/core/upload_constants.py  (this file — Python side)
  - frontend/src/upload_constants.ts (TypeScript mirror — must be kept in sync manually)

If any limit changes, update upload_constants.json and then update
frontend/src/upload_constants.ts to match. Do not define these values
anywhere else in the codebase.

Values are loaded once at module import time. A missing or malformed JSON
file is a deployment error and will raise immediately at startup.
"""

import json
import os

_HERE = os.path.dirname(__file__)
_JSON_PATH = os.path.join(_HERE, "upload_constants.json")

with open(_JSON_PATH, encoding="utf-8") as _f:
    _data = json.load(_f)

ALLOWED_MIME_TYPES: list[str] = _data["ALLOWED_MIME_TYPES"]
MAX_FILE_SIZE_BYTES: int = _data["MAX_FILE_SIZE_BYTES"]
MAX_TOTAL_SIZE_BYTES: int = _data["MAX_TOTAL_SIZE_BYTES"]
MAX_FILE_COUNT: int = _data["MAX_FILE_COUNT"]

# Derived, not part of the shared JSON: this is a server-side multipart
# request-size ceiling, not a photo limit, so it has no frontend mirror.
# It caps the raw Content-Length of a POST /form/finish request -- photo
# bytes plus multipart boundaries/headers plus the JSON 'payload' form
# field -- used by app/core/max_body_size_route.py to reject oversized
# requests before FastAPI parses the body. The 2 MiB margin comfortably
# covers multipart framing overhead for MAX_FILE_COUNT parts and the JSON
# payload field.
MAX_FINISH_REQUEST_BYTES: int = MAX_TOTAL_SIZE_BYTES + 2 * 1024 * 1024
