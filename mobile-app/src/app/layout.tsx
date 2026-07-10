import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FridaMCP - AI 驱动的 Frida 动态分析",
  description: "将 Frida 动态插桩与 MCP 协议结合，专为 AI 辅助的 Android 应用安全分析而设计。支持应用注入、自动检测、MCP 服务管理。",
  keywords: ["Frida", "MCP", "Android", "Hook", "逆向", "安全分析", "AI"],
  authors: [{ name: "FridaMCP" }],
  icons: {
    icon: "https://z-cdn.chatglm.cn/z-ai/static/logo.svg",
  },
  openGraph: {
    title: "FridaMCP",
    description: "AI 驱动的 Frida 动态分析工具",
    siteName: "FridaMCP",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "FridaMCP",
    description: "AI 驱动的 Frida 动态分析工具",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        {children}
      </body>
    </html>
  );
}
