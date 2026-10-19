"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Nav } from "@/components/Nav";
import { telegramError } from "@/lib/telegramUser";

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

function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [uid, setUid] = useState("");
  const [nickname, setNickname] = useState("");
  const [telegram, setTelegram] = useState("");
  const [website, setWebsite] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [fieldErr, setFieldErr] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const q = (params.get("uid") || "").replace(/\D/g, "").slice(0, 10);
    if (q) setUid(q);
  }, [params]);

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!/^\d{6,10}$/.test(uid.trim())) {
      next.uid = "UID — число из 6–10 цифр";
    }
    if (nickname.trim() && !/^[\p{L}\p{N}_.\- ]{1,32}$/u.test(nickname.trim())) {
      next.nickname = "Ник: буквы, цифры, пробел, точка, _ или -";
    }
    const tgErr = telegramError(telegram, false);
    if (tgErr) next.telegram = tgErr;
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
    <>
    <Nav />
    <main className="wrap">
      <div className="kicker">ENTRY</div>
      <h1>Регистрация</h1>
      <p className="lead">Укажи UID счёта. Для участия в дневном рейтинге нужен депозит от $50 за сегодняшние сутки (UTC+2).</p>
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
            maxLength={200}
            placeholder="https://t.me/username, @username или username"
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
    </>
  );
}

export default function RegisterPage() {
  return (
    <Suspense
      fallback={
        <main className="wrap">
          <p className="note">Загрузка формы…</p>
        </main>
      }
    >
      <RegisterForm />
    </Suspense>
  );
}
