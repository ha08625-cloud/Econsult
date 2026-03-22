// Structural layout wrappers only.
// These components have no knowledge of application state, API calls, or business logic.
// They may reference global CSS class names from index.css — that coupling is intentional and acceptable.
// Do not import from api.ts, helpers.ts, or any screen component from this file.

import React from "react";

interface PageShellProps {
  children: React.ReactNode;
  practiceName?: string | null;
}

export function PageShell({ children, practiceName }: PageShellProps) {
  return (
    <>
      <header className="page-header">
        <span className="page-header-title">Online Consultation</span>
        {practiceName && (
          <span className="page-header-practice">{practiceName}</span>
        )}
      </header>
      <div className="page-container">
        <div className="screen-card">{children}</div>
      </div>
    </>
  );
}

export function InlineError({ message }: { message: string }) {
  return (
    <div className="alert alert-danger" style={{ marginTop: "16px", marginBottom: 0 }}>
      <p style={{ margin: 0 }}>{message}</p>
    </div>
  );
}