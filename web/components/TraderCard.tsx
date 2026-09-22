"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiPath } from "@/lib/api";

const TOKEN_KEY = "ibcup_admin_token";

function champWhen(iso?: string | null, withDate = false) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", {
    timeZone: "Africa/Johannesburg",
    ...(withDate
      ? { day: "2-digit" as const, month: "2-digit" as const, hour: "2-digit" as const, minute: "2-digit" as const }
      : { hour: "2-digit" as const, minute: "2-digit" as const }),
  });
}

export type TraderPayload = {
  uid: number;
  nickname: string;
  telegram?: string;
  country?: string;
  registered: boolean;
  registered_at?: string | null;
  last_checked_at?: string | null;
  day: string;
  ledger: {
    uid: number;
    nickname: string;
    balance: number;
    start_balance: number;
    pnl: number;
    trading_pnl?: number;
    return_pct: number;
    deposits: number;
    withdrawals: number;
    bonuses: number;
    basis?: number;
    eligible: boolean;
    dq_reason?: string;
    start_ts?: string | null;
    snapshot_ts?: string | null;
    trades?: number;
    status?: string;
    self_excluded?: boolean;
  } | null;
};

export function TraderCard({ data, canEdit }: { data: TraderPayload; canEdit: boolean }) {
  const l = data.ledger;
  const [nickname, setNickname] = useState(data.nickname || "");
  const [telegram, setTelegram] = useState(data.telegram || "");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const token = sessionStorage.getItem(TOKEN_KEY) || "";
    if (!token) {
      setErr("Нет админ-токена. Зайди в /admin.");
      return;
    }
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const res = await fetch(apiPath(`/admin/participants/${data.uid}`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-Admin-Token": token },
        body: JSON.stringify({ nickname, telegram }),
      });
      const body = await res.json();
      if (!res.ok) {
        const detail = body.detail;
        const text =
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((x: { msg?: string } | string) => (typeof x === "string" ? x : x.msg)).join("; ")
              : "Не сохранилось";
        throw new Error(text);
      }
      setMsg("Ник и Telegram сохранены");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>{nickname || data.uid}</h1>
      <p className="note">
        {data.registered ? "Зарегистрирован на сайте" : "Нет регистрации"}
        {data.country ? ` · ${data.country}` : ""}
        {telegram ? ` · @${telegram}` : ""}
      </p>
      {canEdit && data.registered ? (
        <form className="form card" onSubmit={save} style={{ marginBottom: 18 }}>
          <h3>Профиль</h3>
          <label>
            Ник
            <input value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={32} />
          </label>
          <label>
            Telegram
            <input
              value={telegram}
              onChange={(e) => setTelegram(e.target.value)}
              maxLength={64}
              placeholder="@username"
            />
          </label>
          <div className="actions">
            <button className="cta" type="submit" disabled={busy}>
              {busy ? "Сохраняем…" : "Сохранить ник и Telegram"}
            </button>
            <button
              className="cta ghost"
              type="button"
              disabled={busy}
              onClick={async () => {
                if (
                  !window.confirm(
                    `Удалить ${data.uid} из чемпионата?\nОн пропадёт из рейтинга. Снимки и архив дней останутся.`
                  )
                ) {
                  return;
                }
                const typed = window.prompt(`Введи UID ${data.uid}, чтобы подтвердить удаление:`);
                if (typed !== String(data.uid)) return;
                const token = sessionStorage.getItem(TOKEN_KEY) || "";
                setBusy(true);
                setErr("");
                try {
                  const res = await fetch(apiPath(`/admin/participants/${data.uid}`), {
                    method: "DELETE",
                    headers: { "X-Admin-Token": token },
                  });
                  const body = await res.json();
                  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Не удалилось");
                  router.push("/admin#users");
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "ошибка");
                  setBusy(false);
                }
              }}
            >
              Удалить из чемпионата
            </button>
          </div>
          {msg ? <p className="ok">{msg}</p> : null}
          {err ? <p className="err">{err}</p> : null}
        </form>
      ) : null}
      {l ? (
        <section className="grid-2">
          <article className="card">
            <h3>Сегодня · {data.day}</h3>
            <p className="mono">Баланс ${l.balance.toFixed(2)}</p>
            <p className="mono">
              Старт ${l.start_balance.toFixed(2)} · {champWhen(l.start_ts)} UTC+2
            </p>
            <p className="mono">База расчёта {l.basis != null ? `$${l.basis.toFixed(2)}` : "—"}</p>
            <p className={`mono ${l.pnl >= 0 ? "up" : "down"}`}>PnL рейтинга ${l.pnl.toFixed(2)}</p>
            <p className="mono">{l.return_pct.toFixed(2)}%</p>
            <p className={`mono ${(l.trading_pnl ?? l.pnl) >= 0 ? "up" : "down"}`}>
              Торговый PnL ${(l.trading_pnl ?? l.pnl).toFixed(2)}
            </p>
            <p className="note">
              Доходность считает PnL с выводом (вывел — место падает). Просадка считает только
              торговлю. Точка 0 — первый снимок, не 00:00.
            </p>
          </article>
          <article className="card">
            <h3>Движение и статус</h3>
            <p className="mono">Депозит за сутки ${l.deposits.toFixed(2)}</p>
            <p className="mono">Вывод за сутки ${l.withdrawals.toFixed(2)}</p>
            <p className="mono">Бонусы с точки 0 ${l.bonuses.toFixed(2)}</p>
            <p className="mono">Сделок {l.trades ?? "—"}</p>
            <p className="mono">Статус счёта {l.status || "—"}</p>
            <p className="mono">Self-exclude {l.self_excluded ? "да" : "нет"}</p>
            <p className="mono">Регистрация {champWhen(data.registered_at, true)}</p>
            <p className="mono">Последняя проверка UID {champWhen(data.last_checked_at, true)} UTC+2</p>
            <p className="note">{l.eligible ? "в зачёте" : l.dq_reason}</p>
          </article>
        </section>
      ) : (
        <p className="note">Снимка за сегодня ещё нет.</p>
      )}
    </>
  );
}
