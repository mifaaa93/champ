"use client";

import Link from "next/link";
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

  async function load(next = nom) {
    try {
      const data = await api.board(next);
      setRows(data.rows);
      setDay(data.day);
      setErr("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ошибка загрузки");
    }
  }

  useEffect(() => {
    load(nom);
    const id = setInterval(() => load(nom), 30000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
            <th>UID</th>
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
              <tr key={r.uid}>
                <td>{r.place}</td>
                <td className="mono">
                  <Link href={`/trader/${r.uid}`}>{r.nickname || r.uid}</Link>
                </td>
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
