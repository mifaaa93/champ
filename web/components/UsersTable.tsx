"use client";

import { useMemo, useState } from "react";

export type ParticipantRow = {
  uid: number;
  nickname: string;
  telegram: string;
  country: string;
  created_at: string | null;
  last_checked_at: string | null;
  eligible: boolean;
  registered?: boolean;
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
  const [scope, setScope] = useState<"all" | "in" | "out" | "named" | "api">("all");
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return users.filter((u) => {
      if (scope === "in" && !u.eligible) return false;
      if (scope === "out" && u.eligible) return false;
      if (scope === "named" && !(u.registered ?? Boolean((u.nickname || "").trim()))) return false;
      if (scope === "api" && (u.registered ?? Boolean((u.nickname || "").trim()))) return false;
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
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Участники</h1>
          <div className="page-subtitle">
            Имя сохраняется после ввода UID на сайте · {filtered.length}/{users.length} · {day || "—"}
          </div>
        </div>
      </div>
      <div className="card">
        <div className="search-bar">
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="🔍 Поиск по UID или имени..."
          />
          <select
            value={scope}
            onChange={(e) => {
              setScope(e.target.value as "all" | "in" | "out" | "named" | "api");
              setPage(1);
            }}
          >
            <option value="all">Все статусы</option>
            <option value="named">Зарегистрировались</option>
            <option value="api">Из API, ещё без регистрации</option>
            <option value="in">В зачёте</option>
            <option value="out">Не в зачёте</option>
          </select>
        </div>
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                {(
                  [
                    ["uid", "UID"],
                    ["nickname", "Имя"],
                    ["telegram", "Telegram"],
                    ["country", "Страна"],
                    ["created_at", "Регистрация"],
                    ["deposits", "Депозит"],
                    ["balance", "Баланс"],
                    ["pnl", "Прибыль"],
                    ["return_pct", "Доходность"],
                    ["eligible", "Статус"],
                  ] as [SortKey, string][]
                ).map(([key, label]) => (
                  <th key={key}>
                    <button type="button" className="th-sort" onClick={() => toggleSort(key)}>
                      {label}
                      {mark(key)}
                    </button>
                  </th>
                ))}
                {onDelete ? <th>Действия</th> : null}
              </tr>
            </thead>
            <tbody>
              {slice.length === 0 ? (
                <tr>
                  <td colSpan={onDelete ? 11 : 10} className="note-dim">
                    Никого не найдено.
                  </td>
                </tr>
              ) : (
                slice.map((u) => (
                  <tr key={u.uid}>
                    <td className="uid-cell">
                      <a href={`/trader/${u.uid}?from=admin`}>{u.uid}</a>
                    </td>
                    <td className="name-cell">
                      {u.nickname || "—"}
                      {(u.registered ?? Boolean((u.nickname || "").trim())) ? (
                        <div className="note-dim">на сайте</div>
                      ) : null}
                    </td>
                    <td>{u.telegram ? `@${u.telegram}` : "—"}</td>
                    <td>{u.country || "—"}</td>
                    <td>{dubaiWhen(u.created_at)}</td>
                    <td>{u.deposits === null ? "—" : `$${u.deposits.toFixed(2)}`}</td>
                    <td>{u.balance === null ? "—" : `$${u.balance.toFixed(2)}`}</td>
                    <td className={u.pnl !== null && u.pnl < 0 ? "loss-cell" : "profit-cell"}>{money(u.pnl)}</td>
                    <td className={u.return_pct !== null && u.return_pct < 0 ? "loss-cell" : "profit-cell"}>
                      {pct(u.return_pct)}
                    </td>
                    <td>
                      {u.eligible ? (
                        <span className="status-badge status-active">активен</span>
                      ) : (
                        <span className="status-badge status-withdraw">{u.dq_reason || "нет"}</span>
                      )}
                    </td>
                    {onDelete && u.registered ? (
                      <td>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          onClick={() => {
                            const who = u.nickname ? `${u.uid} (${u.nickname})` : String(u.uid);
                            if (
                              !window.confirm(
                                `Удалить ${who} из чемпионата?\nОн пропадёт из рейтинга. Снимки и архив дней останутся.`,
                              )
                            ) {
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
          <button type="button" className="btn btn-ghost btn-sm" disabled={safePage <= 1} onClick={() => setPage(1)}>
            «
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={safePage <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Назад
          </button>
          <span className="note-dim">
            {safePage} / {pages} · по {PAGE_SIZE}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={safePage >= pages}
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
          >
            Вперёд
          </button>
          <button type="button" className="btn btn-ghost btn-sm" disabled={safePage >= pages} onClick={() => setPage(pages)}>
            »
          </button>
        </div>
      </div>
    </>
  );
}
