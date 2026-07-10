// FridaMCP Mobile App - Type Definitions

/** Injection status of an app */
export type InjectionStatus =
  | "injected" // frida-gadget 已注入
  | "not_injected" // 未注入
  | "running" // 已注入且正在运行（gadget 已激活）
  | "error"; // 注入异常

/** MCP service status */
export type MCPServiceStatus =
  | "online" // MCP 服务在线
  | "offline" // MCP 服务离线
  | "starting" // 正在启动
  | "error"; // 服务异常

/** Device connection status */
export type DeviceStatus =
  | "connected" // 已连接
  | "disconnected" // 未连接
  | "unauthorized" // 未授权
  | "offline"; // 离线

/** App info - represents an installed Android application */
export interface AppInfo {
  id: string;
  packageName: string;
  appName: string;
  version: string;
  versionCode: number;
  iconColor: string; // 用于生成图标占位的颜色
  iconText: string; // 图标占位文字
  isSystem: boolean;
  installTime: number;
  updateTime: number;
  // 注入相关信息
  injectionStatus: InjectionStatus;
  gadgetVersion?: string; // frida-gadget 版本
  gadgetArch?: string; // 注入的架构
  injectedAt?: number; // 注入时间
  // 运行时信息
  pid?: number; // 进程 PID（运行中时）
  mcpPort?: number; // MCP 服务端口
  mcpStatus?: MCPServiceStatus;
  // 检测信息
  lastScanTime?: number;
  detectionMethod?: "static" | "runtime" | "process" | "none";
}

/** Frida device info */
export interface DeviceInfo {
  id: string;
  name: string;
  type: "usb" | "remote" | "local";
  status: DeviceStatus;
  androidVersion: string;
  apiLevel: number;
  arch: string;
  isRooted: boolean;
  fridaServerVersion?: string;
  fridaServerRunning: boolean;
}

/** MCP server status */
export interface MCPServerStatus {
  running: boolean;
  host: string;
  port: number;
  transport: "stdio" | "sse" | "http";
  startTime?: number;
  activeSessions: number;
  totalTools: number;
  connectedClients: number;
}

/** MCP session info */
export interface MCPSession {
  id: string;
  pid: number;
  appName: string;
  packageName: string;
  state: "created" | "attached" | "detached" | "error";
  createdAt: number;
  scriptCount: number;
  hookCount: number;
  messageCount: number;
}

/** Injection task */
export interface InjectionTask {
  id: string;
  apkPath: string;
  appName: string;
  packageName: string;
  status: "pending" | "analyzing" | "injecting" | "signing" | "installing" | "done" | "error";
  progress: number;
  arch: string;
  useApktool: boolean;
  autoInstall?: boolean;
  autoScan?: boolean;
  outputApk?: string;
  error?: string;
  createdAt: number;
}

/** MCP module info */
export interface MCPModule {
  name: string;
  displayName: string;
  description: string;
  toolCount: number;
  icon: string;
  enabled: boolean;
}

/** Log entry */
export interface LogEntry {
  id: string;
  timestamp: number;
  level: "info" | "warning" | "error" | "debug";
  source: string;
  message: string;
}

/** Scan result for injection detection */
export interface ScanResult {
  appId: string;
  packageName: string;
  detected: boolean;
  method: "static" | "runtime" | "process" | "none";
  details: string;
  timestamp: number;
}

/** Bottom navigation tab */
export type TabId = "dashboard" | "apps" | "inject" | "mcp" | "settings";


/** User-provided options for creating an injection task. */
export interface InjectionOptions {
  apkPath: string;
  appName?: string;
  packageName?: string;
  arch: string;
  useApktool: boolean;
  autoInstall: boolean;
  autoScan: boolean;
}
