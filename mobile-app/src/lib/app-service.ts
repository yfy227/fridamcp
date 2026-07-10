import {
  mockApps,
  mockDevice,
  mockInjectionTasks,
  mockMCPServer,
  mockModules,
} from "./mock-data";
import type {
  AppInfo,
  DeviceInfo,
  InjectionOptions,
  InjectionTask,
  MCPModule,
  MCPServerStatus,
  MCPSession,
} from "./types";
import { basename, isAndroidPackageName, sleep, stableNumber } from "./utils";

export interface AppSnapshot {
  device: DeviceInfo;
  server: MCPServerStatus;
  apps: AppInfo[];
  tasks: InjectionTask[];
  modules: MCPModule[];
}

export interface FridaMCPAppService {
  loadSnapshot(): Promise<AppSnapshot>;
  scanApps(apps: AppInfo[]): Promise<AppInfo[]>;
  rescanApp(app: AppInfo): Promise<AppInfo>;
  launchApp(app: AppInfo): Promise<AppInfo>;
  stopApp(app: AppInfo): Promise<AppInfo>;
  toggleAppMcp(app: AppInfo): Promise<AppInfo>;
  toggleServer(server: MCPServerStatus, sessions: MCPSession[]): Promise<MCPServerStatus>;
  createInjectionTask(input: InjectionOptions): Promise<InjectionTask>;
  runInjectionTask(task: InjectionTask, onProgress: (task: InjectionTask) => void): Promise<InjectionTask>;
  removeInjection(app: AppInfo): Promise<AppInfo>;
  setModuleEnabled(modules: MCPModule[], name: string, enabled: boolean): Promise<MCPModule[]>;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

function derivePackageFromApk(apkPath: string): string {
  const file = basename(apkPath).replace(/\.apk$/i, "");
  const cleaned = file
    .toLowerCase()
    .replace(/^com[._-]/, "com.")
    .replace(/[^a-z0-9._-]+/g, ".")
    .replace(/[_-]+/g, ".")
    .replace(/\.+/g, ".")
    .replace(/^\.|\.$/g, "");
  const candidate = cleaned.includes(".") ? cleaned : `local.${cleaned || "app"}`;
  return isAndroidPackageName(candidate) ? candidate : `local.app.${Date.now()}`;
}

function deriveAppName(apkPath: string): string {
  const name = basename(apkPath).replace(/\.apk$/i, "").replace(/[._-]+/g, " ").trim();
  return name ? name.replace(/\w/g, (m) => m.toUpperCase()) : "Unknown APK";
}

function validateInjectionInput(input: InjectionOptions) {
  if (!input.apkPath.trim()) throw new Error("请选择 APK 文件");
  if (!/\.apk$/i.test(input.apkPath.trim())) throw new Error("只能选择 .apk 文件");
  if (!input.arch) throw new Error("请选择目标架构");
  if (input.packageName && !isAndroidPackageName(input.packageName)) {
    throw new Error(`包名格式不合法: ${input.packageName}`);
  }
}

class LocalSimulationService implements FridaMCPAppService {
  async loadSnapshot(): Promise<AppSnapshot> {
    await sleep(150);
    return {
      device: clone(mockDevice),
      server: clone(mockMCPServer),
      apps: clone(mockApps),
      tasks: clone(mockInjectionTasks),
      modules: clone(mockModules),
    };
  }

  async scanApps(apps: AppInfo[]): Promise<AppInfo[]> {
    await sleep(900);
    return apps.map((app) => this.detectApp(app));
  }

  async rescanApp(app: AppInfo): Promise<AppInfo> {
    await sleep(500);
    return this.detectApp(app);
  }

  async launchApp(app: AppInfo): Promise<AppInfo> {
    if (app.injectionStatus === "not_injected") throw new Error("未注入应用不能直接启动 Gadget 会话");
    if (app.injectionStatus === "error") throw new Error("注入异常，请先重新注入或移除注入");
    await sleep(650);
    return {
      ...app,
      injectionStatus: "running",
      pid: app.pid ?? stableNumber(app.packageName, 10000, 45000),
      detectionMethod: "runtime",
      lastScanTime: Date.now(),
    };
  }

  async stopApp(app: AppInfo): Promise<AppInfo> {
    await sleep(350);
    return {
      ...app,
      injectionStatus: app.gadgetVersion ? "injected" : "not_injected",
      pid: undefined,
      mcpStatus: app.gadgetVersion ? "offline" : undefined,
      detectionMethod: app.gadgetVersion ? "static" : "none",
      lastScanTime: Date.now(),
    };
  }

