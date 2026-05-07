"use client";

import { useEffect, useState } from "react";

export type TeamNoticeToast = { id: string; message: string } | null;

// 读取 URL 上的 ?team_notice=… 渲染顶部 toast，3-5 秒后消失，并把 query 从 URL 上移除
// （history.replaceState，不会触发导航或刷新），避免刷新后 toast 二次出现。
//
// server actions（actions.ts 中 51 处用到）会在 redirect 时把 team_notice 写到 URL；
// 之前前端两个壳都没读它，导致绝大多数协作动作没有"已下发 / 已生成 / 已吊销"等可见反馈。
export function useTeamNoticeToast(durationMs = 4000): TeamNoticeToast {
  const [toast, setToast] = useState<TeamNoticeToast>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    let timer: ReturnType<typeof setTimeout> | null = null;

    function pickFromUrl() {
      const url = new URL(window.location.href);
      const message = url.searchParams.get("team_notice");
      if (!message) return;
      url.searchParams.delete("team_notice");
      window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setToast({ id, message });
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => setToast(null), durationMs);
    }

    pickFromUrl();
    window.addEventListener("popstate", pickFromUrl);
    return () => {
      if (timer) clearTimeout(timer);
      window.removeEventListener("popstate", pickFromUrl);
    };
  }, [durationMs]);

  return toast;
}
