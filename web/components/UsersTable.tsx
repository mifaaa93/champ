"use client";

import { useMemo, useState } from "react";
import { Hint } from "@/components/Hint";

export type ParticipantRow = {
  uid: number;
  nickname: string;
  telegram: string;
  country: string;
  created_at: string | null;
  last_checked_at: string | null;
  eligible: boolean;
  dq_reason: string;
  balance: number | null;
  pnl: number | null;
  return_pct: number | null;
  deposits: number | null;
};

type SortKey =
  | "uid"
  | "nickname"
  | "telegram"
  | "country"
  | "created_at"
  | "last_checked_at"
  | "deposits"
  | "balance"
  | "pnl"
  | "return_pct"
  | "eligible";

const PAGE_SIZE = 20;

function money(n: number | null) {
  if (n === null || n === undefined) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}

function pct(n: number | null) {
  if (n === null || n === undefined) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function dubaiWhen(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", {
    timeZone: "Africa/Johannesburg",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function cmp(a: ParticipantRow, b: ParticipantRow, key: SortKey, dir: number) {
  const va = a[key];
  const vb = b[key];
  if (va === null || va === undefined) return 1 * dir;
  if (vb === null || vb === undefined) return -1 * dir;
  if (typeof va === "boolean" && typeof vb === "boolean") {
    return ((va ? 1 : 0) - (vb ? 1 : 0)) * dir;
  }
  if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
  return String(va).localeCompare(String(vb), "ru") * dir;
}

export function UsersTable({
  users,
  day,
  onDelete,
}: {
  users: ParticipantRow[];
  day: string;
  onDelete?: (uid: number) => Promise<void>;
}) {
  const [q, setQ] = useState("");
  const [scope, setScope] = useState<"all" | "in" | "out">("all");
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return users.filter((u) => {
      if (scope === "in" && !u.eligible) return false;
      if (scope === "out" && u.eligible) return false;
      if (!needle) return true;
      const blob = `${u.uid} ${u.nickname} ${u.telegram} ${u.country} ${u.dq_reason}`.toLowerCase();
      return blob.includes(needle);
    });
  }, [users, q, scope]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => cmp(a, b, sortKey, sortDir));
    return copy;
  }, [filtered, sortKey, sortDir]);

  const pages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, pages);
  const slice = sorted.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(key);
      setSortDir(key === "created_at" || key === "return_pct" || key === "pnl" ? -1 : 1);
    }
    setPage(1);
  }

  function mark(key: SortKey) {
    if (sortKey !== key) return "";
    return sortDir === 1 ? " ↑" : " ↓";
  }

  return (
    <section id="users" className="card" style={{ marginBottom: 18 }}>
      <h3>
        <Hint text="Все, кто один раз зарегистрировался на сайте. В зачёт сегодняшнего дня попадают только с депозитом за эти сутки UTC+2.">
          Зарегистрированные · {filtered.length}/{users.length} · {day || "—"}
        </Hint>
      </h3>
      <div className="form-grid" style={{ marginBottom: 12 }}>
        <label>
          <Hint text="Ищет сразу по UID, нику, telegram и стране.">Поиск</Hint>
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="UID, ник, telegram, страна"
          />
        </label>
        <label>
          <Hint text="«В зачёте» — сегодня выполнены условия дня (депозит, статус). Остальные зарегистрированы, но в рейтинг дня не входят.">
            Зачёт сегодня
          </Hint>
          <select
            value={scope}
            onChange={(e) => {
              setScope(e.target.value as "all" | "in" | "out");
              setPage(1);
            }}
          >
            <option value="all">все</option>
            <option value="in">в зачёте</option>
            <option value="out">не в зачёте</option>
          </select>
        </label>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead>
            <tr>
              {(
                [
                  ["uid", "UID"],
                  ["nickname", "Ник"],
                  ["telegram", "Telegram"],
                  ["country", "Страна"],
                  ["created_at", "Регистрация"],
                  ["last_checked_at", "Последняя проверка"],
                  ["deposits", "Депозит дня"],
                  ["balance", "Баланс"],
                  ["pnl", "PnL"],
                  ["return_pct", "%"],
                  ["eligible", "Зачёт"],
                ] as [SortKey, string][]
              ).map(([key, label]) => (
                <th key={key}>
                  <button type="button" className="th-sort" onClick={() => toggleSort(key)}>
                    {label}
                    {mark(key)}
                  </button>
                </th>
              ))}
              {onDelete ? <th></th> : null}
            </tr>
          </thead>
          <tbody>
            {slice.length === 0 ? (
              <tr>
                <td colSpan={onDelete ? 12 : 11} className="note">
                  Никого не найдено.
                </td>
              </tr>
            ) : (
              slice.map((u) => (
                <tr key={u.uid}>
                  <td className="mono">
                    <a href={`/trader/${u.uid}?from=admin`}>{u.uid}</a>
                  </td>
                  <td>{u.nickname || "—"}</td>
                  <td className="mono">{u.telegram ? `@${u.telegram}` : "—"}</td>
                  <td>{u.country || "—"}</td>
                  <td className="mono">{dubaiWhen(u.created_at)}</td>
                  <td className="mono">{dubaiWhen(u.last_checked_at)}</td>
                  <td className="mono">{u.deposits === null ? "—" : `$${u.deposits.toFixed(2)}`}</td>
                  <td className="mono">{u.balance === null ? "—" : `$${u.balance.toFixed(2)}`}</td>
                  <td className={`mono ${u.pnl !== null && u.pnl < 0 ? "down" : "up"}`}>{money(u.pnl)}</td>
                  <td className={`mono ${u.return_pct !== null && u.return_pct < 0 ? "down" : "up"}`}>
                    {pct(u.return_pct)}
                  </td>
                  <td>{u.eligible ? "да" : u.dq_reason || "нет"}</td>
                  {onDelete ? (
                    <td>
                      <button
                        type="button"
                        className="cta ghost"
                        onClick={() => {
                          const who = u.nickname ? `${u.uid} (${u.nickname})` : String(u.uid);
                          if (!window.confirm(`Удалить ${who} из чемпионата?\nОн пропадёт из рейтинга. Снимки и архив дней останутся.`)) {
                            return;
                          }
                          const typed = window.prompt(`Введи UID ${u.uid}, чтобы подтвердить удаление:`);
                          if (typed !== String(u.uid)) return;
                          void onDelete(u.uid);
                        }}
                      >
                        Удалить
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button type="button" className="cta ghost" disabled={safePage <= 1} onClick={() => setPage(1)}>
          «
        </button>
        <button
          type="button"
          className="cta ghost"
          disabled={safePage <= 1}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          Назад
        </button>
        <span className="note">
          {safePage} / {pages} · по {PAGE_SIZE}
        </span>
        <button
          type="button"
          className="cta ghost"
          disabled={safePage >= pages}
          onClick={() => setPage((p) => Math.min(pages, p + 1))}
        >
          Вперёд
        </button>
        <button
          type="button"
          className="cta ghost"
          disabled={safePage >= pages}
          onClick={() => setPage(pages)}
        >
          »
        </button>
      </div>
    </section>
  );
}
