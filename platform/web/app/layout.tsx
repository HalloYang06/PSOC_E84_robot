import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "研发基地庄园",
  description: "人类主导的智能体协作平台，面向嵌入式、机器人和多人联合开发。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
