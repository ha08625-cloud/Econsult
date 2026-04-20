// layout.tsx
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

/**
 * WCAG 2.1 AA Compliant Error Message
 * Includes visually hidden "Error: " prefix for screen readers.
 */
export function InlineError({ message }: { message: string }) {
  return (
    <p className="nhsuk-error-message">
      <span className="nhsuk-u-visually-hidden">Error: </span>
      {message}
    </p>
  );
}
