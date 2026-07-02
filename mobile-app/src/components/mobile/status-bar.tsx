"use client";

import { useEffect, useState } from "react";
import { Wifi, BatteryFull, Signal } from "lucide-react";

/**
 * 模拟 Android 状态栏
 * 显示时间、信号、WiFi、电量等信息
 */
export function StatusBar() {
  const [time, setTime] = useState("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const h = now.getHours().toString().padStart(2, "0");
      const m = now.getMinutes().toString().padStart(2, "0");
      setTime(`${h}:${m}`);
    };
    updateTime();
    const interval = setInterval(updateTime, 1000 * 30);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center justify-between px-5 py-2 text-xs font-medium text-foreground/90 select-none">
      <span className="font-mono tracking-tight">{time}</span>
      <div className="flex items-center gap-1.5">
        <Signal className="w-3.5 h-3.5" />
        <Wifi className="w-3.5 h-3.5" />
        <div className="flex items-center gap-0.5">
          <span className="text-[10px]">87%</span>
          <BatteryFull className="w-4 h-4" />
        </div>
      </div>
    </div>
  );
}
