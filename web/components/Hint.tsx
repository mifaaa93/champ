"use client";

import { useRef, useState } from "react";

export function Hint({ text, children }: { text: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const timer = useRef<number | null>(null);

  function enter() {
    timer.current = window.setTimeout(() => setOpen(true), 1000);
  }

  function leave() {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
    setOpen(false);
  }

  return (
    <span className="hint-wrap" onMouseEnter={enter} onMouseLeave={leave} onFocus={enter} onBlur={leave}>
      {children}
      {open ? (
        <span className="hint-pop" role="tooltip">
          {text}
        </span>
      ) : null}
    </span>
  );
}
