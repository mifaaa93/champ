"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiPath } from "@/lib/api";

type Gap = {
  already: boolean;
  place: number | null;
  need_pnl: number | null;
  need_pct?: number | null;
  target_pct?: number | null;
  target_pnl?: number | null;
  open_slot?: boolean;
  occupied?: number;
};

type LookupResult = {
  uid: number;
  day: string;
  status: string;
  registered: boolean;
  reasons: string[];
  need_deposit: number;
  min_day_deposit: number;
  require_trade: boolean;
  top_n: number;
  prize_places: number;
  yield: { place: number | null; count: number; top_n: Gap; prize: Gap; first: Gap };
  loss: { place: number | null; count: number; top_n: Gap; prize: Gap; first: Gap };
  you: {
    nickname: string;
    eligible: boolean;
    pnl: number;
    trading_pnl: number;
    return_pct: number;
    deposits: number;
    balance: number;
  } | null;
};

function money(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  const abs = Math.abs(n);
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}$${abs.toFixed(2)}`;
}

function pct(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}${Math.abs(n).toFixed(2)}%`;
}

function reasonText(code: string, needDep: number, minDep: number, requireTrade: boolean) {
  if (code === "min_deposit") {
    return needDep > 0
      ? `внеси ещё ${money(needDep)} сегодня (минимум ${money(minDep)} за сутки)`
      : `нужен депозит от ${money(minDep)} за сегодня`;
  }
  if (code === "no_trades") return requireTrade ? "нужна хотя бы одна сделка за сегодня" : "";
  if (code === "no_start") return "депозит должен пройти, затем подожди пару минут — снимем точку 0";
  if (code === "no_basis") return "нет базы расчёта за сегодня";
  if (code === "not_registered") return "сначала регистрация на сайте";
  if (code === "inactive") return "счёт не Active";
  if (code === "self_excluded") return "на счёте self-exclude";
  return "";
}

function GapLines({
  label,
  gap,
  kind,
  topN,
  prizes,
}: {
  label: string;
  gap: Gap;
  kind: "yield" | "loss";
  topN: number;
  prizes: number;
}) {
  if (gap.already) {
    return <p className="ok">{label}: уже там.</p>;
  }
  if (kind === "yield") {
    if (gap.open_slot) {
      return (
        <p>
          {label}: в топе свободно ({gap.occupied ?? 0} из {topN}). Нужен плюс по счёту
          {gap.need_pnl ? ` — ещё примерно ${money(gap.need_pnl)} прибыли` : ""}.
        </p>
      );
    }
    return (
      <p>
        {label}: нужно обогнать {pct(gap.target_pct)} — ещё {pct(gap.need_pct)}
        {gap.need_pnl != null ? ` (около ${money(gap.need_pnl)} к результату дня)` : ""}.
      </p>
    );
  }
  if (gap.open_slot) {
    return (
      <p>
        {label}: в просадке свободно. Достаточно перейти в торговый минус.
      </p>
    );
  }
  return (
    <p>
      {label}: чтобы обойти текущее {prizes ? "" : ""}место, торговый минус должен быть глубже ещё на{" "}
      {money(gap.need_pnl)} (цель {money(gap.target_pnl)}).
    </p>
  );
}

