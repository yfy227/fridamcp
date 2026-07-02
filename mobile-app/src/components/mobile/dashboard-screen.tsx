"use client";

import { useState } from "react";
import {
  Smartphone,
  Server,
  Zap,
  Activity,
  Shield,
  Cpu,
  Wifi,
  RefreshCw,
  Play,
  Square,
  ChevronRight,
  CircleCheck,
  CircleAlert,
  CircleDot,
} from "lucide-react";
import type { DeviceInfo, MCPServerStatus, AppInfo, MCPSession } from "@/lib/types";
import { cn } from "@/lib/utils";

interface DashboardScreenProps {
  device: DeviceInfo;
  mcpServer: MCPServerStatus;
  apps: AppInfo[];
  sessions: MCPSession[];
  onRefresh: () => void;
  onToggleMCPServer: () => void;
  onNavigateApps: () => void;
  onNavigateMCP: () => void;
}

export function DashboardScreen({
  device,
  mcpServer,
  apps,
  sessions,
  onRefresh,
  onToggleMCPServer,
  onNavigateApps,
  onNavigateMCP,
}: DashboardScreenProps) {
  const [scanning, setScanning] = useState(false);

  const injectedApps = apps.filter(
    (a) => a.injectionStatus === "injected" || a.injectionStatus === "running"
  );
  const runningApps = apps.filter((a) => a.injectionStatus === "running");
  const errorApps = apps.filter((a) => a.injectionStatus === "error");

  const handleScan = () => {
    setScanning(true);
    setTimeout(() => {
      setScanning(false);
      onRefresh();
    }, 2000);
  };

  return (
    <div className="px-4 pb-6 space-y-4 fade-in">
      {/* 设备状态卡片 */}
      <section className="rounded-2xl bg-card border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={cn(
              "w-10 h-10 rounded-xl flex items-center justify-center",
              device.status === "connected" ? "bg-primary/15 text-primary" : "bg-destructive/15 text-destructive"
            )}>
              <Smartphone className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-foreground">{device.name}</h2>
              <p className="text-xs text-muted-foreground font-mono">{device.id}</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={cn(
              "status-dot",
              device.status === "connected" ? "bg-primary scan-pulse" : "bg-destructive"
            )} />
            <span className="text-xs font-medium text-muted-foreground">
              {device.status === "connected" ? "已连接" : "未连接"}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 pt-1">
          <InfoChip icon={Cpu} label="架构" value={device.arch} />
          <InfoChip icon={Activity} label="系统" value={`Android ${device.androidVersion}`} />
          <InfoChip icon={Shield} label="Root" value={device.isRooted ? "已获取" : "未获取"} />
        </div>

        <div className="flex items-center justify-between pt-1 border-t border-border/50">
          <div className="flex items-center gap-2">
            <Zap className={cn("w-4 h-4", device.fridaServerRunning ? "text-primary" : "text-muted-foreground")} />
            <span className="text-xs text-muted-foreground">Frida Server</span>
          </div>
          <div className="flex items-center gap-2">
            {device.fridaServerRunning ? (
              <>
                <span className="text-xs font-mono text-primary">v{device.fridaServerVersion}</span>
                <span className="text-xs text-primary font-medium">运行中</span>
              </>
            ) : (
              <span className="text-xs text-destructive font-medium">未运行</span>
            )}
          </div>
        </div>
      </section>

      {/* MCP 服务器控制卡片 */}
      <section className="rounded-2xl bg-gradient-to-br from-primary/10 to-card border border-primary/20 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={cn(
              "w-10 h-10 rounded-xl flex items-center justify-center",
              mcpServer.running ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
            )}>
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-foreground">MCP 服务</h2>
              <p className="text-xs text-muted-foreground font-mono">
                {mcpServer.host}:{mcpServer.port} · {mcpServer.transport.toUpperCase()}
              </p>
            </div>
          </div>
          <button
            onClick={onToggleMCPServer}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
              mcpServer.running
                ? "bg-destructive/15 text-destructive hover:bg-destructive/25"
                : "bg-primary text-primary-foreground hover:bg-primary/90"
            )}
          >
            {mcpServer.running ? <Square className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            {mcpServer.running ? "停止" : "启动"}
          </button>
        </div>

        {mcpServer.running && (
          <div className="grid grid-cols-3 gap-2">
            <StatBox label="活跃会话" value={mcpServer.activeSessions} />
            <StatBox label="工具总数" value={mcpServer.totalTools} />
            <StatBox label="AI 客户端" value={mcpServer.connectedClients} />
          </div>
        )}
      </section>

      {/* 注入检测概览 */}
      <section className="rounded-2xl bg-card border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Shield className="w-4 h-4 text-primary" />
            注入检测概览
          </h2>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-primary/10 text-primary hover:bg-primary/20 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", scanning && "animate-spin")} />
            {scanning ? "扫描中..." : "重新扫描"}
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <SummaryCard
            icon={CircleCheck}
            label="已注入"
            value={injectedApps.length}
            color="text-primary"
            bgColor="bg-primary/10"
          />
          <SummaryCard
            icon={CircleDot}
            label="运行中"
            value={runningApps.length}
            color="text-amber-400"
            bgColor="bg-amber-400/10"
          />
          <SummaryCard
            icon={CircleAlert}
            label="注入异常"
            value={errorApps.length}
            color="text-destructive"
            bgColor="bg-destructive/10"
          />
          <SummaryCard
            icon={Smartphone}
            label="应用总数"
            value={apps.length}
            color="text-sky-400"
            bgColor="bg-sky-400/10"
          />
        </div>

        <button
          onClick={onNavigateApps}
          className="w-full flex items-center justify-between px-3 py-2.5 rounded-xl bg-muted/50 hover:bg-muted transition-colors"
        >
          <span className="text-xs font-medium text-foreground">查看应用列表详情</span>
          <ChevronRight className="w-4 h-4 text-muted-foreground" />
        </button>
      </section>

      {/* 活跃会话 */}
      {sessions.length > 0 && (
        <section className="rounded-2xl bg-card border border-border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" />
              活跃会话
            </h2>
            <button
              onClick={onNavigateMCP}
              className="text-xs text-primary font-medium hover:underline"
            >
              全部
            </button>
          </div>
          <div className="space-y-2">
            {sessions.slice(0, 3).map((session) => (
              <div key={session.id} className="flex items-center gap-3 p-2.5 rounded-xl bg-muted/40">
                <div className={cn(
                  "w-2 h-2 rounded-full",
                  session.state === "attached" ? "bg-primary scan-pulse" : "bg-muted-foreground"
                )} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-foreground truncate">{session.appName}</p>
                  <p className="text-[10px] text-muted-foreground font-mono truncate">
                    {session.packageName} · PID {session.pid || "—"}
                  </p>
                </div>
                <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                  <span>{session.hookCount} hooks</span>
                  <span>{session.messageCount} msgs</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 快捷操作 */}
      <section className="grid grid-cols-2 gap-3">
        <QuickAction
          icon={Smartphone}
          label="应用列表"
          desc="管理已注入应用"
          onClick={onNavigateApps}
        />
        <QuickAction
          icon={Server}
          label="MCP 服务"
          desc="会话与工具管理"
          onClick={onNavigateMCP}
        />
      </section>
    </div>
  );
}

function InfoChip({ icon: Icon, label, value }: { icon: typeof Cpu; label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 px-2 py-1.5 rounded-lg bg-muted/40">
      <div className="flex items-center gap-1 text-muted-foreground">
        <Icon className="w-3 h-3" />
        <span className="text-[10px]">{label}</span>
      </div>
      <span className="text-xs font-medium text-foreground truncate">{value}</span>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center px-2 py-2 rounded-xl bg-background/50">
      <p className="text-lg font-bold text-primary tabular-nums">{value}</p>
      <p className="text-[10px] text-muted-foreground">{label}</p>
    </div>
  );
}

function SummaryCard({
  icon: Icon,
  label,
  value,
  color,
  bgColor,
}: {
  icon: typeof CircleCheck;
  label: string;
  value: number;
  color: string;
  bgColor: string;
}) {
  return (
    <div className="flex items-center gap-2.5 p-2.5 rounded-xl bg-muted/30">
      <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", bgColor)}>
        <Icon className={cn("w-4 h-4", color)} />
      </div>
      <div>
        <p className={cn("text-lg font-bold tabular-nums", color)}>{value}</p>
        <p className="text-[10px] text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

function QuickAction({
  icon: Icon,
  label,
  desc,
  onClick,
}: {
  icon: typeof Smartphone;
  label: string;
  desc: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col gap-2 p-3 rounded-2xl bg-card border border-border hover:border-primary/30 transition-colors text-left"
    >
      <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center">
        <Icon className="w-4.5 h-4.5 text-primary" />
      </div>
      <div>
        <p className="text-xs font-semibold text-foreground">{label}</p>
        <p className="text-[10px] text-muted-foreground">{desc}</p>
      </div>
    </button>
  );
}
