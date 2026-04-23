/**
 * UsersTab.tsx — manage admin users for the current practice.
 *
 * Allows adding new admin users by email address, removing existing users,
 * and resending invitation emails to users who have not yet logged in.
 *
 * State model:
 * - users / loadState: the fetched user list and its loading lifecycle.
 * - isAdding: true while the POST /admin/users request is in flight.
 * - actionLoadingId: the id of the user currently being acted on (remove or
 *   resend), or null. Used to disable row buttons during in-flight requests.
 * - inlineMessage: a transient status message shown below the add-user form
 *   or alongside the user list. Cleared on any new action.
 *
 * Mounting strategy: UsersTab is conditionally rendered by EditorView when
 * the "users" tab is active. It performs a fresh fetch on every mount.
 * There is no unsaved state, so no unsavedRef is needed.
 *
 * Session expiry: any AuthError from an API call propagates to onAuthError,
 * which transitions App back to LoginView. This matches the pattern used by
 * all other tabs.
 */

import { useState, useEffect } from "react";
import { AuthError, fetchUsers, addUser, removeUser, resendInvitation } from "../api";
import type { AdminUser } from "../types";

interface Props {
  onAuthError: () => void;
}

type LoadState = "loading" | "ready" | "error";

type InlineMessage = {
  type: "error" | "warning" | "success";
  text: string;
};

function formatLastLogin(lastLogin: string | null): string {
  if (!lastLogin) return "Pending";
  return new Date(lastLogin).toLocaleString("en-GB", { timeZone: "Europe/London" });
}

export default function UsersTab({ onAuthError }: Props) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [emailInput, setEmailInput] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [inlineMessage, setInlineMessage] = useState<InlineMessage | null>(null);

  useEffect(() => {
    loadUsers();
  }, []);

  async function loadUsers() {
    setLoadState("loading");
    try {
      const data = await fetchUsers();
      setUsers(data);
      setLoadState("ready");
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError();
        return;
      }
      setLoadState("error");
    }
  }

  async function handleAddUser() {
    const email = emailInput.trim();
    if (!email) return;

    setIsAdding(true);
    setInlineMessage(null);

    try {
      const result = await addUser(email);
      setEmailInput("");
      await loadUsers();
      if (!result.email_sent) {
        setInlineMessage({
          type: "warning",
          text: "Admin added, but the invitation email failed to send. Use 'Resend Invite' to retry.",
        });
      }
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError();
        return;
      }
      setInlineMessage({
        type: "error",
        text: err instanceof Error ? err.message : "An unexpected error occurred.",
      });
    } finally {
      setIsAdding(false);
    }
  }

  async function handleRemoveUser(userId: string) {
    setActionLoadingId(userId);
    setInlineMessage(null);

    try {
      await removeUser(userId);
      await loadUsers();
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError();
        return;
      }
      setInlineMessage({
        type: "error",
        text: err instanceof Error ? err.message : "An unexpected error occurred.",
      });
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleResendInvitation(userId: string) {
    setActionLoadingId(userId);
    setInlineMessage(null);

    try {
      const result = await resendInvitation(userId);
      if (!result.email_sent) {
        setInlineMessage({
          type: "warning",
          text: "Admin added, but the invitation email failed to send. Use 'Resend Invite' to retry.",
        });
      } else {
        setInlineMessage({ type: "success", text: "Invitation email sent." });
      }
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError();
        return;
      }
      setInlineMessage({
        type: "error",
        text: err instanceof Error ? err.message : "An unexpected error occurred.",
      });
    } finally {
      setActionLoadingId(null);
    }
  }

  return (
    <>
      {/* Add user form */}
      <p className="section-label">Add admin user</p>
      <div style={{ display: "flex", gap: "10px", alignItems: "flex-end" }}>
        <div style={{ flex: 1 }}>
          <label htmlFor="new-admin-email">Email address</label>
          <input
            id="new-admin-email"
            type="text"
            value={emailInput}
            onChange={(e) => setEmailInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleAddUser(); }}
            placeholder="admin@example.com"
            disabled={isAdding}
          />
        </div>
        <button
          className="btn btn-primary"
          onClick={handleAddUser}
          disabled={isAdding || !emailInput.trim()}
          style={{ marginBottom: "0" }}
        >
          {isAdding ? (
            <>
              <span className="spinner" />
              Adding...
            </>
          ) : (
            "Add Admin"
          )}
        </button>
      </div>

      {inlineMessage && (
        <div className={`alert alert-${inlineMessage.type}`}>
          {inlineMessage.text}
        </div>
      )}

      <hr className="divider" />

      {/* User list */}
      <p className="section-label">Current admins</p>

      {loadState === "loading" && (
        <div className="loading-row">
          <span className="spinner dark" />
          Loading users...
        </div>
      )}

      {loadState === "error" && (
        <div className="alert alert-error">
          Failed to load users.{" "}
          <button
            className="btn btn-ghost"
            onClick={loadUsers}
            style={{ padding: "0", fontSize: "inherit", color: "inherit", textDecoration: "underline" }}
          >
            Retry
          </button>
        </div>
      )}

      {loadState === "ready" && users.length === 0 && (
        <div className="empty-state">No admin users found.</div>
      )}

      {loadState === "ready" && users.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {users.map((user) => (
            <div
              key={user.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                padding: "12px 16px",
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--card-radius)",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500, fontSize: "14px" }}>
                  {user.email}
                  {user.is_current_user && (
                    <span
                      style={{
                        marginLeft: "8px",
                        fontSize: "11px",
                        fontWeight: 600,
                        color: "var(--text-muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                      }}
                    >
                      You
                    </span>
                  )}
                </div>
                <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>
                  Last login: {formatLastLogin(user.last_login)}
                </div>
              </div>

              <div style={{ display: "flex", gap: "8px", flexShrink: 0 }}>
                {user.last_login === null && (
                  <button
                    className="btn btn-outline"
                    style={{ fontSize: "13px", padding: "6px 12px" }}
                    disabled={actionLoadingId === user.id}
                    onClick={() => handleResendInvitation(user.id)}
                  >
                    {actionLoadingId === user.id ? "Sending..." : "Resend Invite"}
                  </button>
                )}
                <button
                  className="btn btn-outline"
                  style={{
                    fontSize: "13px",
                    padding: "6px 12px",
                    color: user.is_current_user ? undefined : "var(--danger)",
                    borderColor: user.is_current_user ? undefined : "var(--danger)",
                  }}
                  disabled={user.is_current_user || actionLoadingId === user.id}
                  onClick={() => handleRemoveUser(user.id)}
                >
                  {actionLoadingId === user.id ? "Removing..." : "Remove"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}