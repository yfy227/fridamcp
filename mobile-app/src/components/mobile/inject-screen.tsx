"use client";

import { useState } from "react";
import {
  FileUp,
  Syringe,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Cpu,
  FileArchive,
  Shield,
  Download,
  Info,
  ChevronRight,
} from "lucide-react";
import type { InjectionTask } from "@/lib/types";
import { cn } from "@/lib/utils";

interface InjectScreenProps {
  tasks: InjectionTask[];
  onInject: (task: Omit<InjectionTask, "id" | "status" | "progress" | "createdAt">) => void;
}

export function InjectScreen({ tasks, onInject }: InjectScreenProps) {
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [arch, setArch] = useState("arm64-v8a");
  const [useApktool, setUseApktool] = useState(true);
  const [autoInstall, setAutoInstall] = useState(true);
  const [autoScan, setAutoScan] = useState(true);
  const [injecting, setInjecting] = useState(false);

  const archs = [
    { value: "arm64-v8a", label: "arm64-v8a", desc: "64位 (推荐)" },
    { value: "armeabi-v7a", label: "armeabi-v7a", desc: "32位" },
    { value: "x86", label: "x86", desc: "模拟器" },
    { value: "x86_64", label: "x86_64", desc: "64位模拟器" },
  ];

  const handleInject = () => {
    if (!selectedFile) return;
    setInjecting(true);
    const fileName = selectedFile.split("/").pop() || "unknown.apk";
    const appName = fileName.replace(".apk", "").replace(/_/g, " ");
    onInject({
      apkPath: selectedFile,
      appName,
      packageName: `com.${appName.toLowerCase().replace(/\s/g, ".")}`,
      arch,
      useApktool,
    });
    setTimeout(() => {
      setInjecting(false);
      setSelectedFile("");
    }, 3000);
  };

  const handleFileSelect = () => {
    // 模拟文件选择
    const mockFiles = [
      "/storage/emulated/0/Download/com.example.demo.apk",
      "/storage/emulated/0/Download/test_app.apk",
      "/storage/emulated/0/Download/sample.apk",
    ];
    setSelectedFile(mockFiles[Math.floor(Math.random() * mockFiles.length)]);
  };

  return (
    <div className="px-4 pb-6 space-y-4 fade-in">
      {/* 说明卡片 */}
      <section className="rounded-2xl bg-primary/5 border border-primary/20 p-4 space-y-2">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-foreground">APK 注入说明</h3>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              将 frida-gadget 注入到目标 APK 中，应用启动时自动加载 Frida，无需 root。
              注入完成后可自动安装并检测。
            </p>
          </div>
        </div>
      </section>

      {/* 文件选择 */}
      <section className="rounded-2xl bg-card border border-border p-4 space-y-3">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <FileArchive className="w-4 h-4 text-primary" />
          选择 APK 文件
        </h3>

        {selectedFile ? (
          <div className="flex items-center gap-3 p-3 rounded-xl bg-muted/40">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center shrink-0">
              <FileArchive className="w-5 h-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-foreground truncate">
                {selectedFile.split("/").pop()}
              </p>
              <p className="text-[10px] text-muted-foreground font-mono truncate">
                {selectedFile}
              </p>
            </div>
            <button
              onClick={() => setSelectedFile("")}
              className="text-xs text-destructive hover:underline shrink-0"
            >
              更换
            </button>
          </div>
        ) : (
          <button
            onClick={handleFileSelect}
            className="w-full flex flex-col items-center justify-center gap-2 py-8 rounded-xl border-2 border-dashed border-border hover:border-primary/40 hover:bg-primary/5 transition-colors"
          >
            <FileUp className="w-8 h-8 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">点击选择 APK 文件</span>
            <span className="text-[10px] text-muted-foreground/70">支持从文件管理器选择</span>
          </button>
        )}
      </section>

      {/* 注入选项 */}
      <section className="rounded-2xl bg-card border border-border p-4 space-y-4">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Cpu className="w-4 h-4 text-primary" />
          注入配置
        </h3>

        {/* 架构选择 */}
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">目标架构</label>
          <div className="grid grid-cols-2 gap-2">
            {archs.map((a) => (
              <button
                key={a.value}
                onClick={() => setArch(a.value)}
                className={cn(
                  "flex flex-col items-start p-2.5 rounded-xl border text-left transition-colors",
                  arch === a.value
                    ? "bg-primary/10 border-primary/30"
                    : "bg-muted/30 border-border"
                )}
              >
                <span className={cn(
                  "text-xs font-mono font-medium",
                  arch === a.value ? "text-primary" : "text-foreground"
                )}>
                  {a.label}
                </span>
                <span className="text-[10px] text-muted-foreground">{a.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* 开关选项 */}
        <div className="space-y-1">
          <ToggleRow
            label="使用 Apktool 反编译"
            desc="更精确的 smali 注入（推荐）"
            checked={useApktool}
            onChange={setUseApktool}
          />
          <ToggleRow
            label="注入后自动安装"
            desc="注入完成后自动安装到设备"
            checked={autoInstall}
            onChange={setAutoInstall}
          />
          <ToggleRow
            label="安装后自动扫描检测"
            desc="自动检测注入结果并更新应用列表"
            checked={autoScan}
            onChange={setAutoScan}
          />
        </div>
      </section>

      {/* 注入按钮 */}
      <button
        onClick={handleInject}
        disabled={!selectedFile || injecting}
        className={cn(
          "w-full flex items-center justify-center gap-2 py-3.5 rounded-2xl font-semibold text-sm transition-all",
          !selectedFile || injecting
            ? "bg-muted text-muted-foreground"
            : "bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.98]"
        )}
      >
        {injecting ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            正在注入...
          </>
        ) : (
          <>
            <Syringe className="w-4 h-4" />
            开始注入
          </>
        )}
      </button>

      {/* 历史任务 */}
      {tasks.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-foreground px-1">注入历史</h3>
          <div className="space-y-2">
            {tasks.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function ToggleRow({
  label,
  desc,
  checked,
  onChange,
}: {
  label: string;
  desc: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex-1 min-w-0 pr-3">
        <p className="text-xs font-medium text-foreground">{label}</p>
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

function TaskCard({ task }: { task: InjectionTask }) {
  const statusConfig = getTaskStatusConfig(task.status);

  return (
    <div className="rounded-2xl bg-card border border-border p-3 space-y-2">
      <div className="flex items-center gap-3">
        <div className={cn(
          "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
          statusConfig.bgColor
        )}>
          <statusConfig.icon className={cn("w-4.5 h-4.5", statusConfig.color, task.status === "injecting" && "animate-spin")} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-foreground truncate">{task.appName}</p>
          <p className="text-[10px] text-muted-foreground font-mono truncate">{task.packageName}</p>
        </div>
        <span className={cn("text-[10px] font-medium shrink-0", statusConfig.color)}>
          {statusConfig.label}
        </span>
      </div>

      {task.status === "injecting" || task.status === "signing" ? (
        <div className="space-y-1">
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${task.progress}%` }}
            />
          </div>
          <p className="text-[10px] text-muted-foreground">{task.progress}% · {task.status === "injecting" ? "注入中" : "签名中"}</p>
        </div>
      ) : null}

      {task.outputApk && task.status === "done" && (
        <div className="flex items-center gap-2 pt-1.5 border-t border-border/50">
          <button className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-muted/50 text-foreground hover:bg-muted transition-colors">
            <Download className="w-3.5 h-3.5" />
            安装
          </button>
          <button className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
            <Shield className="w-3.5 h-3.5" />
            检测
          </button>
        </div>
      )}

      {task.error && (
        <p className="text-[10px] text-destructive pt-1.5 border-t border-border/50">{task.error}</p>
      )}
    </div>
  );
}

function getTaskStatusConfig(status: InjectionTask["status"]) {
  switch (status) {
    case "done":
      return { icon: CheckCircle2, label: "完成", color: "text-primary", bgColor: "bg-primary/10" };
    case "injecting":
      return { icon: Loader2, label: "注入中", color: "text-primary", bgColor: "bg-primary/10" };
    case "signing":
      return { icon: Loader2, label: "签名中", color: "text-amber-400", bgColor: "bg-amber-400/10" };
    case "error":
      return { icon: AlertCircle, label: "失败", color: "text-destructive", bgColor: "bg-destructive/10" };
    default:
      return { icon: Loader2, label: "等待中", color: "text-muted-foreground", bgColor: "bg-muted/30" };
  }
}
