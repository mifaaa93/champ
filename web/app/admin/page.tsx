"use client";

import { useEffect, useMemo, useState } from "react";
import { Hint } from "@/components/Hint";
import { EventPanel } from "@/components/EventPanel";
import { UsersTable, type ParticipantRow } from "@/components/UsersTable";
import { apiPath } from "@/lib/api";
import {
  buildFinal,
  buildHourly,
  toPreviewHtml,
  validateTelegramHtml,
  type TgContext,
} from "@/lib/tgPreview";

type Settings = {
  top_n: number;
  min_day_deposit: number;
  publish_interval_minutes: number;
  min_return_pct: number;
  prize_yield: number[];
  prize_loss_pct: number[];
  loss_comp_cap: number;
  require_trade: boolean;
  prize_places: number;
  prize_pool: number;
  tg_hourly_header: string;
  tg_yield_title: string;
  tg_yield_row: string;
  tg_yield_empty: string;
  tg_loss_title: string;
  tg_loss_row: string;
  tg_loss_empty: string;
  tg_footer: string;
  tg_final_header: string;
  tg_final_yield_row: string;
  tg_final_loss_row: string;
};

type BoardRow = {
  place: number;
  name: string;
  dep: number;
  turn: number;
  pnl?: number;
  return_pct?: number;
  dummy?: boolean;
  uid?: number;
};

type PublicEvent = {
  name: string;
  prize_pool: number;
  stats_players: number;
  stats_deposits?: number;
  stats_turnover: number;
  top: BoardRow[];
};

type Tab =
  | "dashboard"
  | "participants"
  | "ranking"
  | "top"
  | "prizes"
  | "params"
  | "day"
  | "telegram"
  | "archive";

const TOKEN_KEY = "ibcup_admin_token";

const empty: Settings = {
  top_n: 7,
  min_day_deposit: 50,
  publish_interval_minutes: 60,
  min_return_pct: 0,
  prize_yield: [100, 50, 25],
  prize_loss_pct: [15, 10, 5],
  loss_comp_cap: 500,
  require_trade: false,
  prize_places: 3,
  prize_pool: 5000,
  tg_hourly_header: "<b>Чемпионат</b> · {day} · {time} UTC+2",
  tg_yield_title: "<b>Доходность</b>",
  tg_yield_row: "{place}. <code>{uid}</code> {name}  {pct}  ({pnl})",
  tg_yield_empty: "пока пусто — ждут депозит и регистрацию",
  tg_loss_title: "<b>Просадка</b>",
  tg_loss_row: "{place}. <code>{uid}</code> {name}  {pnl}  ({pct})",
  tg_loss_empty: "нет отрицательных результатов",
  tg_footer: '<a href="{site}">Рейтинг на сайте</a>',
  tg_final_header: "<b>Итоги дня</b> · {day} UTC+2",
  tg_final_yield_row: "{place}. <code>{uid}</code>  приз {prize}",
  tg_final_loss_row: "{place}. <code>{uid}</code>  {prize}",
};

const NAV: { id: Tab; icon: string; label: string; group: string }[] = [
  { id: "dashboard", icon: "📊", label: "Дашборд", group: "Основное" },
  { id: "participants", icon: "👥", label: "Участники", group: "Основное" },
  { id: "ranking", icon: "🏆", label: "Рейтинг", group: "Основное" },
  { id: "top", icon: "✏️", label: "Редактор Топ-10", group: "Основное" },
  { id: "prizes", icon: "💰", label: "Призы ($)", group: "Настройки" },
  { id: "params", icon: "⚙️", label: "Параметры", group: "Настройки" },
  { id: "day", icon: "⏱️", label: "День", group: "Управление" },
  { id: "telegram", icon: "📱", label: "Telegram", group: "Управление" },
  { id: "archive", icon: "📁", label: "Архив", group: "Аналитика" },
];

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((x: unknown) => (typeof x === "string" ? x : (x as { msg?: string }).msg))
      .filter(Boolean)
      .join("; ");
  }
  return "Ошибка запроса";
}

