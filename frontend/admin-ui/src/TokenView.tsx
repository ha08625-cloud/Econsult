/**
 * TokenView.tsx — token input form.
 *
 * Shown when no valid token is held in App state.
 * On successful connection, calls onSuccess with the token and condition list.
 */

import { useState } from "react";
import { fetchConditions } from "./api";
import type { ConditionSummary } from "./types";

interface Props {
  onSuccess: (token: string, conditions: ConditionSummary[]) => void;
}

export default function TokenView({ onSuccess }: Props) {
  const [token, setToken] = useState("");
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConnect() {
    const trimmed = token.trim();
    if (!trimmed) return;

    setIsConnecting(true);
    setError(null);

    try {
      const conditions = await fetchConditions(trimmed);
      onSuccess(trimmed, conditions);
    } catch (err) {
      if (err instanceof Error && err.message === "UNAUTHORIZED") {
        setError("Invalid token. Check the value and try again.");
      } else {
        setError("Could not reach server. Check that the application is running.");
      }
    } finally {
      setIsConnecting(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleConnect();
  }

  return (
    <div className="card token-view">
      <p className="card-title">Connect to admin</p>
      <p className="card-subtitle">
        Enter your admin token to manage practice signposting.
        <br />
        <span style={{ color: "var(--warning-text)", fontSize: 12 }}>
          Note: token-based access is a temporary measure and will be replaced
          with proper authentication in a future version.
        </span>
      </p>

      <div className="form-row">
        <div className="field">
          <label htmlFor="token-input">Admin token</label>
          <input
            id="token-input"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter token"
            autoComplete="off"
          />
        </div>
        <button
          className="btn btn-primary"
          onClick={handleConnect}
          disabled={isConnecting || token.trim() === ""}
          style={{ marginTop: 22 }}
        >
          {isConnecting ? (
            <>
              <span className="spinner" />
              Connecting…
            </>
          ) : (
            "Connect"
          )}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
    </div>
  );
}
