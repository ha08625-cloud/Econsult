/**
 * App.tsx — admin portal root component.
 *
 * Holds token and conditions in state.
 * Renders TokenView until a valid token is confirmed, then EditorView.
 */

import { useState } from "react";
import TokenView from "./TokenView";
import EditorView from "./EditorView";
import type { ConditionSummary } from "./types";

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [conditions, setConditions] = useState<ConditionSummary[]>([]);

  function handleTokenSuccess(validToken: string, loadedConditions: ConditionSummary[]) {
    setToken(validToken);
    setConditions(loadedConditions);
  }

  return (
    <div>
      <header className="page-header">
        <span className="wordmark">econsult</span>
        <span className="separator" />
        <span className="title">Practice admin</span>
      </header>

      <main className="main">
        {token === null ? (
          <TokenView onSuccess={handleTokenSuccess} />
        ) : (
          <EditorView token={token} conditions={conditions} />
        )}
      </main>
    </div>
  );
}
