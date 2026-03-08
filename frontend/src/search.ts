/**
 * search.ts
 *
 * Condition filtering logic for Screen 0 autocomplete.
 *
 * Three-layer matching strategy (applied in order):
 *   Layer 1: substring match on condition label
 *   Layer 2: substring match on any search tag
 *   Layer 3: fuzzy match (Levenshtein) on individual tag tokens
 *
 * Layer 3 only runs if layers 1 and 2 both fail.
 * Fuzzy matching is disabled for queries shorter than FUZZY_MIN_QUERY_LENGTH
 * to prevent short strings from matching everything.
 *
 * All matching is case-insensitive.
 * Empty query always returns the full list.
 * No-match query also returns the full list (caller handles the UI message).
 */

import type { ConditionSummary } from "./types";

// --- Constants ---

const FUZZY_MIN_QUERY_LENGTH = 4;
const FUZZY_THRESHOLD_SHORT = 1; // query length 4-5
const FUZZY_THRESHOLD_LONG = 2;  // query length 6+

// --- Private helpers ---

/**
 * Standard dynamic programming Levenshtein distance.
 * Measures the minimum number of single-character edits (insert, delete,
 * substitute) needed to change string a into string b.
 */
function levenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;

  // Allocate a (m+1) x (n+1) matrix
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array(n + 1).fill(0)
  );

  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1];
      } else {
        dp[i][j] = 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
      }
    }
  }

  return dp[m][n];
}

/**
 * Returns the Levenshtein threshold for a given query length,
 * or null if fuzzy matching should be disabled entirely.
 */
function fuzzyThreshold(queryLength: number): number | null {
  if (queryLength < FUZZY_MIN_QUERY_LENGTH) return null;
  if (queryLength <= 5) return FUZZY_THRESHOLD_SHORT;
  return FUZZY_THRESHOLD_LONG;
}

// --- Exported functions ---

/**
 * Normalise a string for comparison: lowercase and trim.
 * Exported so it can be used in tests.
 */
export function normalise(text: string): string {
  return text.toLowerCase().trim();
}

/**
 * Returns true if the condition should appear for the given query.
 *
 * Layer 1: normalised label contains normalised query
 * Layer 2: any normalised tag contains normalised query
 * Layer 3: for each tag, split into whitespace-delimited tokens,
 *           check levenshtein(query, token) <= threshold
 *
 * Empty query always returns true.
 */
export function matchesQuery(
  condition: ConditionSummary,
  query: string
): boolean {
  if (!query) return true;

  const q = normalise(query);

  // Layer 1: label substring match
  if (normalise(condition.label).includes(q)) return true;

  // Layer 2: tag substring match
  for (const tag of condition.search_tags) {
    if (normalise(tag).includes(q)) return true;
  }

  // Layer 3: fuzzy match on individual tag tokens
  const threshold = fuzzyThreshold(q.length);
  if (threshold !== null) {
    for (const tag of condition.search_tags) {
      const tokens = normalise(tag).split(/\s+/);
      for (const token of tokens) {
        if (levenshtein(q, token) <= threshold) return true;
      }
    }
  }

  return false;
}

/**
 * Filter a list of conditions by query.
 *
 * Rules:
 * - Always filters from the full canonical list passed in (never incremental)
 * - Empty query returns the full list
 * - No matches returns the full list (caller is responsible for showing a message)
 */
export function filterConditions(
  conditions: ConditionSummary[],
  query: string
): ConditionSummary[] {
  if (!query.trim()) return conditions;

  const matched = conditions.filter((c) => matchesQuery(c, query));
  return matched.length > 0 ? matched : conditions;
}