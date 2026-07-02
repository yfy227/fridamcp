"use client";

import { useEffect } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  desc: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "warning";
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * 确认对话框
 * 用于移除注入、停止服务等危险操作的二次确认
 */
export function ConfirmDialog({
  open,
  title,
  desc,
  confirmLabel = "确认",
  cancelLabel = "取消",
  variant = "danger",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  const isDanger = variant === "danger";

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm fade-in" onClick={onCancel} />
      <div className="relative w-full max-w-[320px] rounded-2xl bg-card border border-border p-5 slide-up-enter">
        <button
          onClick={onCancel}
          className="absolute top-3 right-3 w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted/50 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-3 ${
          isDanger ? "bg-destructive/10" : "bg-amber-400/10"
        }`}>
          <AlertTriangle className={`w-6 h-6 ${isDanger ? "text-destructive" : "text-amber-400"}`} />
        </div>

        <h3 className="text-base font-semibold text-foreground mb-1.5">{title}</h3>
        <p className="text-xs text-muted-foreground leading-relaxed mb-5">{desc}</p>

        <div className="flex gap-2.5">
          <button
            onClick={onCancel}
            className="flex-1 py-2.5 rounded-xl bg-muted/50 text-foreground text-sm font-medium hover:bg-muted transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition-colors ${
              isDanger
                ? "bg-destructive text-white hover:bg-destructive/90"
                : "bg-amber-500 text-white hover:bg-amber-500/90"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
