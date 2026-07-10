"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  appFromInjectionTask,
  appService,
  buildSessions,
} from "@/lib/app-service";
import type {
  AppInfo,
  DeviceInfo,
  InjectionOptions,
  InjectionTask,
  MCPModule,
  MCPServerStatus,
  TabId,
} from "@/lib/types";

function updateApp(apps: AppInfo[], updated: AppInfo) {
  return apps.map((app) => (app.id === updated.id ? updated : app));
}

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [apps, setApps] = useState<AppInfo[]>([]);
  const [modules, setModules] = useState<MCPModule[]>([]);
  const [scanning, setScanning] = useState(false);
  const [selectedApp, setSelectedApp] = useState<AppInfo | null>(null);
  const [mcpServer, setMcpServer] = useState<MCPServerStatus | null>(null);
  const [tasks, setTasks] = useState<InjectionTask[]>([]);
  const [busyAppId, setBusyAppId] = useState<string | null>(null);
  const { toasts, showToast, dismiss } = useToast();

  useEffect(() => {
    let alive = true;
    appService
      .loadSnapshot()
      .then((snapshot) => {
        if (!alive) return;
        setDevice(snapshot.device);
        setApps(snapshot.apps);
        setMcpServer(snapshot.server);
        setTasks(snapshot.tasks);
        setModules(snapshot.modules);
      })
      .catch((error) => showToast(error instanceof Error ? error.message : "初始化失败", "error"));
    return () => {
      alive = false;
    };
  }, [showToast]);

  const sessions = useMemo(() => buildSessions(apps), [apps]);

  useEffect(() => {
    if (!mcpServer) return;
    setMcpServer((prev) =>
      prev && prev.running ? { ...prev, activeSessions: sessions.length } : prev
    );
  }, [sessions.length]);

  useEffect(() => {
    if (selectedApp) {
      const latest = apps.find((app) => app.id === selectedApp.id) ?? null;
      setSelectedApp(latest);
    }
  }, [apps, selectedApp]);

  const injectedCount = apps.filter(
    (a) => a.injectionStatus === "injected" || a.injectionStatus === "running"
  ).length;

  const handleScan = useCallback(async () => {
    if (scanning) return;
    setScanning(true);
    try {
      const scanned = await appService.scanApps(apps);
      setApps(scanned);
      showToast(`扫描完成，检测到 ${scanned.filter((a) => a.injectionStatus === "injected" || a.injectionStatus === "running").length} 个已注入应用`, "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "扫描失败", "error");
    } finally {
      setScanning(false);
    }
  }, [apps, scanning, showToast]);

  const handleLaunchApp = useCallback(async (app: AppInfo) => {
    if (busyAppId) return;
    setBusyAppId(app.id);
    try {
      const updated =
        app.injectionStatus === "running"
          ? await appService.stopApp(app)
          : await appService.launchApp(app);
      setApps((prev) => updateApp(prev, updated));
      showToast(
        updated.injectionStatus === "running"
          ? `${updated.appName} 已启动 (PID: ${updated.pid})`
          : `${updated.appName} 已停止`,
        "success"
      );
    } catch (error) {
      showToast(error instanceof Error ? error.message : "应用操作失败", "error");
    } finally {
      setBusyAppId(null);
    }
  }, [busyAppId, showToast]);

  const handleToggleMCP = useCallback(async (app: AppInfo) => {
    if (busyAppId) return;
    setBusyAppId(app.id);
    try {
      const optimistic: AppInfo = app.mcpStatus === "online" ? app : { ...app, mcpStatus: "starting" };
      setApps((prev) => updateApp(prev, optimistic));
      const updated = await appService.toggleAppMcp(optimistic);
      setApps((prev) => updateApp(prev, updated));
      showToast(
        updated.mcpStatus === "online"
          ? `${updated.appName} MCP 服务已在线 (:${updated.mcpPort})`
          : `${updated.appName} MCP 服务已停止`,
        updated.mcpStatus === "online" ? "success" : "info"
      );
    } catch (error) {
      setApps((prev) => updateApp(prev, app));
      showToast(error instanceof Error ? error.message : "MCP 操作失败", "error");
    } finally {
      setBusyAppId(null);
    }
  }, [busyAppId, showToast]);

  const handleRescan = useCallback(async (app: AppInfo) => {
    setBusyAppId(app.id);
    try {
      const updated = await appService.rescanApp(app);
      setApps((prev) => updateApp(prev, updated));
      showToast(`${updated.appName} 检测完成`, updated.injectionStatus === "error" ? "warning" : "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "检测失败", "error");
    } finally {
      setBusyAppId(null);
    }
  }, [showToast]);

  const handleRemoveInjection = useCallback(async (app: AppInfo) => {
    setBusyAppId(app.id);
    try {
      const updated = await appService.removeInjection(app);
      setApps((prev) => updateApp(prev, updated));
      setSelectedApp(null);
      showToast(`${app.appName} 注入已移除`, "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "移除失败", "error");
    } finally {
      setBusyAppId(null);
    }
  }, [showToast]);

  const handleToggleMCPServer = useCallback(async () => {
    if (!mcpServer) return;
    try {
      const updated = await appService.toggleServer(mcpServer, sessions);
      setMcpServer(updated);
      showToast(updated.running ? "MCP 服务器已启动" : "MCP 服务器已停止", updated.running ? "success" : "info");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "服务器操作失败", "error");
    }
  }, [mcpServer, sessions, showToast]);

  const handleInject = useCallback(async (input: InjectionOptions) => {
    try {
      const task = await appService.createInjectionTask(input);
      setTasks((prev) => [task, ...prev]);
      const done = await appService.runInjectionTask(task, (progressTask) => {
        setTasks((prev) => prev.map((item) => (item.id === progressTask.id ? progressTask : item)));
      });
      setTasks((prev) => prev.map((item) => (item.id === done.id ? done : item)));
      showToast(`${done.appName} 注入完成`, "success");
      if (done.autoScan !== false) {
        const newApp = appFromInjectionTask(done);
        setApps((prev) => [newApp, ...prev.filter((app) => app.packageName !== newApp.packageName)]);
        showToast(`${done.appName} 已加入应用列表并完成检测`, "success");
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : "注入失败", "error");
    }
  }, [showToast]);

  const handleToggleModule = useCallback(async (name: string, enabled: boolean) => {
    try {
      const updated = await appService.setModuleEnabled(modules, name, enabled);
      setModules(updated);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "模块设置失败", "error");
    }
  }, [modules, showToast]);

  if (!device || !mcpServer) {
    return <div className="min-h-screen bg-background text-foreground flex items-center justify-center text-sm">正在加载 FridaMCP...</div>;
  }

  const online = device.status === "connected" && mcpServer.running;

  return (
    <div className="min-h-screen bg-background">
      <div className="mobile-container flex flex-col">
        <StatusBar />
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
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10">
              <span className={`w-1.5 h-1.5 rounded-full ${online ? "bg-primary scan-pulse" : "bg-muted-foreground"}`} />
              <span className="text-[10px] font-medium text-primary">{online ? "在线" : "待连接"}</span>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto pt-3">
          {activeTab === "dashboard" && (
            <DashboardScreen device={device} mcpServer={mcpServer} apps={apps} sessions={sessions} scanning={scanning} onRefresh={handleScan} onToggleMCPServer={handleToggleMCPServer} onNavigateApps={() => setActiveTab("apps")} onNavigateMCP={() => setActiveTab("mcp")} />
          )}
          {activeTab === "apps" && (
            <AppsScreen apps={apps} scanning={scanning} busyAppId={busyAppId} onScan={handleScan} onSelectApp={setSelectedApp} onLaunchApp={handleLaunchApp} onToggleMCP={handleToggleMCP} />
          )}
          {activeTab === "inject" && <InjectScreen tasks={tasks} onInject={handleInject} />}
          {activeTab === "mcp" && (
            <MCPScreen server={mcpServer} sessions={sessions} modules={modules} onToggleServer={handleToggleMCPServer} onToggleModule={handleToggleModule} />
          )}
          {activeTab === "settings" && <SettingsScreen device={device} />}
        </main>

        <BottomNav activeTab={activeTab} onTabChange={setActiveTab} injectedCount={injectedCount} />
        <AppDetailSheet app={selectedApp} busy={Boolean(busyAppId)} onClose={() => setSelectedApp(null)} onLaunch={handleLaunchApp} onToggleMCP={handleToggleMCP} onRescan={handleRescan} onRemoveInjection={handleRemoveInjection} />
        <ToastContainer toasts={toasts} onDismiss={dismiss} />
      </div>
    </div>
  );
}
