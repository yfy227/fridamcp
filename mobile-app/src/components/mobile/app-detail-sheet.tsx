"use client";

import { useEffect, useState } from "react";
import {
  X,
  Play,
  Square,
  Server,
  Shield,
  Cpu,
  Clock,
  Wifi,
  FileSearch,
  Activity,
  RefreshCw,
  Trash2,
  CircleCheck,
  CircleDot,
  CircleAlert,
  CircleDashed,
} from "lucide-react";
import type { AppInfo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ConfirmDialog } from "./confirm-dialog";

interface AppDetailSheetProps {
  app: AppInfo | null;
  onClose: () => void;
  onLaunch: (app: AppInfo) => void;
  onToggleMCP: (app: AppInfo) => void;
  onRescan: (app: AppInfo) => void;
  onRemoveInjection: (app: AppInfo) => void;
}

export function AppDetailSheet({
  app,
  onClose,
  onLaunch,
  onToggleMCP,
  onRescan,
  onRemoveInjection,
}: AppDetailSheetProps) {
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false);

  useEffect(() => {
    if (app) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [app]);

  if (!app) return null;

  const isInjected = app.injectionStatus === "injected" || app.injectionStatus === "running";
  const statusConfig = getStatusConfig(app.injectionStatus);

  const handleRemoveClick = () => setShowRemoveConfirm(true);
  const handleRemoveConfirm = () => {
    setShowRemoveConfirm(false);
    onRemoveInjection(app);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      {/* 遮罩 */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm fade-in"
        onClick={onClose}
      />

      {/* 底部面板 */}
      <div className="relative w-full max-w-[480px] max-h-[85vh] overflow-y-auto no-scrollbar rounded-t-3xl bg-card border-t border-border slide-up-enter">
        {/* 拖拽指示器 */}
        <div className="sticky top-0 z-10 flex justify-center pt-3 pb-2 bg-card">
          <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
        </div>

        <div className="px-5 pb-8 space-y-4">
          {/* 头部信息 */}
          <div className="flex items-start gap-3">
            <div
              className="app-icon w-16 h-16 text-2xl"
              style={{ backgroundColor: app.iconColor }}
            >
              {app.iconText}
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-bold text-foreground">{app.appName}</h2>
              <p className="text-xs text-muted-foreground font-mono break-all">{app.packageName}</p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium", statusConfig.bgColor, statusConfig.color)}>
                  <statusConfig.icon className="w-3 h-3" />
                  {statusConfig.label}
                </span>
                <span className="text-xs text-muted-foreground">v{app.version}</span>
              </div>
            </div>
            <button onClick={onClose} className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted">
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* 注入检测详情 */}
          <section className="rounded-2xl bg-muted/30 p-4 space-y-3">
            <h3 className="text-xs font-semibold text-foreground flex items-center gap-2">
              <FileSearch className="w-4 h-4 text-primary" />
              注入检测详情
            </h3>

            <div className="space-y-2.5">
              <DetailRow
                icon={Shield}
                label="注入状态"
                value={statusConfig.label}
                valueClass={statusConfig.color}
              />
              <DetailRow
                icon={Cpu}
                label="检测方式"
                value={getDetectionMethodLabel(app.detectionMethod)}
              />
              {app.gadgetVersion && (
                <DetailRow
                  icon={Activity}
                  label="Gadget 版本"
                  value={`v${app.gadgetVersion}`}
                  valueClass="text-primary"
                />
              )}
              {app.gadgetArch && (
                <DetailRow
                  icon={Cpu}
                  label="注入架构"
                  value={app.gadgetArch}
                />
              )}
              {app.injectedAt && (
                <DetailRow
                  icon={Clock}
                  label="注入时间"
                  value={formatTime(app.injectedAt)}
                />
              )}
              {app.lastScanTime && (
                <DetailRow
                  icon={RefreshCw}
                  label="最后扫描"
                  value={formatTime(app.lastScanTime)}
                />
              )}
              {app.pid && (
                <DetailRow
                  icon={Activity}
                  label="进程 PID"
                  value={app.pid.toString()}
                  valueClass="text-amber-400"
                />
              )}
              {app.mcpPort && (
                <DetailRow
                  icon={Wifi}
                  label="Gadget 端口"
                  value={app.mcpPort.toString()}
                />
              )}
            </div>

            {/* 检测方法说明 */}
            <div className="pt-2 border-t border-border/50">
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                {getDetectionDescription(app.detectionMethod, app.injectionStatus)}
              </p>
            </div>
          </section>

          {/* MCP 服务状态 */}
          {isInjected && (
            <section className="rounded-2xl bg-muted/30 p-4 space-y-3">
              <h3 className="text-xs font-semibold text-foreground flex items-center gap-2">
                <Server className="w-4 h-4 text-primary" />
                MCP 服务
              </h3>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "status-dot",
                    app.mcpStatus === "online" ? "bg-primary scan-pulse" :
                    app.mcpStatus === "starting" ? "bg-amber-400" :
                    app.mcpStatus === "error" ? "bg-destructive" : "bg-muted-foreground"
                  )} />
                  <span className="text-sm text-foreground">
                    {app.mcpStatus === "online" ? "服务在线" :
                     app.mcpStatus === "starting" ? "启动中..." :
                     app.mcpStatus === "error" ? "服务异常" : "服务离线"}
                  </span>
                </div>
                {app.mcpPort && (
                  <span className="text-xs font-mono text-muted-foreground">:{app.mcpPort}</span>
                )}
              </div>
            </section>
          )}

          {/* 操作按钮 */}
          <div className="space-y-2 pt-1">
            {isInjected && (
              <button
                onClick={() => onLaunch(app)}
                className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-muted/50 text-foreground font-medium text-sm hover:bg-muted transition-colors"
              >
                <Play className="w-4 h-4" />
                {app.injectionStatus === "running" ? "应用运行中" : "启动应用"}
              </button>
            )}

            {isInjected && (
              <button
                onClick={() => onToggleMCP(app)}
                className={cn(
                  "w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-colors",
                  app.mcpStatus === "online"
                    ? "bg-destructive/15 text-destructive hover:bg-destructive/25"
                    : "bg-primary text-primary-foreground hover:bg-primary/90"
                )}
              >
                {app.mcpStatus === "online" ? <Square className="w-4 h-4" /> : <Server className="w-4 h-4" />}
                {app.mcpStatus === "online" ? "停止 MCP 服务" : "拉起 MCP 服务"}
              </button>
            )}

            <div className="flex gap-2">
              <button
                onClick={() => onRescan(app)}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-muted/30 text-muted-foreground font-medium text-xs hover:bg-muted transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                重新检测
              </button>
              {isInjected && (
                <button
                  onClick={handleRemoveClick}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-destructive/10 text-destructive font-medium text-xs hover:bg-destructive/20 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  移除注入
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 移除注入确认对话框 */}
      <ConfirmDialog
        open={showRemoveConfirm}
        title="移除注入"
        desc={`确定要移除 ${app.appName} 的 frida-gadget 注入吗？移除后需要重新注入才能使用 Frida 功能。`}
        confirmLabel="移除注入"
        variant="danger"
        onConfirm={handleRemoveConfirm}
        onCancel={() => setShowRemoveConfirm(false)}
      />
    </div>
  );
}

