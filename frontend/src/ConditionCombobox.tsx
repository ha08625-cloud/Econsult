// File path: frontend/src/ConditionCombobox.tsx
/**
 * ConditionCombobox.tsx
 *
 * Custom combobox for condition selection on Screen 0.
 *
 * Behaviour:
 * - Click/focus: opens suggestion list showing all conditions
 * - Typing: filters list using filterConditions (label, tag, fuzzy)
 * - Mouse click on suggestion: selects condition
 * - Keyboard: ArrowDown/ArrowUp to navigate, Enter to select, Escape/Tab to close
 * - Blur: closes list after short delay to allow click events to fire first
 * - On selection: input shows condition label, onChange called with condition id
 * - On typing after selection: selection is cleared (onChange called with null)
 * - On mount: if selectedId is provided, the input is pre-filled with that
 *   condition's label. This is a one-time lookup, not a live sync — if the
 *   parent needs the displayed text to re-sync to a changed selectedId after
 *   mount, it must remount this component (e.g. via a changing `key` prop).
 *
 * Filtering is always from the full canonical conditions list, never incremental.
 */

import React, { useState, useRef, useId, useEffect } from "react";
import type { ConditionSummary } from "./types";
import { filterConditions } from "./search";

interface ConditionComboboxProps {
  conditions: ConditionSummary[];
  selectedId: string | null;
  onChange: (id: string | null) => void;
  labelId: string;
}

const SUGGESTION_LIST_MAX_HEIGHT = 300;

