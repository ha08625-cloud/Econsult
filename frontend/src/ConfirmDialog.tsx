// File path: frontend/src/ConfirmDialog.tsx
// Shared accessible dialog primitive for the modal overlays used across the
// patient flow (condition-change warning, back-navigation warning, photo
// guide). Implements the behaviour WCAG 2.1 AA requires for a modal dialog:
// role="dialog", aria-modal, an accessible name, focus moved in on open,
// a Tab focus trap, Escape to close, and focus returned to the triggering
// element on close.
import { useEffect, useId, useRef, type ReactNode } from "react";

const FOCUSABLE_SELECTOR =
  "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

interface ConfirmDialogProps {
  /** Visible heading rendered inside the dialog and referenced via aria-labelledby. */
  title?: string;
  /** Accessible name to use when the dialog has no visible heading. Ignored if `title` is set. */
  ariaLabel?: string;
  /**
   * Called on Escape. Callers must map this to the safe / non-destructive
   * option, matching the button that receives initial focus.
   */
  onEscape: () => void;
  /** Called on backdrop click. Omit to make the backdrop inert. */
  onOverlayClick?: () => void;
  className?: string;
  children: ReactNode;
}

export default function ConfirmDialog({
  title,
  ariaLabel,
  onEscape,
  onOverlayClick,
  className,
  children,
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const previouslyFocused = useRef<HTMLElement | null>(null);

  // Move focus to the first focusable element (by DOM order — callers put
  // the safe/non-destructive button first) when the dialog opens, and
  // return focus to whatever triggered it when the dialog closes.
  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const first = panelRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
    first?.focus();
    return () => {
      previouslyFocused.current?.focus();
    };
  }, []);

  // Escape closes the dialog; Tab/Shift+Tab is trapped inside it while open.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onEscape();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onEscape]);

  return (
    <div
      className="modal-overlay"
      onClick={() => onOverlayClick?.()}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? titleId : undefined}
      aria-label={title ? undefined : ariaLabel}
    >
      <div
        ref={panelRef}
        className={className ?? "modal-panel"}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <h2 id={titleId} className="modal-title">
            {title}
          </h2>
        )}
        {children}
      </div>
    </div>
  );
}
