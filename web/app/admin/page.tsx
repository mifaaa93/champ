"use client";

import { useState } from "react";
import { apiPath } from "@/lib/api";

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [body, setBody] = useState("{\n  \"top_n\": 7,\n  \"min_day_deposit\": 50\n}");
  const [out, setOut] = useState("");

  async function call(path: string, method = "GET", json?: string) {
    const res = await fetch(apiPath(path), {
      method,
      headers: {
        "X-Admin-Token": token,
        "Content-Type": "application/json",
      },
      body: json ? json : undefined,
    });
    setOut(await res.text());
  }

  return (
    <main className="wrap">
      <div className="kicker">OPS</div>
      <h1>Админка</h1>
      <form className="form card" onSubmit={(e) => e.preventDefault()}>
        <label>
          Admin token
          <input value={token} onChange={(e) => setToken(e.target.value)} />
        </label>
        <label>
          PATCH settings JSON
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={6}
            style={{ width: "100%", background: "#0b0d12", color: "inherit", borderRadius: 12 }}
          />
        </label>
        <button className="cta ghost" type="button" onClick={() => call("/admin/settings")}>
          Читать настройки
        </button>
        <button className="cta ghost" type="button" onClick={() => call("/admin/settings", "PATCH", body)}>
          Сохранить
        </button>
        <button className="cta ghost" type="button" onClick={() => call("/admin/snapshot", "POST")}>
          Снять снимки сейчас
        </button>
        <button className="cta" type="button" onClick={() => call("/admin/day-close", "POST")}>
          Freeze дня
        </button>
        <pre className="note">{out}</pre>
      </form>
    </main>
  );
}
