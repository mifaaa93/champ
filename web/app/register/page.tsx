"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((x: { msg?: string }) => x.msg)
      .filter(Boolean)
      .join("; ");
  }
  return "Не удалось зарегистрировать";
}

export default function RegisterPage() {
  const router = useRouter();
  const [uid, setUid] = useState("");
  const [nickname, setNickname] = useState("");
  const [telegram, setTelegram] = useState("");
  const [website, setWebsite] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [fieldErr, setFieldErr] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!/^\d{6,10}$/.test(uid.trim())) {
      next.uid = "UID — число из 6–10 цифр";
    }
    if (nickname.trim() && !/^[\w.\- ]{1,32}$/u.test(nickname.trim())) {
      next.nickname = "Ник: буквы, цифры, пробел, точка, _ или -";
    }
    const tg = telegram.trim().replace(/^@/, "");
    if (tg && !/^[A-Za-z0-9_]{5,32}$/.test(tg)) {
      next.telegram = "Telegram username, 5–32 символа";
    }
    setFieldErr(next);
    return Object.keys(next).length === 0;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setMsg("");
    if (!validate() || busy) return;
    setBusy(true);
    try {
      const res = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          uid: Number(uid),
          nickname: nickname.trim(),
          telegram: telegram.trim(),
          website,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(detailText(data.detail));
      }
      setMsg(data.message || "Готово");
      router.push(`/trader/${data.uid}`);
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
      <p className="lead">Укажи UID счёта Pocket Option. Затем депозит за сегодня.</p>
      <form className="form card" onSubmit={onSubmit} autoComplete="off">
        <label>
          Pocket UID
          <input
            value={uid}
            onChange={(e) => setUid(e.target.value.replace(/\D/g, "").slice(0, 10))}
            required
            inputMode="numeric"
            name="uid"
            placeholder="например 114653273"
          />
          {fieldErr.uid ? <span className="field-err">{fieldErr.uid}</span> : null}
        </label>
        <label className="hp" aria-hidden="true">
          Сайт
          <input
            tabIndex={-1}
            autoComplete="off"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
          />
        </label>
        <label>
          Ник в таблице (необязательно)
          <input value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={32} />
          {fieldErr.nickname ? <span className="field-err">{fieldErr.nickname}</span> : null}
        </label>
        <label>
          Telegram (необязательно)
          <input
            value={telegram}
            onChange={(e) => setTelegram(e.target.value)}
            maxLength={64}
            placeholder="@username"
          />
          {fieldErr.telegram ? <span className="field-err">{fieldErr.telegram}</span> : null}
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
