/**
 * types.ts — admin portal type definitions.
 */

export interface ConditionSummary {
  id: string;
  label: string;
}

export type SaveStatus = {
  type: "success" | "error";
  text: string;
};
