"""
PDF job constants.

Retry schedule and maximum attempt count for the PDF worker.

No application-module imports. This module may be imported by
pdf_repository.py and pdf_worker.py only.
"""

# Maximum number of processing attempts before a pdf_job is marked 'failed'
# permanently (no further retries).
MAX_PDF_ATTEMPTS: int = 3

# Backoff windows between retries. Index 0 is applied after the first failure,
# index 1 after the second. If attempt_count >= MAX_PDF_ATTEMPTS the job is
# marked failed; no further backoff entry is needed.
PDF_RETRY_BACKOFF_MINUTES: list[int] = [5, 10]