function money(n: number) {
  return `$${Math.round(n).toLocaleString("en-US")}`;
}

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [authed, setAuthed] = useState(false);
  const [form, setForm] = useState<Settings>(empty);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [tgCtx, setTgCtx] = useState<TgContext | null>(null);
  const [users, setUsers] = useState<ParticipantRow[]>([]);
  const [usersDay, setUsersDay] = useState("");
  const [tab, setTab] = useState<Tab>("dashboard");
  const [event, setEvent] = useState<PublicEvent | null>(null);

  useEffect(() => {
    const saved = sessionStorage.getItem(TOKEN_KEY);
    if (saved) {
      setToken(saved);
      void load(saved);
    }
    if (typeof window !== "undefined") {
      const hash = window.location.hash.replace("#", "") as Tab;
      if (NAV.some((n) => n.id === hash)) setTab(hash);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openTab(next: Tab) {
    setTab(next);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `/admin#${next}`);
    }
  }

  const places = useMemo(() => {
    const n = Math.min(10, Math.max(1, Number(form.prize_places) || 1));
    return Array.from({ length: n }, (_, i) => i);
  }, [form.prize_places]);

  async function adminFetch(path: string, method = "GET", body?: unknown, tok = token) {
    const res = await fetch(apiPath(path), {
      method,
      headers: {
        "X-Admin-Token": tok,
        "Content-Type": "application/json",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    let data: unknown = text;
    try {
      data = JSON.parse(text);
    } catch {
      /* raw */
    }
    if (!res.ok) {
      const detail =
        typeof data === "object" && data && "detail" in data
          ? (data as { detail: unknown }).detail
          : text;
      const error = new Error(res.status === 401 ? "Неверный токен" : detailText(detail));
      (error as Error & { status?: number }).status = res.status;
      throw error;
    }
    return data;
  }

  async function loadTg(tok = token, refresh = false) {
    try {
      const q = refresh ? "?refresh=true" : "";
      const data = (await adminFetch(`/admin/telegram-context${q}`, "GET", undefined, tok)) as TgContext;
      setTgCtx(data);
    } catch {
      /* preview stays empty */
    }
  }

  async function loadEvent() {
    try {
      const res = await fetch(apiPath("/public/event"), { cache: "no-store" });
      if (!res.ok) return;
      setEvent((await res.json()) as PublicEvent);
    } catch {
      /* dashboard stays empty */
    }
  }

  async function load(tok = token) {
    setErr("");
    setBusy("load");
    try {
      const data = (await adminFetch("/admin/settings", "GET", undefined, tok)) as Settings;
      setForm({
        ...empty,
        ...data,
        prize_yield: data.prize_yield?.length ? data.prize_yield : empty.prize_yield,
        prize_loss_pct: data.prize_loss_pct?.length ? data.prize_loss_pct : empty.prize_loss_pct,
        min_return_pct: data.min_return_pct ?? 0,
      });
      sessionStorage.setItem(TOKEN_KEY, tok);
      setAuthed(true);
      const plist = (await adminFetch("/admin/participants", "GET", undefined, tok)) as {
        day: string;
        rows: ParticipantRow[];
      };
      setUsers(plist.rows || []);
      setUsersDay(plist.day || "");
      await loadTg(tok, true);
      await loadEvent();
      setStatus("Настройки загружены");
    } catch (e) {
      setAuthed(false);
      setErr(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!(form.top_n >= 1 && form.top_n <= 50)) next.top_n = "Топ: 1–50";
    if (!(form.min_day_deposit >= 1 && form.min_day_deposit <= 1_000_000)) {
      next.min_day_deposit = "Мин. депозит от 1 до 1 000 000";
    }
    if (!(form.publish_interval_minutes >= 15 && form.publish_interval_minutes <= 180)) {
      next.publish_interval_minutes = "Интервал 15–180 минут";
    }
    if (!(form.min_return_pct >= 0 && form.min_return_pct <= 10000)) {
      next.min_return_pct = "Порог доходности 0–10000";
    }
    if (!(form.prize_places >= 1 && form.prize_places <= 10)) next.prize_places = "Мест: 1–10";
    if (!(form.loss_comp_cap >= 0 && form.loss_comp_cap <= 1_000_000)) {
      next.loss_comp_cap = "Кап 0–1 000 000";
    }
    places.forEach((i) => {
      const y = Number(form.prize_yield[i]);
      const p = Number(form.prize_loss_pct[i]);
      if (!(y >= 0 && y <= 1_000_000)) next[`y${i}`] = "Сумма 0–1 000 000";
      if (!(p >= 0 && p <= 100)) next[`p${i}`] = "Процент 0–100";
    });
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function patch<K extends keyof Settings>(key: K, value: Settings[K]) {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "prize_places") {
        const n = Math.min(10, Math.max(1, Number(value) || 1));
        next.prize_places = n;
        next.prize_yield = Array.from({ length: n }, (_, i) => Number(prev.prize_yield[i] ?? 0));
        next.prize_loss_pct = Array.from({ length: n }, (_, i) => Number(prev.prize_loss_pct[i] ?? 0));
      }
      return next;
    });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setBusy("save");
    setErr("");
    try {
      await adminFetch("/admin/settings", "PATCH", {
        top_n: Number(form.top_n),
        min_day_deposit: Number(form.min_day_deposit),
        publish_interval_minutes: Number(form.publish_interval_minutes),
        prize_places: Number(form.prize_places),
        prize_yield: places.map((i) => Number(form.prize_yield[i])),
        prize_loss_pct: places.map((i) => Number(form.prize_loss_pct[i])),
        loss_comp_cap: Number(form.loss_comp_cap),
        require_trade: Boolean(form.require_trade),
        min_return_pct: Number(form.min_return_pct),
        tg_hourly_header: form.tg_hourly_header,
        tg_yield_title: form.tg_yield_title,
        tg_yield_row: form.tg_yield_row,
        tg_yield_empty: form.tg_yield_empty,
        tg_loss_title: form.tg_loss_title,
        tg_loss_row: form.tg_loss_row,
        tg_loss_empty: form.tg_loss_empty,
        tg_footer: form.tg_footer,
        tg_final_header: form.tg_final_header,
        tg_final_yield_row: form.tg_final_yield_row,
        tg_final_loss_row: form.tg_final_loss_row,
      });
      setStatus("Сохранено. Worker подхватит на следующем цикле.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  async function snapshot() {
    setBusy("snap");
    setErr("");
    try {
      const data = (await adminFetch("/admin/snapshot", "POST")) as {
        snapshots?: { ok?: number; fail?: number };
        stats?: { stats_rows?: number; participants?: number };
      };
      setStatus(
        `Снимки: ок ${data.snapshots?.ok ?? 0}, ошибок ${data.snapshots?.fail ?? 0}. ` +
          `Statistics: ${data.stats?.stats_rows ?? 0} строк, участников ${data.stats?.participants ?? 0}.`,
      );
      await loadTg(token, true);
      await loadEvent();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  async function freeze() {
    if (!window.confirm("Закрыть текущие сутки? Итог нельзя пересчитать автоматически.")) return;
    setBusy("freeze");
    setErr("");
    try {
      const data = (await adminFetch("/admin/day-close", "POST")) as {
        status?: string;
        day?: string;
        count?: number;
      };
      if (data.status === "refrozen") {
        setStatus(`День ${data.day} пересчитан, записей: ${data.count ?? 0}.`);
      } else {
        setStatus(`День ${data.day} зафиксирован, записей: ${data.count ?? 0}.`);
      }
      await loadTg(token, true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  async function sendPost(kind: "hourly" | "final") {
    const warn =
      kind === "final"
        ? "Отправить пост ИТОГОВ дня в группу сейчас?"
        : "Отправить часовой пост в группу сейчас?";
    if (!window.confirm(warn)) return;
    setBusy(kind === "hourly" ? "sendH" : "sendF");
    setErr("");
    try {
      const data = (await adminFetch(`/admin/telegram-send?kind=${kind}`, "POST")) as {
        message?: string;
      };
      setStatus(data.message || "Отправлено");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    if (!authed || tab !== "telegram") return;
    const id = window.setInterval(() => void loadTg(token, false), 60000);
    return () => window.clearInterval(id);
  }, [authed, tab, token]);

  const hourlyText = useMemo(() => (tgCtx ? buildHourly(tgCtx, form) : ""), [tgCtx, form]);
  const finalText = useMemo(() => (tgCtx ? buildFinal(tgCtx, form) : ""), [tgCtx, form]);
  const hourlyErrors = useMemo(
    () => (hourlyText ? validateTelegramHtml(hourlyText) : []),
    [hourlyText],
  );
  const finalErrors = useMemo(
    () => (finalText ? validateTelegramHtml(finalText) : []),
    [finalText],
  );

  const avgReturn = useMemo(() => {
    const rows = event?.top || [];
    if (!rows.length) return 0;
    const sum = rows.reduce((acc, r) => acc + Number(r.return_pct || 0), 0);
    return sum / rows.length;
  }, [event]);

  const groups = ["Основное", "Настройки", "Управление", "Аналитика"];

  if (!authed) {
    return (
      <div className="login-wrap">
        <form
          className="login-card"
          onSubmit={(e) => {
            e.preventDefault();
            void load(token);
          }}
        >
          <div className="sidebar-logo">
            PO ADMIN
            <span>Full Control Panel</span>
          </div>
          <div className="form-group">
            <label className="form-label">Токен администратора</label>
            <input
              className="form-input"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={busy === "load" || !token} style={{ width: "100%" }}>
            {busy === "load" ? "Входим…" : "Войти"}
          </button>
          {err ? <p className="err-line">{err}</p> : null}
        </form>
      </div>
    );
  }

  function rankingTable(rows: BoardRow[], limit?: number) {
    const list = limit ? rows.slice(0, limit) : rows;
    return (
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Место</th>
              <th>UID</th>
              <th>Имя</th>
              <th>Депозит</th>
              <th>Оборот</th>
              <th>Прибыль</th>
              <th>Доходность</th>
            </tr>
          </thead>
          <tbody>
            {list.length === 0 ? (
              <tr>
                <td colSpan={7} className="note-dim">
                  Пока пусто
                </td>
              </tr>
            ) : (
              list.map((row) => (
                <tr key={row.place}>
                  <td className={`rank-cell${row.place <= 3 ? ` rank-${row.place}` : ""}`}>{row.place}</td>
                  <td className="uid-cell">{row.dummy ? "HIDDEN" : row.uid || "—"}</td>
                  <td className="name-cell">{row.name}</td>
                  <td>{money(row.dep)}</td>
                  <td>{money(row.turn)}</td>
                  <td className={(row.pnl || 0) >= 0 ? "profit-cell" : "loss-cell"}>{money(row.pnl || 0)}</td>
                  <td className={(row.return_pct || 0) >= 0 ? "profit-cell" : "loss-cell"}>
                    {(row.return_pct || 0) >= 0 ? "+" : ""}
                    {(row.return_pct || 0).toFixed(1)}%
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-logo">
          PO ADMIN
          <span>Full Control Panel</span>
        </div>
        {groups.map((group) => (
          <div className="nav-section" key={group}>
            <div className="nav-section-title">{group}</div>
            {NAV.filter((n) => n.group === group).map((n) => (
              <button
                type="button"
                key={n.id}
                className={`nav-item ${tab === n.id ? "active" : ""}`}
                onClick={() => openTab(n.id)}
              >
                <span className="icon">{n.icon}</span>
                {n.label}
                {n.id === "participants" ? <span className="badge">{users.length}</span> : null}
              </button>
            ))}
          </div>
        ))}
        <div className="nav-section">
          <div className="nav-section-title">Сессия</div>
          <button
            type="button"
            className="nav-item"
            onClick={() => {
              sessionStorage.removeItem(TOKEN_KEY);
              setAuthed(false);
            }}
          >
            <span className="icon">🚪</span>
            Выйти
          </button>
        </div>
        <div className="sidebar-footer">
          <div className="admin-status">
            <span className="dot" />
            <span>Полный контроль активен</span>
          </div>
        </div>
      </aside>
      <main className="main">
        <div className="toast-container">
          {status ? <div className="toast success">{status}</div> : null}
          {err ? <div className="toast error">{err}</div> : null}
        </div>
        <div className="mobile-nav">
          {NAV.map((n) => (
            <button
              type="button"
              key={n.id}
              className={`btn btn-sm ${tab === n.id ? "btn-primary" : "btn-ghost"}`}
              onClick={() => openTab(n.id)}
            >
              {n.label}
            </button>
          ))}
        </div>

        <section className={`section ${tab === "dashboard" ? "active" : ""}`}>
          <div className="page-header">
            <div>
              <h1 className="page-title">Дашборд</h1>
              <div className="page-subtitle">Живые цифры с публичного рейтинга</div>
            </div>
            <button className="btn btn-ghost" type="button" onClick={() => void loadEvent()}>
              🔄 Обновить
            </button>
          </div>
          <div className="stats-grid">
            <button type="button" className="stat-card cyan" onClick={() => openTab("participants")}>
              <div className="stat-label">Участников</div>
              <div className="stat-value">{(event?.stats_players || 0).toLocaleString("en-US")}</div>
            </button>
            <button type="button" className="stat-card green" onClick={() => openTab("ranking")}>
              <div className="stat-label">Общий депозит</div>
              <div className="stat-value">{money(event?.stats_deposits || 0)}</div>
            </button>
            <button type="button" className="stat-card gold" onClick={() => openTab("prizes")}>
              <div className="stat-label">Призовой пул</div>
              <div className="stat-value">{money(event?.prize_pool || form.prize_pool || 0)}</div>
            </button>
            <button type="button" className="stat-card purple" onClick={() => openTab("ranking")}>
              <div className="stat-label">Средняя доходность</div>
              <div className="stat-value">
                {avgReturn >= 0 ? "+" : ""}
                {avgReturn.toFixed(1)}%
              </div>
            </button>
          </div>
          <div className="card">
            <div className="card-header">
              <div className="card-title">🔥 Топ-5 текущего рейтинга</div>
              <span className="card-badge badge-live">● LIVE</span>
            </div>
            {rankingTable(event?.top || [], 5)}
          </div>
        </section>

        <section className={`section ${tab === "participants" ? "active" : ""}`}>
          <UsersTable
            users={users}
            day={usersDay}
            onDelete={async (uid) => {
              setBusy("del");
              setErr("");
              try {
                await adminFetch(`/admin/participants/${uid}`, "DELETE");
                setUsers((prev) => prev.filter((u) => u.uid !== uid));
                setStatus(`UID ${uid} удалён из чемпионата`);
              } catch (e) {
                setErr(e instanceof Error ? e.message : "ошибка");
              } finally {
                setBusy("");
              }
            }}
          />
        </section>

        <section className={`section ${tab === "ranking" ? "active" : ""}`}>
          <div className="page-header">
            <div>
              <h1 className="page-title">Рейтинг Live</h1>
              <div className="page-subtitle">Обновление с публичной витрины</div>
            </div>
            <button className="btn btn-ghost" type="button" onClick={() => void loadEvent()}>
              🔄 Обновить
            </button>
          </div>
          <div className="card">{rankingTable(event?.top || [])}</div>
        </section>

        <section className={`section ${tab === "top" || tab === "prizes" || tab === "params" ? "active" : ""}`}>
          {tab === "top" || tab === "prizes" || tab === "params" ? (
            <EventPanel
              adminFetch={adminFetch}
              onStatus={setStatus}
              onError={setErr}
              section={tab === "top" ? "top" : tab === "prizes" ? "prizes" : "params"}
            />
          ) : null}
        </section>

        <section className={`section ${tab === "day" ? "active" : ""}`}>
          <div className="page-header">
            <div>
              <h1 className="page-title">Управление днём</h1>
              <div className="page-subtitle">Снимки, закрытие суток, посты</div>
            </div>
          </div>
          <div className="card">
            <div className="day-actions">
              <button className="btn btn-primary" type="button" onClick={() => void snapshot()} disabled={Boolean(busy)}>
                {busy === "snap" ? "Снимаем…" : "📸 Snapshot"}
              </button>
              <button className="btn btn-primary" type="button" onClick={() => void loadEvent()} disabled={Boolean(busy)}>
                🔄 Обновить рейтинг
              </button>
              <button className="btn btn-success" type="button" onClick={() => void sendPost("hourly")} disabled={Boolean(busy)}>
                {busy === "sendH" ? "Шлём…" : "📤 Telegram"}
              </button>
              <button className="btn btn-danger" type="button" onClick={() => void freeze()} disabled={Boolean(busy)}>
                {busy === "freeze" ? "Фиксируем…" : "🔒 Закрыть день"}
              </button>
            </div>
          </div>
        </section>

        <section className={`section ${tab === "telegram" ? "active" : ""}`}>
          <div className="page-header">
            <div>
              <h1 className="page-title">Telegram бот</h1>
              <div className="page-subtitle">Шаблоны постов. Токен бота лежит в окружении сервера.</div>
            </div>
          </div>
          <form className="card" onSubmit={save}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">
                  <Hint text="Сколько человек попадает в часовой пост: топ по доходности и отдельно топ по просадке.">
                    Участников в посте (1–50)
                  </Hint>
                </label>
                <input
                  className="form-input"
                  type="number"
                  min={1}
                  max={50}
                  value={form.top_n}
                  onChange={(e) => patch("top_n", Number(e.target.value))}
                />
                {errors.top_n ? <span className="field-err">{errors.top_n}</span> : null}
              </div>
              <div className="form-group">
                <label className="form-label">Пост каждые, мин</label>
                <input
                  className="form-input"
                  type="number"
                  min={15}
                  max={180}
                  value={form.publish_interval_minutes}
                  onChange={(e) => patch("publish_interval_minutes", Number(e.target.value))}
                />
                {errors.publish_interval_minutes ? (
                  <span className="field-err">{errors.publish_interval_minutes}</span>
                ) : null}
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Мин. депозит дня, $</label>
                <input
                  className="form-input"
                  type="number"
                  min={1}
                  value={form.min_day_deposit}
                  onChange={(e) => patch("min_day_deposit", Number(e.target.value))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Мин. доходность в посте, %</label>
                <input
                  className="form-input"
                  type="number"
                  min={0}
                  step={0.1}
                  value={form.min_return_pct}
                  onChange={(e) => patch("min_return_pct", Number(e.target.value))}
                />
              </div>
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={form.require_trade}
                onChange={(e) => patch("require_trade", e.target.checked)}
              />
              Нужна хотя бы одна сделка за день
            </label>
            <div className="form-group">
              <label className="form-label">Шапка часового поста</label>
              <textarea
                className="form-input"
                rows={2}
                value={form.tg_hourly_header}
                onChange={(e) => patch("tg_hourly_header", e.target.value)}
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Заголовок доходности</label>
                <input className="form-input" value={form.tg_yield_title} onChange={(e) => patch("tg_yield_title", e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Заголовок просадки</label>
                <input className="form-input" value={form.tg_loss_title} onChange={(e) => patch("tg_loss_title", e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Строка доходности</label>
              <input className="form-input" value={form.tg_yield_row} onChange={(e) => patch("tg_yield_row", e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Строка просадки</label>
              <input className="form-input" value={form.tg_loss_row} onChange={(e) => patch("tg_loss_row", e.target.value)} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Пустая доходность</label>
                <input className="form-input" value={form.tg_yield_empty} onChange={(e) => patch("tg_yield_empty", e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Пустая просадка</label>
                <input className="form-input" value={form.tg_loss_empty} onChange={(e) => patch("tg_loss_empty", e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Подвал</label>
              <textarea className="form-input" rows={2} value={form.tg_footer} onChange={(e) => patch("tg_footer", e.target.value)} />
            </div>
            <div className="preview-box">
              {hourlyErrors.length ? (
                <p className="err-line">{hourlyErrors.join("; ")}</p>
              ) : hourlyText ? (
                <p className="ok-line">Часовой пост: HTML корректный</p>
              ) : (
                <p className="note-dim">Ждём данные рейтинга…</p>
              )}
              <div className="preview tg-preview" dangerouslySetInnerHTML={{ __html: toPreviewHtml(hourlyText) }} />
            </div>
            <div className="form-group">
              <label className="form-label">Шапка итогов дня</label>
              <input className="form-input" value={form.tg_final_header} onChange={(e) => patch("tg_final_header", e.target.value)} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Итог, строка доходности</label>
                <input
                  className="form-input"
                  value={form.tg_final_yield_row}
                  onChange={(e) => patch("tg_final_yield_row", e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Итог, строка просадки</label>
                <input
                  className="form-input"
                  value={form.tg_final_loss_row}
                  onChange={(e) => patch("tg_final_loss_row", e.target.value)}
                />
              </div>
            </div>
            <div className="preview-box">
              <p className="note-dim">
                {tgCtx?.final_source === "frozen"
                  ? "Зафиксированный итог закрытого дня."
                  : "Черновик: день ещё не закрыт, места посчитаны по текущему рейтингу."}
              </p>
              {finalErrors.length ? (
                <p className="err-line">{finalErrors.join("; ")}</p>
              ) : finalText ? (
                <p className="ok-line">Итоги дня: HTML корректный</p>
              ) : (
                <p className="note-dim">Ждём данные рейтинга…</p>
              )}
              <div className="preview tg-preview" dangerouslySetInnerHTML={{ __html: toPreviewHtml(finalText) }} />
            </div>
            <p className="note-dim">Отправка в группу берёт уже сохранённые шаблоны. Сначала сохрани, если правил текст.</p>
            <div className="header-actions">
              <button className="btn btn-success" type="submit" disabled={Boolean(busy)}>
                {busy === "save" ? "Сохраняем…" : "💾 Сохранить"}
              </button>
              <button className="btn btn-primary" type="button" disabled={Boolean(busy)} onClick={() => void sendPost("hourly")}>
                {busy === "sendH" ? "Шлём…" : "Отправить часовой"}
              </button>
              <button className="btn btn-ghost" type="button" disabled={Boolean(busy)} onClick={() => void sendPost("final")}>
                {busy === "sendF" ? "Шлём…" : "Отправить итоги"}
              </button>
            </div>
          </form>
        </section>

        <section className={`section ${tab === "archive" ? "active" : ""}`}>
          <div className="page-header">
            <div>
              <h1 className="page-title">Архив</h1>
              <div className="page-subtitle">Закрытые дни чемпионата</div>
            </div>
          </div>
          <div className="card" style={{ textAlign: "center", padding: 40 }}>
            <p className="note-dim" style={{ marginBottom: 16 }}>
              Архив дней открывается на отдельной странице.
            </p>
            <a className="btn btn-primary" href="/archive">
              Открыть архив
            </a>
          </div>
        </section>
      </main>
    </>
  );
}
