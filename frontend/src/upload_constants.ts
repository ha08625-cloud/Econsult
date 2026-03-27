/**
 * upload_constants.ts
 *
 * Frontend mirror of app/core/upload_constants.json.
 *
 * These values are NOT imported from JSON — they are written by hand to avoid
 * a dependency on resolveJsonModule (not enabled in this project's tsconfig).
 *
 * If any limit changes, update ALL THREE of:
 *   1. app/core/upload_constants.json  — canonical source of truth
 *   2. app/core/upload_constants.py    — Python side
 *   3. frontend/src/upload_constants.ts — this file
 *
 * Do not define these values anywhere else in the frontend codebase.
 *
 * Note: MIME type checking on the client is a usability guard against
 * accidental misuse, not a security control. The server validates the same
 * limits independently. Magic bytes checking in EditScreen provides a
 * stronger client-side check for file content.
 */

export const ALLOWED_MIME_TYPES: ReadonlyArray<string> = [
  "image/jpeg",
  "image/png",
];

/** Maximum size for a single file, in bytes (5 MB). */
export const MAX_FILE_SIZE_BYTES: number = 5_242_880;

/** Maximum combined size of all files in one submission, in bytes (10 MB). */
export const MAX_TOTAL_SIZE_BYTES: number = 10_485_760;

/** Maximum number of photos per submission. */
export const MAX_FILE_COUNT: number = 5;