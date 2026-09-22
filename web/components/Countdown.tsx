"use client";

import { useEffect, useRef, useState } from "react";
import { apiPath } from "@/lib/api";

function fmt(total: number) {
  const s = Math.max(0, total);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return [h, m, sec].map((n) => String(n).padStart(2, "0")).join(":");
}

function leftFrom(endMs: number) {
  return Math.max(0, Math.floor((endMs - Date.now()) / 1000));
}

export function Countdown({ seconds, dayEnd }: { seconds: number; dayEnd?: string }) {
  const initialEnd =
    dayEnd && !Number.isNaN(Date.parse(dayEnd))
      ? Date.parse(dayEnd)
      : Date.now() + Math.max(0, seconds) * 1000;
  const endRef = useRef(initialEnd);
  const [left, setLeft] = useState(() => leftFrom(initialEnd));

  useEffect(() => {
    function tick() {
      setLeft(leftFrom(endRef.current));
    }

    async function resync() {
      try {
        const res = await fetch(apiPath("/public/meta"), { cache: "no-store" });
        if (!res.ok) {
          tick();
          return;
        }
        const meta = (await res.json()) as { day_end?: string; seconds_to_close?: number };
        if (meta.day_end) {
          const parsed = Date.parse(meta.day_end);
          if (!Number.isNaN(parsed)) {
            endRef.current = parsed;
            tick();
            return;
          }
        }
        if (typeof meta.seconds_to_close === "number") {
          endRef.current = Date.now() + meta.seconds_to_close * 1000;
        }
        tick();
      } catch {
        tick();
      }
    }

    tick();
    const tickId = window.setInterval(tick, 1000);
    const syncId = window.setInterval(resync, 30000);

    function onWake() {
      tick();
      void resync();
    }
    function onVis() {
      if (document.visibilityState === "visible") onWake();
    }

    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onWake);
    window.addEventListener("online", onWake);
    window.addEventListener("pageshow", onWake);
    return () => {
      window.clearInterval(tickId);
      window.clearInterval(syncId);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onWake);
      window.removeEventListener("online", onWake);
      window.removeEventListener("pageshow", onWake);
    };
  }, []);

  return (
    <div className="clock">
      <div className="live">
        <i /> LIVE · ДО КОНЦА СУТОК
      </div>
      <div className="digits">{fmt(left)}</div>
      <small>Календарный день UTC+2. Итог фиксируется в 23:59.</small>
    </div>
  );
}
