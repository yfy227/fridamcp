"use client";

import { useState, useMemo } from "react";
import {
  Search,
  RefreshCw,
  Filter,
  CircleCheck,
  CircleDot,
  CircleAlert,
  CircleDashed,
  Play,
  Square,
  Server,
  ChevronRight,
  X,
} from "lucide-react";
import type { AppInfo, InjectionStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AppsScreenProps {
  apps: AppInfo[];
  scanning: boolean;
  onScan: () => void;
  onSelectApp: (app: AppInfo) => void;
  onLaunchApp: (app: AppInfo) => void;
  onToggleMCP: (app: AppInfo) => void;
}

type FilterType = "all" | "injected" | "running" | "not_injected" | "error";

export function AppsScreen({
  apps,
  scanning,
  onScan,
  onSelectApp,
  onLaunchApp,
  onToggleMCP,
}: AppsScreenProps) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterType>("all");
  const [showFilter, setShowFilter] = useState(false);

  const filteredApps = useMemo(() => {
    return apps.filter((app) => {
      // 搜索过滤
      if (search) {
        const q = search.toLowerCase();
        if (
          !app.appName.toLowerCase().includes(q) &&
          !app.packageName.toLowerCase().includes(q)
        ) {
          return false;
        }
      }
      // 状态过滤
      if (filter === "all") return true;
      if (filter === "injected")
        return app.injectionStatus === "injected" || app.injectionStatus === "running";
      if (filter === "running") return app.injectionStatus === "running";
      if (filter === "not_injected") return app.injectionStatus === "not_injected";
      if (filter === "error") return app.injectionStatus === "error";
      return true;
    });
  }, [apps, search, filter]);

  const injectedCount = apps.filter(
    (a) => a.injectionStatus === "injected" || a.injectionStatus === "running"
  ).length;

  const filterOptions: { value: FilterType; label: string; count: number }[] = [
    { value: "all", label: "全部", count: apps.length },
    { value: "injected", label: "已注入", count: injectedCount },
    { value: "running", label: "运行中", count: apps.filter((a) => a.injectionStatus === "running").length },
    { value: "not_injected", label: "未注入", count: apps.filter((a) => a.injectionStatus === "not_injected").length },
    { value: "error", label: "异常", count: apps.filter((a) => a.injectionStatus === "error").length },
  ];

  return (
    <div className="px-4 pb-6 space-y-3 fade-in">
      {/* 搜索栏 */}
      <div className="flex items-center gap-2">
        <div className="flex-1 flex items-center gap-2 px-3 py-2 rounded-xl bg-card border border-border">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索应用名或包名..."
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none min-w-0"
          />
          {search && (
            <button onClick={() => setSearch("")} className="text-muted-foreground hover:text-foreground">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        <button
          onClick={() => setShowFilter(!showFilter)}
          className={cn(
            "p-2.5 rounded-xl border transition-colors",
            showFilter || filter !== "all"
              ? "bg-primary/15 border-primary/30 text-primary"
              : "bg-card border-border text-muted-foreground"
          )}
        >
          <Filter className="w-4 h-4" />
        </button>
      </div>

      {/* 过滤标签栏 */}
      {showFilter && (
        <div className="flex items-center gap-2 overflow-x-auto no-scrollbar pb-1 fade-in">
          {filterOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                setFilter(opt.value);
                setShowFilter(false);
              }}
              className={cn(
                "shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors",
                filter === opt.value
                  ? "bg-primary text-primary-foreground"
                  : "bg-card border border-border text-muted-foreground hover:text-foreground"
              )}
            >
              {opt.label} ({opt.count})
            </button>
          ))}
        </div>
      )}

      {/* 扫描状态条 */}
      <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-card border border-border">
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-2 h-2 rounded-full",
            scanning ? "bg-primary scan-pulse" : "bg-muted-foreground"
          )} />
          <span className="text-xs text-muted-foreground">
            {scanning ? "正在扫描已注入应用..." : `检测到 ${injectedCount} 个已注入应用`}
          </span>
        </div>
        <button
          onClick={onScan}
          disabled={scanning}
          className="flex items-center gap-1 text-xs text-primary font-medium disabled:opacity-50"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", scanning && "animate-spin")} />
          扫描
        </button>
      </div>

      {/* 当前过滤提示 */}
      {filter !== "all" && (
        <div className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-primary/5">
          <span className="text-xs text-primary">
            筛选: {filterOptions.find((f) => f.value === filter)?.label} · {filteredApps.length} 个结果
          </span>
          <button onClick={() => setFilter("all")} className="text-xs text-muted-foreground hover:text-foreground">
            清除
          </button>
        </div>
      )}

      {/* 应用列表 */}
      <div className="space-y-2">
        {filteredApps.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <CircleDashed className="w-10 h-10 text-muted-foreground/50 mb-3" />
            <p className="text-sm text-muted-foreground">没有匹配的应用</p>
            <p className="text-xs text-muted-foreground/70 mt-1">尝试调整搜索或筛选条件</p>
          </div>
        ) : (
          filteredApps.map((app) => (
            <AppCard
              key={app.id}
              app={app}
              onSelect={() => onSelectApp(app)}
              onLaunch={() => onLaunchApp(app)}
              onToggleMCP={() => onToggleMCP(app)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function AppCard({
  app,
  onSelect,
  onLaunch,
  onToggleMCP,
}: {
  app: AppInfo;
  onSelect: () => void;
  onLaunch: () => void;
  onToggleMCP: () => void;
}) {
  const statusConfig = getStatusConfig(app.injectionStatus);

  return (
    <div
      className={cn(
        "rounded-2xl border p-3 transition-all",
        app.injectionStatus === "running"
          ? "bg-primary/5 border-primary/20"
          : "bg-card border-border"
      )}
    >
      <button onClick={onSelect} className="w-full flex items-center gap-3 text-left">
        {/* 应用图标 */}
        <div
          className="app-icon w-12 h-12 text-lg"
          style={{ backgroundColor: app.iconColor }}
        >
          {app.iconText}
        </div>

        {/* 应用信息 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground truncate">{app.appName}</h3>
            {app.isSystem && (
              <span className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-medium bg-muted text-muted-foreground">
                系统
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground font-mono truncate">{app.packageName}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium", statusConfig.bgColor, statusConfig.color)}>
              <statusConfig.icon className="w-2.5 h-2.5" />
              {statusConfig.label}
            </span>
            {app.gadgetVersion && (
              <span className="text-[10px] text-muted-foreground font-mono">
                gadget v{app.gadgetVersion}
              </span>
            )}
            {app.pid && (
              <span className="text-[10px] text-amber-400 font-mono">PID {app.pid}</span>
            )}
          </div>
        </div>

        <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
      </button>

      {/* 操作按钮 - 仅对已注入/运行中的应用显示 */}
      {(app.injectionStatus === "injected" || app.injectionStatus === "running") && (
        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border/50">
          <button
            onClick={onLaunch}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-muted/50 text-foreground hover:bg-muted transition-colors"
          >
            <Play className="w-3.5 h-3.5" />
            {app.injectionStatus === "running" ? "已运行" : "启动应用"}
          </button>
          <button
            onClick={onToggleMCP}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-semibold transition-colors",
              app.mcpStatus === "online"
                ? "bg-destructive/15 text-destructive hover:bg-destructive/25"
                : "bg-primary text-primary-foreground hover:bg-primary/90"
            )}
          >
            {app.mcpStatus === "online" ? <Square className="w-3.5 h-3.5" /> : <Server className="w-3.5 h-3.5" />}
            {app.mcpStatus === "online" ? "停止 MCP" : "拉起 MCP"}
          </button>
        </div>
      )}
    </div>
  );
}

function getStatusConfig(status: InjectionStatus) {
  switch (status) {
    case "running":
      return {
        icon: CircleDot,
        label: "运行中",
        color: "text-amber-400",
        bgColor: "bg-amber-400/10",
      };
    case "injected":
      return {
        icon: CircleCheck,
        label: "已注入",
        color: "text-primary",
        bgColor: "bg-primary/10",
      };
    case "error":
      return {
        icon: CircleAlert,
        label: "注入异常",
        color: "text-destructive",
        bgColor: "bg-destructive/10",
      };
    default:
      return {
        icon: CircleDashed,
        label: "未注入",
        color: "text-muted-foreground",
        bgColor: "bg-muted/30",
      };
  }
}
