"use client";

import { useState, useCallback, useMemo } from "react";
import { StatusBar } from "@/components/mobile/status-bar";
import { BottomNav } from "@/components/mobile/bottom-nav";
import { DashboardScreen } from "@/components/mobile/dashboard-screen";
import { AppsScreen } from "@/components/mobile/apps-screen";
import { InjectScreen } from "@/components/mobile/inject-screen";
import { MCPScreen } from "@/components/mobile/mcp-screen";
import { SettingsScreen } from "@/components/mobile/settings-screen";
import { AppDetailSheet } from "@/components/mobile/app-detail-sheet";
import { ToastContainer, useToast } from "@/components/mobile/toast";
import {
  mockDevice,
  mockMCPServer,
  mockApps,
  mockModules,
  mockInjectionTasks,
} from "@/lib/mock-data";
import type { TabId, AppInfo, InjectionTask, MCPServerStatus, MCPSession } from "@/lib/types";

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");
  const [apps, setApps] = useState<AppInfo[]>(mockApps);
  const [scanning, setScanning] = useState(false);
  const [selectedApp, setSelectedApp] = useState<AppInfo | null>(null);
  const [mcpServer, setMcpServer] = useState<MCPServerStatus>(mockMCPServer);
  const [tasks, setTasks] = useState<InjectionTask[]>(mockInjectionTasks);
  const { toasts, showToast, dismiss } = useToast();

  const injectedCount = apps.filter(
    (a) => a.injectionStatus === "injected" || a.injectionStatus === "running"
  ).length;

  // 动态生成会话列表：基于正在运行且 MCP 在线的应用
  const dynamicSessions: MCPSession[] = useMemo(() => {
    return apps
      .filter((a) => a.injectionStatus === "running" && a.mcpStatus === "online")
      .map((a, i) => ({
        id: `sess-${a.id}`,
        pid: a.pid || 0,
        appName: a.appName,
        packageName: a.packageName,
        state: "attached" as const,
        createdAt: a.injectedAt || Date.now(),
        scriptCount: 1 + i,
        hookCount: Math.floor(Math.random() * 8) + 1,
        messageCount: Math.floor(Math.random() * 120),
      }));
  }, [apps]);

  // 扫描已注入应用
  const handleScan = useCallback(() => {
    setScanning(true);
    setTimeout(() => {
      setScanning(false);
      // 更新最后扫描时间
      setApps((prev) =>
        prev.map((app) => ({
          ...app,
          lastScanTime: Date.now(),
        }))
      );
      showToast(`扫描完成，检测到 ${injectedCount} 个已注入应用`, "success");
    }, 2000);
  }, [injectedCount, showToast]);

  // 启动应用
  const handleLaunchApp = useCallback((app: AppInfo) => {
    if (app.injectionStatus === "running") {
      showToast(`${app.appName} 已在运行中 (PID: ${app.pid})`, "info");
      return;
    }
    // 模拟启动应用
    setApps((prev) =>
      prev.map((a) =>
        a.id === app.id
          ? {
              ...a,
              injectionStatus: "running",
              pid: Math.floor(10000 + Math.random() * 30000),
              mcpStatus: "online",
              lastScanTime: Date.now(),
              detectionMethod: "runtime",
            }
          : a
      )
    );
    showToast(`正在启动 ${app.appName}...`, "success");
  }, [showToast]);

  // 拉起/停止 MCP 服务
  const handleToggleMCP = useCallback((app: AppInfo) => {
    setApps((prev) =>
      prev.map((a) => {
        if (a.id !== app.id) return a;
        const newStatus = a.mcpStatus === "online" ? "offline" : "online";
        showToast(
          newStatus === "online"
            ? `${a.appName} MCP 服务已启动 (端口 ${a.mcpPort || 27042})`
            : `${a.appName} MCP 服务已停止`,
          newStatus === "online" ? "success" : "info"
        );
        return { ...a, mcpStatus: newStatus };
      })
    );
  }, [showToast]);

  // 重新检测单个应用
  const handleRescan = useCallback((app: AppInfo) => {
    showToast(`正在重新检测 ${app.appName}...`, "info");
    setTimeout(() => {
      setApps((prev) =>
        prev.map((a) =>
          a.id === app.id ? { ...a, lastScanTime: Date.now() } : a
        )
      );
      showToast(`${app.appName} 检测完成`, "success");
    }, 1500);
  }, [showToast]);

  // 移除注入
  const handleRemoveInjection = useCallback((app: AppInfo) => {
    setApps((prev) =>
      prev.map((a) =>
        a.id === app.id
          ? {
              ...a,
              injectionStatus: "not_injected",
              gadgetVersion: undefined,
              gadgetArch: undefined,
              injectedAt: undefined,
              pid: undefined,
              mcpPort: undefined,
              mcpStatus: undefined,
              detectionMethod: "none",
              lastScanTime: Date.now(),
            }
          : a
      )
    );
    setSelectedApp(null);
    showToast(`${app.appName} 注入已移除`, "success");
  }, [showToast]);

  // 切换 MCP 服务器
  const handleToggleMCPServer = useCallback(() => {
    setMcpServer((prev) => {
      const running = !prev.running;
      showToast(
        running ? "MCP 服务器已启动" : "MCP 服务器已停止",
        running ? "success" : "info"
      );
      return {
        ...prev,
        running,
        startTime: running ? Date.now() : undefined,
        activeSessions: running ? prev.activeSessions : 0,
      };
    });
  }, [showToast]);

  // 创建注入任务
  const handleInject = useCallback(
    (task: Omit<InjectionTask, "id" | "status" | "progress" | "createdAt">) => {
      const newTask: InjectionTask = {
        ...task,
        id: `task-${Date.now()}`,
        status: "injecting",
        progress: 0,
        createdAt: Date.now(),
      };
      setTasks((prev) => [newTask, ...prev]);

      // 模拟注入进度
      let progress = 0;
      const interval = setInterval(() => {
        progress += 15;
        setTasks((prev) =>
          prev.map((t) =>
            t.id === newTask.id
              ? {
                  ...t,
                  progress: Math.min(progress, 100),
                  status: progress >= 70 ? "signing" : "injecting",
                }
              : t
          )
        );
        if (progress >= 100) {
          clearInterval(interval);
          setTasks((prev) =>
            prev.map((t) =>
              t.id === newTask.id
                ? {
                    ...t,
                    status: "done",
                    progress: 100,
                    outputApk: t.apkPath.replace(".apk", "_injected.apk"),
                  }
                : t
            )
          );
          showToast(`${task.appName} 注入完成`, "success");

          // 模拟自动安装并添加到应用列表
          setTimeout(() => {
            const newApp: AppInfo = {
              id: `app-${Date.now()}`,
              packageName: task.packageName,
              appName: task.appName,
              version: "1.0.0",
              versionCode: 10000,
              iconColor: "#6366F1",
              iconText: task.appName.charAt(0).toUpperCase(),
              isSystem: false,
              installTime: Date.now(),
              updateTime: Date.now(),
              injectionStatus: "injected",
              gadgetVersion: "16.5.1",
              gadgetArch: task.arch,
              injectedAt: Date.now(),
              mcpStatus: "offline",
              lastScanTime: Date.now(),
              detectionMethod: "static",
            };
            setApps((prev) => [newApp, ...prev]);
            showToast(`${task.appName} 已安装并检测到注入`, "success");
          }, 2000);
        }
      }, 500);
    },
    [showToast]
  );

  return (
    <div className="min-h-screen bg-background">
      <div className="mobile-container flex flex-col">
        {/* 状态栏 */}
        <StatusBar />

        {/* 顶部标题栏 */}
        <header className="sticky top-0 z-20 px-4 py-3 bg-background/80 backdrop-blur-md border-b border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-primary/15 flex items-center justify-center">
                <span className="text-primary font-bold text-sm">F</span>
              </div>
              <div>
                <h1 className="text-base font-bold text-foreground leading-tight">FridaMCP</h1>
                <p className="text-[10px] text-muted-foreground leading-tight">AI 驱动的动态分析</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10">
                <span className="w-1.5 h-1.5 rounded-full bg-primary scan-pulse" />
                <span className="text-[10px] font-medium text-primary">在线</span>
              </div>
            </div>
          </div>
        </header>

        {/* 主内容区 */}
        <main className="flex-1 overflow-y-auto pt-3">
          {activeTab === "dashboard" && (
            <DashboardScreen
              device={mockDevice}
              mcpServer={mcpServer}
              apps={apps}
              sessions={dynamicSessions}
              onRefresh={handleScan}
              onToggleMCPServer={handleToggleMCPServer}
              onNavigateApps={() => setActiveTab("apps")}
              onNavigateMCP={() => setActiveTab("mcp")}
            />
          )}
          {activeTab === "apps" && (
            <AppsScreen
              apps={apps}
              scanning={scanning}
              onScan={handleScan}
              onSelectApp={setSelectedApp}
              onLaunchApp={handleLaunchApp}
              onToggleMCP={handleToggleMCP}
            />
          )}
          {activeTab === "inject" && (
            <InjectScreen tasks={tasks} onInject={handleInject} />
          )}
          {activeTab === "mcp" && (
            <MCPScreen
              server={mcpServer}
              sessions={dynamicSessions}
              modules={mockModules}
              onToggleServer={handleToggleMCPServer}
            />
          )}
          {activeTab === "settings" && <SettingsScreen device={mockDevice} />}
        </main>

        {/* 底部导航 */}
        <BottomNav
          activeTab={activeTab}
          onTabChange={setActiveTab}
          injectedCount={injectedCount}
        />

        {/* 应用详情面板 */}
        <AppDetailSheet
          app={selectedApp}
          onClose={() => setSelectedApp(null)}
          onLaunch={handleLaunchApp}
          onToggleMCP={handleToggleMCP}
          onRescan={handleRescan}
          onRemoveInjection={handleRemoveInjection}
        />

        {/* Toast 通知 */}
        <ToastContainer toasts={toasts} onDismiss={dismiss} />
      </div>
    </div>
  );
}
