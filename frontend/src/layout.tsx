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
      <header className="app-header">
        <div className="header-container">
          <span>Online Consultation</span>
          {practiceName && (
            <span className="practice-tag">{practiceName}</span>
          )}
        </div>
      </header>
      <div className="page-container">
        <div className="screen-card">{children}</div>
      </div>
    </>
  );
}

export function FieldError({ id, message }: { id?: string; message: string }) {
  return (
    <p id={id} className="error-message">
      <span className="sr-only">Error: </span>
      {message}
    </p>
  );
}

export function InlineError({ message }: { message: string }) {
  return (
    <div className="alert alert-danger" role="alert" style={{ marginTop: "16px", marginBottom: 0 }}>
      <p style={{ margin: 0 }}>
        <span className="sr-only">Error: </span>
        {message}
      </p>
    </div>
  );
}