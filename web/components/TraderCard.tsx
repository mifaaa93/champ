"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
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

export function PoRoot({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    document.documentElement.classList.add("po-root");
    document.body.classList.add("po-root");
    return () => {
      document.documentElement.classList.remove("po-root");
      document.body.classList.remove("po-root");
    };
  }, []);
  return children;
}

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

  const pnl = l?.pnl ?? 0;
  const ret = l?.return_pct ?? 0;

  return (
    <>
      <div className="profile-head">
        <div>
          <div className="profile-name">{nickname || data.uid}</div>
          <p className="profile-sub">
            UID {data.uid}
            {data.registered ? " · в чемпионате" : " · нет регистрации"}
            {data.country ? ` · ${data.country}` : ""}
            {telegram ? ` · @${telegram}` : ""}
          </p>
        </div>
        {l ? (
          <span className={`status-badge ${l.eligible ? "status-active" : "status-withdraw"}`}>
            {l.eligible ? "в зачёте" : l.dq_reason || "вне зачёта"}
          </span>
        ) : null}
      </div>

      {canEdit && data.registered ? (
        <form className="profile-panel" onSubmit={save}>
          <h3>Профиль</h3>
          <div className="form-row">
            <label className="form-group">
              <span className="form-label">Ник</span>
              <input className="form-input" value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={32} />
            </label>
            <label className="form-group">
              <span className="form-label">Telegram</span>
              <input
                className="form-input"
                value={telegram}
                onChange={(e) => setTelegram(e.target.value)}
                maxLength={200}
                placeholder="ссылка, @username или username"
              />
            </label>
          </div>
          <div className="profile-actions">
            <button className="btn btn-success" type="submit" disabled={busy}>
              {busy ? "Сохраняем…" : "Сохранить"}
            </button>
            <button
              className="btn btn-danger"
              type="button"
              disabled={busy}
              onClick={async () => {
                if (
                  !window.confirm(
                    `Удалить ${data.uid} из чемпионата?\nОн пропадёт из рейтинга. Снимки и архив дней останутся.`,
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
                  router.push("/admin#participants");
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
        <>
          <div className="profile-grid">
            <div className="profile-stat">
              <span>Депозит дня</span>
              <b>${l.deposits.toFixed(2)}</b>
            </div>
            <div className="profile-stat">
              <span>Баланс</span>
              <b>${l.balance.toFixed(2)}</b>
            </div>
            <div className="profile-stat">
              <span>Прибыль</span>
              <b className={pnl >= 0 ? "up" : "down"}>${pnl.toFixed(2)}</b>
            </div>
            <div className="profile-stat">
              <span>Доходность</span>
              <b className={ret >= 0 ? "up" : "down"}>
                {ret >= 0 ? "+" : ""}
                {ret.toFixed(2)}%
              </b>
            </div>
          </div>
          <div className="profile-panel">
            <h3>Сегодня · {data.day} · UTC+2</h3>
            <p className="note">
              Старт ${l.start_balance.toFixed(2)} · {champWhen(l.start_ts)}. База расчёта{" "}
              {l.basis != null ? `$${l.basis.toFixed(2)}` : "—"}. Торговый PnL $
              {(l.trading_pnl ?? l.pnl).toFixed(2)}.
            </p>
            <p className="note">
              Вывод за сутки ${l.withdrawals.toFixed(2)}. Бонусы ${l.bonuses.toFixed(2)}. Сделок {l.trades ?? "—"}.
              Статус счёта {l.status || "—"}. Self-exclude {l.self_excluded ? "да" : "нет"}.
            </p>
            <p className="note">
              Регистрация {champWhen(data.registered_at, true)}. Последняя проверка{" "}
              {champWhen(data.last_checked_at, true)}.
            </p>
            <p className="note">
              Доходность считает PnL с выводом. Просадка считает только торговлю. Точка 0 — первый снимок после
              депозита дня.
            </p>
          </div>
        </>
      ) : (
        <p className="note">Снимка за сегодня ещё нет.</p>
      )}
    </>
  );
}
