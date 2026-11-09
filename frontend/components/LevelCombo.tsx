"use client";

import { useState } from "react";

import { LEVEL_DESC_MAX, LEVEL_NAME_MAX, nextActiveIndex, type LevelItem } from "@/lib/levelSelection";

type Props = {
  id: string;
  label: string;
  options: LevelItem[];
  /** Order of the last level picked from the list (marks it in the list; never shown as a number). */
  selectedOrder: number | null;
  name: string;
  description: string;
  onNameChange: (name: string) => void;
  onPick: (order: number) => void;
  onDescriptionChange: (description: string) => void;
  disabled?: boolean;
  problem?: string | null;
  /** Tests render the open state; the screen always starts closed. */
  initialOpen?: boolean;
};

/**
 * One editable combo box for a level (CR-012, 2nd). A click, the arrow button or ArrowDown opens the list, which
 * ALWAYS shows every option (a browser datalist filters by the typed text and would hide the other levels).
 * Picking fills the name; the same box stays editable. Keys: ArrowDown/ArrowUp move, Enter picks, Esc closes.
 */
export function LevelCombo({
  id,
  label,
  options,
  selectedOrder,
  name,
  description,
  onNameChange,
  onPick,
  onDescriptionChange,
  disabled = false,
  problem = null,
  initialOpen = false,
}: Props) {
  const listId = `${id}-list`;
  const problemId = `${id}-problem`;
  const [open, setOpen] = useState(initialOpen);
  const [active, setActive] = useState(-1);
  const optionId = (i: number) => `${listId}-${i}`;
  const selectedIndex = options.findIndex((o) => o.order === selectedOrder);
  const showList = open && options.length > 0 && !disabled;

  function openList() {
    if (disabled) return;
    setOpen(true);
    setActive(selectedIndex);
  }

  function closeList() {
    setOpen(false);
    setActive(-1);
  }

  function pick(order: number) {
    onPick(order);
    closeList();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        openList();
        return;
      }
      setActive(nextActiveIndex(e.key, active, options.length, selectedIndex));
    } else if (e.key === "Enter" && showList && active >= 0) {
      e.preventDefault();
      pick(options[active].order);
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      e.stopPropagation();
      closeList();
    }
  }

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="combo">
        <input
          id={id}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-haspopup="listbox"
          aria-autocomplete="none"
          aria-activedescendant={showList && active >= 0 ? optionId(active) : undefined}
          aria-invalid={problem ? true : undefined}
          aria-describedby={problem ? problemId : undefined}
          value={name}
          maxLength={LEVEL_NAME_MAX}
          autoComplete="off"
          disabled={disabled}
          onChange={(e) => onNameChange(e.target.value)}
          onClick={openList}
          onKeyDown={onKeyDown}
          onBlur={closeList}
        />
        <button
          type="button"
          className="combo-toggle"
          tabIndex={-1}
          aria-label={`${label} 목록 ${showList ? "닫기" : "열기"}`}
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => (showList ? closeList() : openList())}
        >
          ▾
        </button>
        {showList && (
          <ul className="combo-list" id={listId} role="listbox" aria-label={`${label} 목록`}>
            {options.map((o, i) => (
              <li
                key={o.order}
                id={optionId(i)}
                role="option"
                aria-selected={o.order === selectedOrder}
                className={`combo-option${i === active ? " active" : ""}${o.order === selectedOrder ? " selected" : ""}`}
                onMouseDown={(e) => {
                  e.preventDefault(); // keep the focus in the box so the blur does not close the list first
                  pick(o.order);
                }}
                onMouseEnter={() => setActive(i)}
              >
                {o.name}
              </li>
            ))}
          </ul>
        )}
      </div>
      {problem && (
        <p className="error" id={problemId} role="alert">
          {problem}
        </p>
      )}
      <details className="level-desc">
        <summary>설명 보기·고치기</summary>
        <textarea
          aria-label={`${label} 설명`}
          value={description}
          maxLength={LEVEL_DESC_MAX}
          onChange={(e) => onDescriptionChange(e.target.value)}
        />
      </details>
    </div>
  );
}
