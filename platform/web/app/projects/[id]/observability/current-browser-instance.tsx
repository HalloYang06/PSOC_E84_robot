"use client";

import { useEffect, useState } from "react";

export function CurrentBrowserInstance() {
  const [origin, setOrigin] = useState("读取中");

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  return (
    <article>
      <span>当前前端</span>
      <strong>{origin}</strong>
      <p>这是你浏览器实际打开的页面实例，用来区分 3000、3001 或其他电脑地址。</p>
    </article>
  );
}