function DetailRow({
  icon: Icon,
  label,
  value,
  valueClass,
}: {
  icon: typeof Shield;
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="w-3.5 h-3.5" />
        <span className="text-xs">{label}</span>
      </div>
      <span className={cn("text-xs font-medium font-mono", valueClass || "text-foreground")}>
        {value}
      </span>
    </div>
  );
}

function getStatusConfig(status: AppInfo["injectionStatus"]) {
  switch (status) {
    case "running":
      return { icon: CircleDot, label: "运行中", color: "text-amber-400", bgColor: "bg-amber-400/10" };
    case "injected":
      return { icon: CircleCheck, label: "已注入", color: "text-primary", bgColor: "bg-primary/10" };
    case "error":
      return { icon: CircleAlert, label: "注入异常", color: "text-destructive", bgColor: "bg-destructive/10" };
    default:
      return { icon: CircleDashed, label: "未注入", color: "text-muted-foreground", bgColor: "bg-muted/30" };
  }
}

function getDetectionMethodLabel(method?: AppInfo["detectionMethod"]): string {
  switch (method) {
    case "static":
      return "静态扫描 (APK 内 libfrida-gadget.so)";
    case "runtime":
      return "运行时检测 (端口 27042 监听)";
    case "process":
      return "进程检测 (已加载 gadget 模块)";
    case "none":
      return "未检测到注入";
    default:
      return "—";
  }
}

function getDetectionDescription(method: AppInfo["detectionMethod"], status: AppInfo["injectionStatus"]): string {
  if (status === "not_injected") {
    return "该应用尚未注入 frida-gadget。可通过「注入」标签页选择 APK 文件进行注入。";
  }
  switch (method) {
    case "static":
      return "通过解析 APK 文件，在 lib/arm64-v8a/ 等目录中检测到 libfrida-gadget.so 文件，确认该应用已被静态注入。";
    case "runtime":
      return "检测到该应用进程已启动，且 frida-gadget 正在监听端口 27042，可通过 frida -U Gadget 连接。";
    case "process":
      return "通过扫描进程内存映射，检测到已加载的 frida-gadget 共享库。";
    default:
      return "检测方式未知。";
  }
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now.getTime() - timestamp;
  if (diff < 60000) return "刚刚";
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
  const m = (date.getMonth() + 1).toString().padStart(2, "0");
  const d = date.getDate().toString().padStart(2, "0");
  const h = date.getHours().toString().padStart(2, "0");
  const min = date.getMinutes().toString().padStart(2, "0");
  return `${m}-${d} ${h}:${min}`;
}