export default function ConditionCombobox({
  conditions,
  selectedId,
  onChange,
  labelId,
}: ConditionComboboxProps) {
  // One-time lookup on mount: if selectedId is already set (e.g. the patient
  // is returning to this screen having previously picked a condition), show
  // its label immediately instead of starting blank. This does not re-run
  // on prop changes — only on mount — by design of useState's lazy initialiser.
  const [inputValue, setInputValue] = useState<string>(() => {
    if (selectedId === null) return "";
    const match = conditions.find((c) => c.id === selectedId);
    return match ? match.label : "";
  });
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  // True once the patient has actually typed a character since this
  // component mounted. A mount-time prefill (above) sets inputValue without
  // this becoming true, so opening the list right after mounting shows every
  // condition rather than immediately filtering down to the one match for
  // the prefilled label. Once they type, filtering behaves as before.
  const [hasTyped, setHasTyped] = useState<boolean>(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const blurTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear any pending blur-close timeout if the component unmounts before
  // it fires (e.g. the patient navigates away mid-blur-delay). Without this,
  // the timeout still fires after unmount and calls closeList(), which is a
  // no-op in React 18+ but is still a leftover timer with nothing left to do.
  useEffect(() => {
    return () => {
      if (blurTimeoutRef.current !== null) {
        clearTimeout(blurTimeoutRef.current);
      }
    };
  }, []);

  // Unique ids for ARIA — useId ensures no collisions if component is rendered
  // multiple times on the same page.
  const baseId = useId();
  const listboxId = `${baseId}-listbox`;
  const optionId = (conditionId: string) => `${baseId}-option-${conditionId}`;

  // Derived — never stored in state. Always computed from the full canonical list.
  // Filtering is skipped until the patient has typed (see hasTyped above),
  // so a mount-time label prefill doesn't pre-filter the list to one match.
  const filteredConditions: ConditionSummary[] = hasTyped
    ? filterConditions(conditions, inputValue)
    : conditions;

  // True when the user has typed something but no tags/labels matched,
  // so filterConditions fell back to the full list.
  const noMatchFallback: boolean =
    inputValue.trim().length > 0 &&
    filteredConditions.length === conditions.length &&
    !conditions.some((c) =>
      c.label.toLowerCase().includes(inputValue.toLowerCase().trim())
    );

  // Announced via the aria-live status region below, not via the listbox
  // (whose children must all be role="option"/"group" — see combobox-info-item
  // rows further down, which are role="presentation" and thus invisible to
  // aria-activedescendant navigation).
  const statusMessage: string = !isOpen
    ? ""
    : noMatchFallback
      ? "No matching conditions — try different words, or scroll below."
      : filteredConditions.length < conditions.length
        ? `Showing ${filteredConditions.length} of ${conditions.length} conditions`
        : hasTyped
          ? `${filteredConditions.length} conditions available`
          : "";

  // --- Helpers ---

  function selectCondition(condition: ConditionSummary) {
    setInputValue(condition.label);
    setIsOpen(false);
    setActiveIndex(null);
    onChange(condition.id);
  }

  function closeList() {
    setIsOpen(false);
    setActiveIndex(null);
  }

  // --- Event handlers ---

  function handleFocus() {
    // Cancel any pending blur-close so focusing back in doesn't flicker.
    if (blurTimeoutRef.current !== null) {
      clearTimeout(blurTimeoutRef.current);
      blurTimeoutRef.current = null;
    }
    setIsOpen(true);
  }

  function handleBlur() {
    // Delay closing so a mousedown on a suggestion fires before the list disappears.
    blurTimeoutRef.current = setTimeout(() => {
      closeList();
    }, 150);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value;
    setInputValue(value);
    setHasTyped(true);
    setIsOpen(true);
    setActiveIndex(null);
    // Typing invalidates any previous selection.
    onChange(null);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        setIsOpen(true);
        e.preventDefault();
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown": {
        e.preventDefault();
        if (filteredConditions.length === 0) break;
        const nextIndex =
          activeIndex === null
            ? 0
            : (activeIndex + 1) % filteredConditions.length;
        setActiveIndex(nextIndex);
        break;
      }

      case "ArrowUp": {
        e.preventDefault();
        if (filteredConditions.length === 0) break;
        const prevIndex =
          activeIndex === null
            ? filteredConditions.length - 1
            : (activeIndex - 1 + filteredConditions.length) %
              filteredConditions.length;
        setActiveIndex(prevIndex);
        break;
      }

      case "Enter": {
        e.preventDefault();
        if (activeIndex !== null && filteredConditions[activeIndex]) {
          selectCondition(filteredConditions[activeIndex]);
        }
        break;
      }

      case "Escape": {
        e.preventDefault();
        closeList();
        break;
      }

      case "Tab": {
        // Do not preventDefault — allow natural tab flow.
        closeList();
        break;
      }
    }
  }

  function handleSuggestionMouseDown(condition: ConditionSummary) {
    // mousedown fires before blur, so cancelling the blur timeout here
    // ensures the list does not close before the selection registers.
    if (blurTimeoutRef.current !== null) {
      clearTimeout(blurTimeoutRef.current);
      blurTimeoutRef.current = null;
    }
    selectCondition(condition);
  }

  // --- Render ---

  const activeDescendant =
    activeIndex !== null && filteredConditions[activeIndex]
      ? optionId(filteredConditions[activeIndex].id)
      : undefined;

  return (
    <div className="combobox-wrapper">
      <input
        ref={inputRef}
        id={`${baseId}-input`}
        type="text"
        role="combobox"
        aria-expanded={isOpen}
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-activedescendant={activeDescendant}
        aria-labelledby={labelId}
        value={inputValue}
        onChange={handleInputChange}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        placeholder="Start typing or click to see all conditions..."
        autoComplete="off"
        className="combobox-input"
      />

      <div aria-live="polite" className="sr-only">
        {statusMessage}
      </div>

      {isOpen && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="Conditions"
          className="combobox-listbox"
          style={{ maxHeight: SUGGESTION_LIST_MAX_HEIGHT }}
        >
          {noMatchFallback && (
            <li className="combobox-info-item" role="presentation">
              No matching conditions — try different words, or scroll below.
            </li>
          )}

          {!noMatchFallback &&
            filteredConditions.length < conditions.length && (
              <li className="combobox-info-item" role="presentation">
                Showing {filteredConditions.length} of {conditions.length}{" "}
                conditions
              </li>
            )}

          {filteredConditions.map((condition, index) => {
            const isActive = index === activeIndex;
            const isSelected = condition.id === selectedId;

            return (
              <li
                key={condition.id}
                id={optionId(condition.id)}
                role="option"
                aria-selected={isSelected}
                onMouseDown={() => handleSuggestionMouseDown(condition)}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseLeave={() => setActiveIndex(null)}
                className={[
                  "combobox-option",
                  isActive ? "combobox-option--active" : "",
                  isSelected ? "combobox-option--selected" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {condition.label}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
