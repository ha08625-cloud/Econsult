## 1. The Ruleset Structure

### CRITICAL DESIGN DECISIONS:
* Not a conversational agent: This is strictly a form-filling engine.
* No external data: The only source of information is the patient (either direct input or encoder reading free text). Do not architect for EHR integrations.
* 1:1 Question-to-Signal Mapping: There is no separate signal_id. A question_id serves as the unique identifier. Do not map multiple questions to a single signal to avoid contradiction resolution complexities.
* Coupled Wording: The question (human) and encoder_prompt (ML) are different wordings of the SAME clinical concept.

## 2. Search Tags

Presentation Metadata (search_tags)
* Boundary Rule: search_tags are presentation-layer metadata, strictly isolated from clinical schema (questions, safety rules). They belong in the presentation block.
* No ML Expansion: Synonym expansion is strictly manual. Do not introduce automated or ML-based tag generation.
* Validation: Enforced fail-fast at startup by condition_registry.py.

## 3. The General Fallback

general.json (Generic Fallback)
* Purpose: A blank form pathway processed identically to other conditions.
* Safety Bypass: It has no specific safety rules; it relies entirely on the universal safety warning on Screen 1.
* CRITICAL COUPLING WARNING: The condition_id ("general_consultation") in general.json MUST EXACTLY MATCH GENERAL_CONSULTATION_ID in the frontend constants.ts.
* Search Exclusion: This condition defines no search_tags because it is excluded from combobox search results and triggered exclusively via the "Use blank form" button.
