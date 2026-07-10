"use client";

import { useState, useEffect } from "react";
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
import type { InjectionOptions, InjectionTask } from "@/lib/types";
import { basename, cn, isAndroidPackageName } from "@/lib/utils";

interface InjectScreenProps {
  tasks: InjectionTask[];
  onInject: (task: InjectionOptions) => void;
}

export function InjectScreen({ tasks, onInject }: InjectScreenProps) {
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [appName, setAppName] = useState("");
  const [packageName, setPackageName] = useState("");
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

  const inferMeta = (path: string) => {
    const fileName = basename(path).replace(/\.apk$/i, "");
    const readableName = fileName.replace(/[._-]+/g, " ").trim();
    if (!appName) setAppName(readableName || "Unknown APK");
    if (!packageName) {
      const candidate = fileName
        .toLowerCase()
        .replace(/^com[._-]/, "com.")
        .replace(/[^a-z0-9._-]+/g, ".")
        .replace(/[_-]+/g, ".")
        .replace(/\.+/g, ".")
        .replace(/^\.|\.$/g, "");
      setPackageName(candidate.includes(".") ? candidate : `local.${candidate || "app"}`);
    }
  };

  const handleInject = async () => {
    if (!canInject) return;
    setInjecting(true);
    await onInject({
      apkPath: selectedFile,
      appName,
      packageName,
      arch,
      useApktool,
      autoInstall,
      autoScan,
    });
    setInjecting(false);
    setSelectedFile("");
    setAppName("");
    setPackageName("");
  };

  const handleFilePathChange = (value: string) => {
    setSelectedFile(value);
    if (/\.apk$/i.test(value)) inferMeta(value);
  };

  const packageNameValid = !packageName || isAndroidPackageName(packageName);
  const canInject = Boolean(selectedFile) && /\.apk$/i.test(selectedFile) && packageNameValid && !injecting;

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

        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">APK 路径</label>
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-muted/30 border border-border">
            <FileUp className="w-4 h-4 text-muted-foreground shrink-0" />
            <input
              value={selectedFile}
              onChange={(event) => handleFilePathChange(event.target.value)}
              placeholder="/storage/emulated/0/Download/target.apk"
              className="flex-1 bg-transparent text-xs text-foreground placeholder:text-muted-foreground outline-none font-mono min-w-0"
            />
          </div>
          {selectedFile && !/\.apk$/i.test(selectedFile) && (
            <p className="text-[10px] text-destructive">请选择 .apk 文件路径</p>
          )}
        </div>

        {selectedFile && (
          <div className="grid grid-cols-1 gap-2 pt-1">
            <LabeledInput label="应用名" value={appName} onChange={setAppName} placeholder="自动从文件名推导，可修改" />
            <LabeledInput label="包名" value={packageName} onChange={setPackageName} placeholder="com.example.app" mono />
            {!packageNameValid && <p className="text-[10px] text-destructive">包名格式不合法，应类似 com.example.app</p>}
          </div>
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
        disabled={!canInject}
        className={cn(
          "w-full flex items-center justify-center gap-2 py-3.5 rounded-2xl font-semibold text-sm transition-all",
          !canInject
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

      {/* 注入进度步骤 */}
      {injecting && (
        <div className="rounded-2xl bg-card border border-border p-4 space-y-3 fade-in">
          <InjectStep label="解析 APK 文件结构" step={1} delay={0} />
          <InjectStep label="注入 frida-gadget.so" step={2} delay={600} />
          <InjectStep label="修改 smali 加载代码" step={3} delay={1200} />
          <InjectStep label="重新打包并签名" step={4} delay={1800} />
          {autoInstall && <InjectStep label="安装到设备" step={5} delay={2400} />}
        </div>
      )}

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


function LabeledInput({
  label,
  value,
  onChange,
  placeholder,
  mono,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  mono?: boolean;
}) {
  return (
    <label className="space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={cn(
          "w-full px-3 py-2 rounded-xl bg-muted/30 border border-border text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40",
          mono && "font-mono"
        )}
      />
    </label>
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

      {["analyzing", "injecting", "signing", "installing"].includes(task.status) ? (
        <div className="space-y-1">
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${task.progress}%` }}
            />
          </div>
          <p className="text-[10px] text-muted-foreground">{task.progress}% · {statusConfig.label}</p>
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
    case "analyzing":
      return { icon: Loader2, label: "解析中", color: "text-sky-400", bgColor: "bg-sky-400/10" };
    case "injecting":
      return { icon: Loader2, label: "注入中", color: "text-primary", bgColor: "bg-primary/10" };
    case "signing":
      return { icon: Loader2, label: "签名中", color: "text-amber-400", bgColor: "bg-amber-400/10" };
    case "installing":
      return { icon: Loader2, label: "安装中", color: "text-amber-400", bgColor: "bg-amber-400/10" };
    case "error":
      return { icon: AlertCircle, label: "失败", color: "text-destructive", bgColor: "bg-destructive/10" };
    default:
      return { icon: Loader2, label: "等待中", color: "text-muted-foreground", bgColor: "bg-muted/30" };
  }
}

function InjectStep({ label, step, delay }: { label: string; step: number; delay: number }) {
  const [status, setStatus] = useState<"pending" | "active" | "done">("pending");

  useEffect(() => {
    const timer1 = setTimeout(() => setStatus("active"), delay);
    const timer2 = setTimeout(() => setStatus("done"), delay + 500);
    return () => { clearTimeout(timer1); clearTimeout(timer2); };
  }, [delay]);

  return (
    <div className="flex items-center gap-3">
      <div className={cn(
        "w-6 h-6 rounded-full flex items-center justify-center shrink-0 transition-colors",
        status === "done" ? "bg-primary text-primary-foreground" :
        status === "active" ? "bg-primary/20 text-primary" :
        "bg-muted/40 text-muted-foreground"
      )}>
        {status === "done" ? (
          <CheckCircle2 className="w-3.5 h-3.5" />
        ) : status === "active" ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <span className="text-[10px] font-bold">{step}</span>
        )}
      </div>
      <span className={cn(
        "text-xs transition-colors",
        status === "pending" ? "text-muted-foreground" : "text-foreground"
      )}>
        {label}
      </span>
    </div>
  );
}
