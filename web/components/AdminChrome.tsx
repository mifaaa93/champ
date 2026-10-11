"use client";

import { useEffect } from "react";

export function AdminChrome({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    html.classList.add("admin-root");
    body.classList.add("admin-root");
    return () => {
      html.classList.remove("admin-root");
      body.classList.remove("admin-root");
    };
  }, []);
  return <div className="adm-root">{children}</div>;
}
