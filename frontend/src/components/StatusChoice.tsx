// 読書ステータスの「読書中」「読了」の選択（本の追加のシート・本の詳細で使う）。

import { Check } from "@phosphor-icons/react";
import { useId } from "react";

import { STATUS_LABELS, type ReadingStatus } from "../api/books";

type Props = {
  value: ReadingStatus;
  onChange: (value: ReadingStatus) => void;
  label?: string;
  disabled?: boolean;
};

export function StatusChoice({ value, onChange, label = "読書ステータス", disabled = false }: Props) {
  const name = useId();
  return (
    <fieldset className="status-choice" disabled={disabled}>
      <legend className="label">{label}</legend>
      <div className="status-options">
        {(["reading", "finished"] as const).map((status) => (
          <label key={status} className="status-option">
            <input
              type="radio"
              name={name}
              value={status}
              checked={value === status}
              onChange={() => onChange(status)}
            />
            <span>
              {status === "finished" && <Check size={14} weight="bold" aria-hidden="true" />}
              {STATUS_LABELS[status]}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
