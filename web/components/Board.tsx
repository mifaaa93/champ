"use client";

import { useEffect, useState } from "react";
import { api, type BoardRow } from "@/lib/api";

function money(n: number) {
  const sign = n > 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}
function pct(n: number) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

export function Board({ initial }: { initial?: "yield" | "loss" }) {
  const [nom, setNom] = useState<"yield" | "loss">(initial ?? "yield");
  const [rows, setRows] = useState<BoardRow[]>([]);
  const [day, setDay] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    const ctrl = new AbortController();
    let dead = false;
    async function run(next: "yield" | "loss") {
      try {
        const data = await api.board(next, ctrl.signal);
        if (dead) return;
        setRows(data.rows);
        setDay(data.day);
        setErr("");
      } catch (e) {
        if (dead || (e instanceof DOMException && e.name === "AbortError")) return;
        setErr(e instanceof Error ? e.message : "ошибка загрузки");
      }
    }
    void run(nom);
    const id = setInterval(() => void run(nom), 30000);
    return () => {
      dead = true;
      ctrl.abort();
      clearInterval(id);
    };
  }, [nom]);

  return (
    <section className="card">
      <div className="live">
        <i /> {day || "—"}
      </div>
      <div className="tabs">
        <button className={`tab ${nom === "yield" ? "on" : ""}`} onClick={() => setNom("yield")}>
          Доходность
        </button>
        <button className={`tab ${nom === "loss" ? "on" : ""}`} onClick={() => setNom("loss")}>
          Просадка
        </button>
      </div>
      {err ? <p className="err">{err}</p> : null}
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Участник</th>
            <th>Баланс</th>
            <th>PnL</th>
            <th>%</th>
            <th>Вывод</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="note">
                Пока пусто. Нужна регистрация на сайте и депозит за сегодня.
              </td>
            </tr>
          ) : (
            rows.map((r) => (
              <tr key={r.place}>
                <td>{r.place}</td>
                <td className="mono">{r.nickname || "Участник"}</td>
                <td className="mono">${r.balance.toFixed(2)}</td>
                <td className={`mono ${r.pnl >= 0 ? "up" : "down"}`}>{money(r.pnl)}</td>
                <td className={`mono ${r.return_pct >= 0 ? "up" : "down"}`}>{pct(r.return_pct)}</td>
                <td className="mono">{r.withdrawals ? `$${r.withdrawals.toFixed(2)}` : "—"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