  async toggleAppMcp(app: AppInfo): Promise<AppInfo> {
    if (app.injectionStatus !== "running") {
      throw new Error("请先启动已注入应用，Gadget 加载后才能拉起 MCP");
    }
    if (app.mcpStatus === "online") {
      await sleep(300);
      return { ...app, mcpStatus: "offline" };
    }
    await sleep(700);
    return {
      ...app,
      mcpStatus: "online",
      mcpPort: app.mcpPort ?? 27042,
      lastScanTime: Date.now(),
    };
  }

  async toggleServer(server: MCPServerStatus, sessions: MCPSession[]): Promise<MCPServerStatus> {
    await sleep(450);
    const running = !server.running;
    return {
      ...server,
      running,
      startTime: running ? Date.now() : undefined,
      activeSessions: running ? sessions.length : 0,
      connectedClients: running ? Math.max(server.connectedClients, 1) : 0,
    };
  }

  async createInjectionTask(input: InjectionOptions): Promise<InjectionTask> {
    validateInjectionInput(input);
    const apkPath = input.apkPath.trim();
    const packageName = input.packageName?.trim() || derivePackageFromApk(apkPath);
    const appName = input.appName?.trim() || deriveAppName(apkPath);
    return {
      id: `task-${Date.now()}`,
      apkPath,
      appName,
      packageName,
      status: "pending",
      progress: 0,
      arch: input.arch,
      useApktool: input.useApktool,
      autoInstall: input.autoInstall,
      autoScan: input.autoScan,
      createdAt: Date.now(),
    };
  }

  async runInjectionTask(task: InjectionTask, onProgress: (task: InjectionTask) => void): Promise<InjectionTask> {
    const steps: Array<Pick<InjectionTask, "status" | "progress">> = [
      { status: "analyzing", progress: 12 },
      { status: "injecting", progress: 38 },
      { status: "injecting", progress: 62 },
      { status: "signing", progress: 84 },
      { status: task.autoInstall ? "installing" : "done", progress: task.autoInstall ? 94 : 100 },
    ];
    let current: InjectionTask = { ...task, status: "analyzing", progress: 5 };

    onProgress(current);
    for (const step of steps) {
      await sleep(450);
      current = { ...current, ...step };
      onProgress(current);
    }
    await sleep(350);
    const done: InjectionTask = {
      ...current,
      status: "done",
      progress: 100,
      outputApk: task.apkPath.replace(/\.apk$/i, "_fridamcp.apk"),
    };
    onProgress(done);
    return done;
  }

  async removeInjection(app: AppInfo): Promise<AppInfo> {
    await sleep(450);
    return {
      ...app,
      injectionStatus: "not_injected",
      gadgetVersion: undefined,
      gadgetArch: undefined,
      injectedAt: undefined,
      pid: undefined,
      mcpPort: undefined,
      mcpStatus: undefined,
      detectionMethod: "none",
      lastScanTime: Date.now(),
    };
  }

  async setModuleEnabled(modules: MCPModule[], name: string, enabled: boolean): Promise<MCPModule[]> {
    await sleep(120);
    return modules.map((m) => (m.name === name ? { ...m, enabled } : m));
  }

  private detectApp(app: AppInfo): AppInfo {
    if (app.injectionStatus === "running" && app.pid) {
      return { ...app, detectionMethod: "runtime", lastScanTime: Date.now() };
    }
    if (app.gadgetVersion) {
      const archMismatch = app.gadgetArch && app.gadgetArch !== mockDevice.arch;
      return {
        ...app,
        injectionStatus: archMismatch ? "error" : "injected",
        detectionMethod: "static",
        lastScanTime: Date.now(),
      };
    }
    return { ...app, injectionStatus: "not_injected", detectionMethod: "none", lastScanTime: Date.now() };
  }
}

export const appService: FridaMCPAppService = new LocalSimulationService();

export function buildSessions(apps: AppInfo[]): MCPSession[] {
  return apps
    .filter((a) => a.injectionStatus === "running" && a.mcpStatus === "online")
    .map((a) => ({
      id: `sess-${a.id}`,
      pid: a.pid ?? 0,
      appName: a.appName,
      packageName: a.packageName,
      state: "attached" as const,
      createdAt: a.injectedAt ?? a.lastScanTime ?? Date.now(),
      scriptCount: stableNumber(`${a.id}:scripts`, 1, 4),
      hookCount: stableNumber(`${a.id}:hooks`, 1, 8),
      messageCount: stableNumber(`${a.id}:messages`, 10, 160),
    }));
}

export function appFromInjectionTask(task: InjectionTask): AppInfo {
  return {
    id: `app-${task.id}`,
    packageName: task.packageName,
    appName: task.appName,
    version: "1.0.0",
    versionCode: 1,
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
}
