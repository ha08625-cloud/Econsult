/**
 * constants.ts
 *
 * Application-wide frontend constants shared across the patient form
 * and the admin portal.
 *
 * GENERAL_CONSULTATION_ID must match the condition_id in general.json exactly.
 * If the ruleset is ever renamed, update this value and this value only.
 *
 * SIGNPOSTING_PURIFY_CONFIG must match the nh3 allowlist in
 * practice_repository.py exactly. If the allowlist changes, update both:
 *   1. practice_repository.py  — nh3.clean() call
 *   2. This file               — SIGNPOSTING_PURIFY_CONFIG constant
 * rel is included because nh3 automatically injects rel="noopener noreferrer"
 * into stored HTML. DOMPurify must not strip it on render.
 */

export const GENERAL_CONSULTATION_ID = "general_consultation";

export const SIGNPOSTING_PURIFY_CONFIG = {
  ALLOWED_TAGS: ["p", "strong", "em", "a", "ul", "ol", "li", "br"],
  ALLOWED_ATTR: ["href", "rel", "target"],
  ALLOWED_URI_REGEXP: /^https?:/i,
};
