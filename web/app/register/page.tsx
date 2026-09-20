"use client";

import { useState } from "react";
import { apiPath } from "@/lib/api";

export default function RegisterPage() {
  const [uid, setUid] = useState("");
  const [nickname, setNickname] = useState("");
  const [telegram, setTelegram] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const res = await fetch(apiPath("/public/register"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          uid: Number(uid),
          nickname,
          telegram,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        const text =
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((x: { msg?: string }) => x.msg).join("; ")
              : "Не удалось зарегистрировать";
        throw new Error(text);
      }
      setMsg(data.message || "Готово");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wrap">
      <div className="kicker">ENTRY</div>
      <h1>Регистрация в кубок</h1>
      <p className="lead">UID должен быть из нашего партнёрского контура. Затем депозит за сегодня.</p>
      <form className="form card" onSubmit={onSubmit}>
        <label>
          Pocket UID
          <input value={uid} onChange={(e) => setUid(e.target.value)} required inputMode="numeric" />
        </label>
        <label>
          Ник в таблице (необязательно)
          <input value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={64} />
        </label>
        <label>
          Telegram (необязательно)
          <input value={telegram} onChange={(e) => setTelegram(e.target.value)} maxLength={64} />
        </label>
        <button className="cta" disabled={busy} type="submit">
          {busy ? "Проверяем…" : "Зарегистрироваться"}
        </button>
        {msg ? <p className="ok">{msg}</p> : null}
        {err ? <p className="err">{String(err)}</p> : null}
      </form>
    </main>
  );
}
