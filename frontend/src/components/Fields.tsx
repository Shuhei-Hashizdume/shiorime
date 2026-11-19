import { Eye, EyeSlash } from "@phosphor-icons/react";
import { forwardRef, useId, useState, type InputHTMLAttributes } from "react";

import { FieldErrorText } from "./Feedback";

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  label: string;
  error?: string;
  hint?: string;
};

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, error, hint, ...inputProps },
  ref,
) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(" ");
  return (
    <div className="field-group">
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <div className={`input-wrap${error ? " invalid" : ""}`}>
        <input
          ref={ref}
          id={id}
          className="input"
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          {...inputProps}
        />
      </div>
      {hint && (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && <FieldErrorText id={`${id}-error`}>{error}</FieldErrorText>}
    </div>
  );
});

type PasswordFieldProps = Omit<TextFieldProps, "type">;

/** 目のアイコンで、入力した文字を表示できるパスワードの欄（screens.md 10.） */
export const PasswordField = forwardRef<HTMLInputElement, PasswordFieldProps>(function PasswordField(
  { label, error, hint, ...inputProps },
  ref,
) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(" ");
  return (
    <div className="field-group">
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <div className={`input-wrap${error ? " invalid" : ""}`}>
        <input
          ref={ref}
          id={id}
          className="input"
          type={visible ? "text" : "password"}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          {...inputProps}
        />
        <button
          type="button"
          className="icon-button"
          aria-label={visible ? "パスワードを隠す" : "パスワードを表示"}
          aria-pressed={visible}
          onClick={() => setVisible((v) => !v)}
        >
          {visible ? <EyeSlash size={22} aria-hidden="true" /> : <Eye size={22} aria-hidden="true" />}
        </button>
      </div>
      {hint && (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && <FieldErrorText id={`${id}-error`}>{error}</FieldErrorText>}
    </div>
  );
});
