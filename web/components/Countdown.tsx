"use client";

import { useEffect, useState } from "react";

function fmt(total: number) {
  const s = Math.max(0, total);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return [h, m, sec].map((n) => String(n).padStart(2, "0")).join(":");
}

export function Countdown({ seconds }: { seconds: number }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    setLeft(seconds);
    const id = setInterval(() => setLeft((v) => Math.max(0, v - 1)), 1000);
    return () => clearInterval(id);
  }, [seconds]);
  return (
    <div className="clock">
      <div className="live">
        <i /> LIVE · ДО КОНЦА СУТОК
      </div>
      <div className="digits">{fmt(left)}</div>
      <small>Календарный день Asia/Dubai (UTC+4). Итог фиксируется в 23:59.</small>
    </div>
  );
}
