// トースト（visual.md 11章）。成功の知らせだけに使う。操作は置かない。
// 15文字までは2秒、16文字以上は2.5秒。200ms で出て、150ms で消える。

import { CheckCircle } from "@phosphor-icons/react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { countChars } from "../lib/text";

type ToastState = { id: number; message: string; leaving: boolean } | null;

const ToastContext = createContext<(message: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState>(null);
  const timers = useRef<number[]>([]);

  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };

  const show = useCallback((message: string) => {
    clearTimers();
    const id = Date.now();
    const duration = countChars(message) <= 15 ? 2000 : 2500;
    setToast({ id, message, leaving: false });
    timers.current.push(
      window.setTimeout(() => setToast((t) => (t && t.id === id ? { ...t, leaving: true } : t)), duration),
      window.setTimeout(() => setToast((t) => (t && t.id === id ? null : t)), duration + 150),
    );
  }, []);

  useEffect(() => clearTimers, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {toast && (
          <div key={toast.id} className={`toast${toast.leaving ? " leaving" : ""}`}>
            <CheckCircle size={20} weight="fill" aria-hidden="true" className="toast-check" />
            <span>{toast.message}</span>
          </div>
        )}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): (message: string) => void {
  return useContext(ToastContext);
}
