"use client";

import { useEffect, useCallback, useRef, useState } from "react";
import { CheckCircle2, Info, AlertCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastType = "success" | "error" | "info" | "warning";

export interface ToastItem {
  id: string;
  msg: string;
  type: ToastType;
}

interface ToastContainerProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

const toastConfig: Record<ToastType, { icon: typeof CheckCircle2; bg: string; iconColor: string }> = {
  success: { icon: CheckCircle2, bg: "bg-primary text-primary-foreground", iconColor: "text-primary-foreground" },
  error: { icon: AlertCircle, bg: "bg-destructive text-white", iconColor: "text-white" },
  warning: { icon: AlertCircle, bg: "bg-amber-500 text-white", iconColor: "text-white" },
  info: { icon: Info, bg: "bg-card border border-border text-foreground", iconColor: "text-primary" },
};

/**
 * Toast 通知容器
 * 支持自动消失、堆叠显示、手动关闭
 */
export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  return (
    <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-[70] flex flex-col items-center gap-2 w-full max-w-[360px] px-4 pointer-events-none">
      {toasts.map((toast) => (
        <ToastView key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastView({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const config = toastConfig[toast.type];
  const Icon = config.icon;
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    timerRef.current = setTimeout(() => onDismiss(toast.id), 3000);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [toast.id, onDismiss]);

  return (
    <div
      className={cn(
        "pointer-events-auto flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-medium shadow-lg fade-in w-full",
        config.bg
      )}
    >
      <Icon className={cn("w-4 h-4 shrink-0", config.iconColor)} />
      <span className="flex-1">{toast.msg}</span>
      <button
        onClick={() => onDismiss(toast.id)}
        className="shrink-0 opacity-70 hover:opacity-100 transition-opacity"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

/**
 * useToast Hook - 管理 Toast 队列
 */
export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback((msg: string, type: ToastType = "info") => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    setToasts((prev) => [...prev.slice(-2), { id, msg, type }]); // 最多保留 3 条
  }, []);

  return { toasts, showToast, dismiss };
}
