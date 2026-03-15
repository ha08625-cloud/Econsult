Provisional plan

Extract each screen into its own component file. The natural split follows the screen names you already have:

- `SafetyWarningScreen.tsx` -- Screen 0 (safety gate + availability)
- `SelectConditionScreen.tsx` -- Screen 1
- `FreeTextScreen.tsx` -- Screen 2
- `EditScreen.tsx` -- Screen 3
- `ReviewScreen.tsx` -- Screen 4
- `ContactScreen.tsx` -- Screen 5
- `DoneScreen.tsx` -- Screen 6

App.tsx becomes a thin orchestrator: it holds the shared state, decides which screen to render, and passes props (state values and callbacks) to the active screen component. This mirrors the same pattern as your backend's `engine_adapters.py` -- it wires things together but contains no logic of its own.

The helper functions (`initialiseEditableAnswers`, `initialiseContactPreferences`, `isValidUkPhone`, `PageShell`, `InlineError`) move to a shared `components.tsx` or `helpers.ts` as appropriate.