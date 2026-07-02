"use client";

import { useState } from "react";
import {
  Smartphone,
  Shield,
  Bell,
  Palette,
  Info,
  Github,
  ChevronRight,
  Terminal,
  Wifi,
  RefreshCw,
  Cpu,
  Zap,
  Moon,
  Sun,
  Monitor,
  Volume2,
  Database,
  Bug,
  Server,
  Clock,
} from "lucide-react";
import type { DeviceInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SettingsScreenProps {
  device: DeviceInfo;
}

export function SettingsScreen({ device }: SettingsScreenProps) {
  const [autoScan, setAutoScan] = useState(true);
  const [scanInterval, setScanInterval] = useState("30");
  const [notifications, setNotifications] = useState(true);
  const [autoStartMCP, setAutoStartMCP] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [theme, setTheme] = useState("dark");

  return (
    <div className="px-4 pb-6 space-y-4 fade-in">
      {/* 设备信息 */}
      <section className="rounded-2xl bg-card border border-border overflow-hidden">
        <div className="p-4 border-b border-border/50">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">设备信息</h3>
        </div>
        <div className="divide-y divide-border/50">
          <InfoRow icon={Smartphone} label="设备名称" value={device.name} />
          <InfoRow icon={Cpu} label="架构" value={device.arch} mono />
          <InfoRow icon={Shield} label="Android 版本" value={device.androidVersion} />
          <InfoRow icon={Terminal} label="API Level" value={device.apiLevel.toString()} mono />
          <InfoRow
            icon={Zap}
            label="Root 状态"
            value={device.isRooted ? "已 Root" : "未 Root"}
            valueClass={device.isRooted ? "text-primary" : "text-muted-foreground"}
          />
          <InfoRow
            icon={Server}
            label="Frida Server"
            value={device.fridaServerRunning ? `运行中 v${device.fridaServerVersion}` : "未运行"}
            valueClass={device.fridaServerRunning ? "text-primary" : "text-destructive"}
          />
        </div>
      </section>

      {/* 扫描设置 */}
      <section className="rounded-2xl bg-card border border-border overflow-hidden">
        <div className="p-4 border-b border-border/50">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">注入检测</h3>
        </div>
        <div className="divide-y divide-border/50">
          <ToggleSettingRow
            icon={RefreshCw}
            label="自动扫描"
            desc="定期检测已注入应用"
            checked={autoScan}
            onChange={setAutoScan}
          />
          {autoScan && (
            <SelectSettingRow
              icon={Clock}
              label="扫描间隔"
              value={scanInterval}
              options={[
                { value: "10", label: "10 秒" },
                { value: "30", label: "30 秒" },
                { value: "60", label: "1 分钟" },
                { value: "300", label: "5 分钟" },
              ]}
              onChange={setScanInterval}
            />
          )}
          <ToggleSettingRow
            icon={Server}
            label="自动启动 MCP"
            desc="检测到运行中的注入应用时自动拉起 MCP 服务"
            checked={autoStartMCP}
            onChange={setAutoStartMCP}
          />
        </div>
      </section>

      {/* 通知设置 */}
      <section className="rounded-2xl bg-card border border-border overflow-hidden">
        <div className="p-4 border-b border-border/50">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">通知</h3>
        </div>
        <div className="divide-y divide-border/50">
          <ToggleSettingRow
            icon={Bell}
            label="注入状态通知"
            desc="应用注入或运行状态变化时通知"
            checked={notifications}
            onChange={setNotifications}
          />
        </div>
      </section>

      {/* 外观设置 */}
      <section className="rounded-2xl bg-card border border-border overflow-hidden">
        <div className="p-4 border-b border-border/50">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">外观</h3>
        </div>
        <div className="p-4 space-y-2">
          <div className="flex items-center gap-2 mb-2">
            <Palette className="w-4 h-4 text-primary" />
            <span className="text-sm text-foreground">主题模式</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {[
              { value: "dark", label: "深色", icon: Moon },
              { value: "light", label: "浅色", icon: Sun },
              { value: "system", label: "跟随系统", icon: Monitor },
            ].map((t) => (
              <button
                key={t.value}
                onClick={() => setTheme(t.value)}
                className={cn(
                  "flex flex-col items-center gap-1.5 py-3 rounded-xl border transition-colors",
                  theme === t.value
                    ? "bg-primary/10 border-primary/30 text-primary"
                    : "bg-muted/30 border-border text-muted-foreground"
                )}
              >
                <t.icon className="w-4 h-4" />
                <span className="text-xs">{t.label}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* 高级设置 */}
      <section className="rounded-2xl bg-card border border-border overflow-hidden">
        <div className="p-4 border-b border-border/50">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">高级</h3>
        </div>
        <div className="divide-y divide-border/50">
          <ToggleSettingRow
            icon={Bug}
            label="调试模式"
            desc="显示详细日志和调试信息"
            checked={debugMode}
            onChange={setDebugMode}
          />
          <ActionRow icon={Database} label="清除缓存" desc="清除应用扫描缓存" />
          <ActionRow icon={RefreshCw} label="重启 Frida Server" desc="重启设备上的 frida-server" />
        </div>
      </section>

      {/* 关于 */}
      <section className="rounded-2xl bg-card border border-border overflow-hidden">
        <div className="p-4 border-b border-border/50">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">关于</h3>
        </div>
        <div className="divide-y divide-border/50">
          <InfoRow icon={Info} label="版本" value="v2.0.0 (Mobile)" mono />
          <ActionRow icon={Github} label="项目仓库" desc="github.com/yfy227/fridamcp" />
          <ActionRow icon={Shield} label="开源协议" desc="MIT License" />
        </div>
      </section>

      <p className="text-center text-[10px] text-muted-foreground/60 pt-2">
        FridaMCP Mobile · 基于 Frida + MCP 协议
      </p>
    </div>
  );
}

function InfoRow({
  icon: Icon,
  label,
  value,
  valueClass,
  mono,
}: {
  icon: typeof Smartphone;
  label: string;
  value: string;
  valueClass?: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
      <span className="text-sm text-foreground flex-1">{label}</span>
      <span className={cn(
        "text-xs text-muted-foreground",
        mono && "font-mono",
        valueClass
      )}>
        {value}
      </span>
    </div>
  );
}

function ToggleSettingRow({
  icon: Icon,
  label,
  desc,
  checked,
  onChange,
}: {
  icon: typeof RefreshCw;
  label: string;
  desc: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-foreground">{label}</p>
        <p className="text-[10px] text-muted-foreground">{desc}</p>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={cn(
          "relative w-11 h-6 rounded-full transition-colors shrink-0",
          checked ? "bg-primary" : "bg-muted"
        )}
      >
        <span className={cn(
          "absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform",
          checked && "translate-x-5"
        )} />
      </button>
    </div>
  );
}

function SelectSettingRow({
  icon: Icon,
  label,
  value,
  options,
  onChange,
}: {
  icon: typeof Clock;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
      <span className="text-sm text-foreground flex-1">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="text-xs text-foreground bg-muted/40 border border-border rounded-lg px-2 py-1 outline-none"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </div>
  );
}

function ActionRow({
  icon: Icon,
  label,
  desc,
}: {
  icon: typeof Database;
  label: string;
  desc: string;
}) {
  return (
    <button className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors">
      <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
      <div className="flex-1 min-w-0 text-left">
        <p className="text-sm text-foreground">{label}</p>
        <p className="text-[10px] text-muted-foreground">{desc}</p>
      </div>
      <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
    </button>
  );
}
