import { useState } from "react";
import { useToast } from "./Toasts.jsx";

/** Кнопка, которая сама показывает «занято» и превращает ошибку в тост. */
export function Button({ onClick, kind = "", small, disabled, children, type = "button", ...rest }) {
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const cls = ["btn", kind, small && "small", busy && "busy"].filter(Boolean).join(" ");
  const handle = async (e) => {
    if (!onClick) return;
    setBusy(true);
    try {
      await onClick(e);
    } catch (err) {
      toast(err.message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <button type={type} className={cls} disabled={disabled || busy} onClick={handle} {...rest}>
      {children}
    </button>
  );
}

/** Сегментированный переключатель. options: [{ v, label }] */
export function Seg({ options, value, onChange, small, disabled }) {
  return (
    <div className={"seg" + (small ? " small" : "")} role="radiogroup">
      {options.map((o) => (
        <button
          key={o.v}
          type="button"
          role="radio"
          aria-checked={value === o.v}
          data-v={o.v}
          className={value === o.v ? "on" : ""}
          disabled={disabled}
          onClick={() => value !== o.v && onChange?.(o.v)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Switch({ checked, disabled, onChange, children }) {
  return (
    <label className="switch">
      <input type="checkbox" checked={!!checked} disabled={disabled} onChange={(e) => onChange?.(e.target.checked)} />
      <span className="track"><span className="knob" /></span>
      <span className="switch-text">{children}</span>
    </label>
  );
}

export function Lamp({ state, small }) {
  return <div className={"bigLamp" + (small ? " small" : "") + (state ? " on-" + state : "")} />;
}

/** Хук для действий без кнопки (сегменты, тумблеры): ошибки — в тост. */
export function useAction() {
  const toast = useToast();
  return async (fn) => {
    try {
      return await fn();
    } catch (err) {
      toast(err.message, true);
    }
  };
}
