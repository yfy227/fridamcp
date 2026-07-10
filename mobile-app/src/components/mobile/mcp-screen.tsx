"use client";

import { useState } from "react";
import {
  Server,
  Play,
  Square,
  Copy,
  Check,
  Link2,
  Activity,
  Users,
  Wrench,
  Clock,
  Terminal,
  Cpu,
  ChevronRight,
  CircleDot,
  Inbox,
} from "lucide-react";
import type { MCPServerStatus, MCPSession, MCPModule } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EmptyState } from "./empty-state";

interface MCPScreenProps {
  server: MCPServerStatus;
  sessions: MCPSession[];
  modules: MCPModule[];
  onToggleServer: () => void;
  onToggleModule: (name: string, enabled: boolean) => void;
}

export function MCPScreen({ server, sessions, modules, onToggleServer, onToggleModule }: MCPScreenProps) {
  const [copied, setCopied] = useState(false);
  const [showModules, setShowModules] = useState(true);

  const sseUrl = `http://${server.host === "0.0.0.0" ? "127.0.0.1" : server.host}:${server.port}/sse`;
  const httpUrl = `http://${server.host === "0.0.0.0" ? "127.0.0.1" : server.host}:${server.port}/mcp`;

  const handleCopy = (text: string) => {
    navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const uptime = server.startTime ? Date.now() - server.startTime : 0;

  return (
    <div className="px-4 pb-6 space-y-4 fade-in">
      {/* 服务器状态卡片 */}
      <section className="rounded-2xl bg-card border border-border overflow-hidden">
        <div className={cn(
          "p-4",
          server.running ? "bg-gradient-to-br from-primary/10 to-transparent" : ""
        )}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className={cn(
                "w-12 h-12 rounded-2xl flex items-center justify-center",
                server.running ? "bg-primary/15" : "bg-muted/40"
              )}>
                <Server className={cn("w-6 h-6", server.running ? "text-primary" : "text-muted-foreground")} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-foreground">MCP Server</h3>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className={cn(
                    "status-dot",
                    server.running ? "bg-primary scan-pulse" : "bg-muted-foreground"
                  )} />
                  <span className="text-xs text-muted-foreground">
                    {server.running ? "运行中" : "已停止"}
                  </span>
                </div>
              </div>
            </div>
            <button
              onClick={onToggleServer}
              className={cn(
                "px-4 py-2 rounded-xl text-xs font-semibold transition-colors",
                server.running
                  ? "bg-destructive/15 text-destructive hover:bg-destructive/25"
                  : "bg-primary text-primary-foreground hover:bg-primary/90"
              )}
            >
              {server.running ? (
                <span className="flex items-center gap-1.5">
                  <Square className="w-3.5 h-3.5" /> 停止
                </span>
              ) : (
                <span className="flex items-center gap-1.5">
                  <Play className="w-3.5 h-3.5" /> 启动
                </span>
              )}
            </button>
          </div>

          {/* 统计数据 */}
          <div className="grid grid-cols-4 gap-2">
            <StatBox icon={Clock} label="运行时长" value={formatUptime(uptime)} />
            <StatBox icon={Users} label="客户端" value={server.connectedClients.toString()} />
            <StatBox icon={Activity} label="会话" value={server.activeSessions.toString()} />
            <StatBox icon={Wrench} label="工具数" value={server.totalTools.toString()} />
          </div>
        </div>
      </section>

      {/* 连接地址 */}
      <section className="rounded-2xl bg-card border border-border p-4 space-y-3">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Link2 className="w-4 h-4 text-primary" />
          连接地址
        </h3>

        <div className="space-y-2">
          <ConnectionRow
            label="SSE 端点"
            url={sseUrl}
            copied={copied}
            onCopy={() => handleCopy(sseUrl)}
          />
          <ConnectionRow
            label="HTTP 端点"
            url={httpUrl}
            copied={copied}
            onCopy={() => handleCopy(httpUrl)}
          />
        </div>

        <div className="flex items-center gap-2 pt-2 border-t border-border/50">
          <Terminal className="w-3.5 h-3.5 text-muted-foreground" />
          <code className="flex-1 text-[10px] text-muted-foreground font-mono truncate">
            python -m fridamcp --transport sse --port {server.port}
          </code>
        </div>
      </section>

      {/* 活跃会话 */}
      <section className="rounded-2xl bg-card border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            活跃会话
            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-primary/15 text-primary">
              {sessions.length}
            </span>
          </h3>
        </div>

        {sessions.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title="暂无活跃会话"
            desc="启动已注入应用后将自动创建会话，或手动拉起 MCP 服务"
          />
        ) : (
          <div className="space-y-2">
            {sessions.map((session) => (
              <SessionCard key={session.id} session={session} />
            ))}
          </div>
        )}
      </section>

      {/* MCP 模块 */}
      <section className="rounded-2xl bg-card border border-border overflow-hidden">
        <button
          onClick={() => setShowModules(!showModules)}
          className="w-full flex items-center justify-between p-4"
        >
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Cpu className="w-4 h-4 text-primary" />
            MCP 模块 ({modules.length})
          </h3>
          <ChevronRight className={cn("w-4 h-4 text-muted-foreground transition-transform", showModules && "rotate-90")} />
        </button>

        {showModules && (
          <div className="px-4 pb-4 space-y-1.5 fade-in">
            {modules.map((mod) => (
              <ModuleRow key={mod.name} module={mod} onToggle={onToggleModule} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ModuleRow({ module: mod, onToggle }: { module: MCPModule; onToggle: (name: string, enabled: boolean) => void }) {
  return (
    <div className="flex items-center gap-3 p-2.5 rounded-xl bg-muted/30">
      <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-base shrink-0">
        {mod.icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-xs font-medium text-foreground">{mod.displayName}</p>
          <span className="text-[9px] text-muted-foreground font-mono">{mod.toolCount} tools</span>
        </div>
        <p className="text-[10px] text-muted-foreground truncate">{mod.description}</p>
      </div>
      {/* 开关 */}
      <button
        onClick={() => onToggle(mod.name, !mod.enabled)}
        className={cn(
          "relative w-9 h-5 rounded-full transition-colors shrink-0",
          mod.enabled ? "bg-primary" : "bg-muted-foreground/30"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform",
            mod.enabled ? "translate-x-4" : "translate-x-0.5"
          )}
        />
      </button>
    </div>
  );
}

function StatBox({ icon: Icon, label, value }: { icon: typeof Clock; label: string; value: string }) {
  return (
    <div className="flex flex-col items-center gap-1 p-2 rounded-xl bg-muted/30">
      <Icon className="w-3.5 h-3.5 text-muted-foreground" />
      <span className="text-xs font-bold text-foreground tabular-nums">{value}</span>
      <span className="text-[9px] text-muted-foreground">{label}</span>
    </div>
  );
}

function ConnectionRow({
  label,
  url,
  copied,
  onCopy,
}: {
  label: string;
  url: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="flex items-center gap-2 p-2.5 rounded-xl bg-muted/30">
      <div className="flex-1 min-w-0">
        <p className="text-[10px] text-muted-foreground mb-0.5">{label}</p>
        <p className="text-xs font-mono text-foreground truncate">{url}</p>
      </div>
      <button
        onClick={onCopy}
        className="p-2 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors shrink-0"
      >
        {copied ? <Check className="w-4 h-4 text-primary" /> : <Copy className="w-4 h-4" />}
      </button>
    </div>
  );
}

function SessionCard({ session }: { session: MCPSession }) {
  const stateConfig = {
    attached: { label: "已附加", color: "text-primary", bg: "bg-primary/10" },
    created: { label: "已创建", color: "text-amber-400", bg: "bg-amber-400/10" },
    detached: { label: "已分离", color: "text-muted-foreground", bg: "bg-muted/30" },
    error: { label: "错误", color: "text-destructive", bg: "bg-destructive/10" },
  }[session.state];

  return (
    <div className="p-3 rounded-xl bg-muted/30 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn("px-1.5 py-0.5 rounded text-[9px] font-medium", stateConfig.bg, stateConfig.color)}>
            {stateConfig.label}
          </span>
          <span className="text-xs font-medium text-foreground truncate">{session.appName}</span>
        </div>
        <span className="text-[10px] text-muted-foreground font-mono shrink-0">PID {session.pid}</span>
      </div>
      <p className="text-[10px] text-muted-foreground font-mono truncate">{session.packageName}</p>
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <Wrench className="w-3 h-3" />
          {session.hookCount} hooks
        </span>
        <span className="flex items-center gap-1">
          <Activity className="w-3 h-3" />
          {session.messageCount} msgs
        </span>
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {formatUptime(Date.now() - session.createdAt)}
        </span>
      </div>
    </div>
  );
}

function formatUptime(ms: number): string {
  if (ms < 60000) return `${Math.floor(ms / 1000)}s`;
  if (ms < 3600000) return `${Math.floor(ms / 60000)}m`;
  return `${Math.floor(ms / 3600000)}h ${Math.floor((ms % 3600000) / 60000)}m`;
}