export function Lookup() {
  const [uid, setUid] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [data, setData] = useState<LookupResult | null>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function run(e?: React.FormEvent) {
    e?.preventDefault();
    const id = uid.replace(/\D/g, "");
    if (!/^\d{6,10}$/.test(id)) {
      setErr("UID — число из 6–10 цифр");
      setOpen(true);
      setData(null);
      return;
    }
    setBusy(true);
    setErr("");
    setOpen(true);
    try {
      const res = await fetch(apiPath(`/public/lookup/${id}`), { cache: "no-store" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof body.detail === "string" ? body.detail : "Не удалось проверить");
      }
      setData(body as LookupResult);
    } catch (e) {
      setData(null);
      setErr(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className="lookup-bar card" onSubmit={run}>
        <div>
          <div className="kicker">ГДЕ Я</div>
          <p className="note" style={{ margin: "4px 0 0" }}>
            Введи UID — покажем место и сколько ещё нужно до топа и призов.
          </p>
        </div>
        <div className="lookup-row">
          <input
            value={uid}
            onChange={(e) => setUid(e.target.value.replace(/\D/g, "").slice(0, 10))}
            inputMode="numeric"
            placeholder="Pocket UID"
            aria-label="UID"
          />
          <button className="cta" type="submit" disabled={busy}>
            {busy ? "Ищем…" : "Проверить"}
          </button>
        </div>
      </form>

      {open ? (
        <div
          className="modal-back"
          onClick={() => setOpen(false)}
          role="presentation"
        >
          <div
            className="card modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="lookup-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button type="button" className="modal-x" onClick={() => setOpen(false)} aria-label="Закрыть">
              ×
            </button>
            <div className="kicker">РЕЗУЛЬТАТ</div>
            <h2 id="lookup-title">{data ? `UID ${data.uid}` : "Проверка места"}</h2>
            {busy ? <p className="note">Смотрим рейтинг дня…</p> : null}
            {err ? <p className="err">{err}</p> : null}

            {data && data.status === "not_registered" ? (
              <>
                <p>Этого UID ещё нет в чемпионате.</p>
                <p>
                  <Link className="cta" href={`/register?uid=${data.uid}`}>
                    Зарегистрировать {data.uid}
                  </Link>
                </p>
              </>
            ) : null}

            {data && data.status === "not_in_day" ? (
              <>
                <p>Ты зарегистрирован, но сегодня не в зачёте.</p>
                <ul className="note">
                  {(data.reasons.length ? data.reasons : ["min_deposit"]).map((c) => {
                    const t = reasonText(c, data.need_deposit, data.min_day_deposit, data.require_trade);
                    return t ? <li key={c}>{t}</li> : null;
                  })}
                </ul>
                {data.need_deposit > 0 ? (
                  <p>
                    Внеси от {money(data.need_deposit)} сегодня (UTC+2), затем подожди 1–2 минуты и проверь снова.
                  </p>
                ) : null}
              </>
            ) : null}

            {data && data.status === "not_in_lists" && data.you ? (
              <>
                <p>
                  В зачёте дня ты есть, но в таблицы доходности и просадки пока не попадаешь. В доходность — только
                  плюс, в просадку — только торговый минус.
                </p>
                <p className="mono">
                  Сейчас: {pct(data.you.return_pct)} · PnL {money(data.you.pnl)}
                </p>
                <p>
                  Чтобы появиться в доходности, нужен плюс
                  {data.yield.first.need_pnl
                    ? ` — примерно ещё ${money(data.yield.first.need_pnl)} к результату`
                    : ""}
                  .
                </p>
              </>
            ) : null}

            {data && data.status === "ranked" && data.you ? (
              <>
                <p className="mono">
                  {data.you.nickname || data.uid} · баланс ${data.you.balance.toFixed(2)} ·{" "}
                  {pct(data.you.return_pct)} · PnL {money(data.you.pnl)}
                </p>
                <p>
                  <strong>Доходность:</strong>{" "}
                  {data.yield.place
                    ? `${data.yield.place} место из ${data.yield.count}`
                    : "пока не в плюсовом списке"}
                </p>
                <GapLines
                  label={`Войти в топ-${data.top_n} доходности`}
                  gap={data.yield.top_n}
                  kind="yield"
                  topN={data.top_n}
                  prizes={data.prize_places}
                />
                <GapLines
                  label={`Призовое место (топ-${data.prize_places})`}
                  gap={data.yield.prize}
                  kind="yield"
                  topN={data.top_n}
                  prizes={data.prize_places}
                />
                <GapLines
                  label="Первое место по доходности"
                  gap={data.yield.first}
                  kind="yield"
                  topN={data.top_n}
                  prizes={data.prize_places}
                />
                <p style={{ marginTop: 16 }}>
                  <strong>Просадка:</strong>{" "}
                  {data.loss.place
                    ? `${data.loss.place} место из ${data.loss.count}`
                    : "нет торгового минуса — в этой номинации тебя нет"}
                </p>
                {data.loss.place || data.you.trading_pnl < 0 ? (
                  <>
                    <GapLines
                      label={`Топ-${data.top_n} просадки`}
                      gap={data.loss.top_n}
                      kind="loss"
                      topN={data.top_n}
                      prizes={data.prize_places}
                    />
                    <GapLines
                      label="Первое место по просадке"
                      gap={data.loss.first}
                      kind="loss"
                      topN={data.top_n}
                      prizes={data.prize_places}
                    />
                  </>
                ) : (
                  <p className="note">Просадка только для тех, у кого торговый PnL ниже нуля.</p>
                )}
                <p>
                  <Link href={`/trader/${data.uid}`}>Открыть карточку</Link>
                </p>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
