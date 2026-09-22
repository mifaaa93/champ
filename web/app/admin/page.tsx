
"use client";

import { useEffect, useMemo, useState } from "react";
import { Hint } from "@/components/Hint";
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
  const [tab, setTab] = useState<"users" | "settings">("users");

  useEffect(() => {
    const saved = sessionStorage.getItem(TOKEN_KEY);
    if (saved) {
      setToken(saved);
      void load(saved);
    }
    if (typeof window !== "undefined" && window.location.hash === "#settings") {
      setTab("settings");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openTab(next: "users" | "settings") {
    setTab(next);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", next === "users" ? "/admin#users" : "/admin#settings");
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
          `Statistics: ${data.stats?.stats_rows ?? 0} строк, участников ${data.stats?.participants ?? 0}.`
      );
      await loadTg(token, true);
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
      if (data.status === "already_frozen") {
        setStatus(`День ${data.day} уже закрыт.`);
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
    if (!authed || tab !== "settings") return;
    const id = window.setInterval(() => void loadTg(token, false), 60000);
    return () => window.clearInterval(id);
  }, [authed, tab, token]);

  const hourlyText = useMemo(() => (tgCtx ? buildHourly(tgCtx, form) : ""), [tgCtx, form]);
  const finalText = useMemo(() => (tgCtx ? buildFinal(tgCtx, form) : ""), [tgCtx, form]);
  const hourlyErrors = useMemo(
    () => (hourlyText ? validateTelegramHtml(hourlyText) : []),
    [hourlyText]
  );
  const finalErrors = useMemo(
    () => (finalText ? validateTelegramHtml(finalText) : []),
    [finalText]
  );

  if (!authed) {
    return (
      <main className="wrap">
        <div className="kicker">OPS</div>
        <h1>Админка</h1>
        <form
          className="form card"
          onSubmit={(e) => {
            e.preventDefault();
            void load(token);
          }}
        >
          <label>
            Токен администратора
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <button className="cta" type="submit" disabled={busy === "load" || !token}>
            {busy === "load" ? "Входим…" : "Войти"}
          </button>
          {err ? <p className="err">{err}</p> : null}
        </form>
      </main>
    );
  }

  return (
    <main className="wrap">
      <div className="kicker">OPS</div>
      <h1>Админка</h1>
      <div className="tabs">
        <button type="button" className={`tab ${tab === "users" ? "on" : ""}`} onClick={() => openTab("users")}>
          Участники
        </button>
        <button type="button" className={`tab ${tab === "settings" ? "on" : ""}`} onClick={() => openTab("settings")}>
          Настройки
        </button>
        <button
          type="button"
          className="tab"
          onClick={() => {
            sessionStorage.removeItem(TOKEN_KEY);
            setAuthed(false);
          }}
        >
          Выйти
        </button>
      </div>
      {status ? <p className="ok">{status}</p> : null}
      {err ? <p className="err">{err}</p> : null}
      {tab === "users" ? (
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
      ) : null}
      {tab === "settings" ? (
      <form className="form wide card" onSubmit={save}>
        <div className="form-grid">
          <label>
            <Hint text="Сколько человек попадает в часовой пост и на сайт: топ по доходности и отдельно топ по просадке, от 1 до 50.">
              Участников в посте (1–50)
            </Hint>
            <input
              type="number"
              min={1}
              max={50}
              value={form.top_n}
              onChange={(e) => patch("top_n", Number(e.target.value))}
            />
            {errors.top_n ? <span className="field-err">{errors.top_n}</span> : null}
          </label>
          <label>
            <Hint text="Порог входа в зачёт сегодняшнего дня. Регистрация на сайте разовая, но депозит должен быть не меньше этой суммы именно за текущие сутки UTC+2.">
              Мин. депозит дня, $
            </Hint>
            <input
              type="number"
              min={1}
              step={1}
              value={form.min_day_deposit}
              onChange={(e) => patch("min_day_deposit", Number(e.target.value))}
            />
            {errors.min_day_deposit ? (
              <span className="field-err">{errors.min_day_deposit}</span>
            ) : null}
          </label>
          <label>
            <Hint text="В часовой пост по доходности попадают только те, у кого % не ниже этого порога. 0 — фильтр выключен, берём просто топ.">
              Мин. доходность в посте, %
            </Hint>
            <input
              type="number"
              min={0}
              step={0.1}
              value={form.min_return_pct}
              onChange={(e) => patch("min_return_pct", Number(e.target.value))}
            />
            {errors.min_return_pct ? <span className="field-err">{errors.min_return_pct}</span> : null}
          </label>
          <label>
            <Hint text="Как часто бот сам шлёт живой рейтинг в группу. 60 = каждый час, 120 = каждые два часа. Итоги дня уходят отдельно после полуночи UTC+2.">
              Пост в Telegram каждые, мин
            </Hint>
            <input
              type="number"
              min={15}
              max={180}
              value={form.publish_interval_minutes}
              onChange={(e) => patch("publish_interval_minutes", Number(e.target.value))}
            />
            {errors.publish_interval_minutes ? (
              <span className="field-err">{errors.publish_interval_minutes}</span>
            ) : null}
          </label>
          <label>
            <Hint text="Сколько призовых мест в каждой номинации при закрытии дня. Не путать с «участников в посте» — это только призы.">
              Призовых мест
            </Hint>
            <input
              type="number"
              min={1}
              max={10}
              value={form.prize_places}
              onChange={(e) => patch("prize_places", Number(e.target.value))}
            />
            {errors.prize_places ? <span className="field-err">{errors.prize_places}</span> : null}
          </label>
          <label>
            <Hint text="Максимум выплаты за просадку на одно место. Если 15% от убытка больше капа — платим кап, не больше.">
              Кап компенсации просадки, $
            </Hint>
            <input
              type="number"
              min={0}
              value={form.loss_comp_cap}
              onChange={(e) => patch("loss_comp_cap", Number(e.target.value))}
            />
            {errors.loss_comp_cap ? <span className="field-err">{errors.loss_comp_cap}</span> : null}
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={form.require_trade}
              onChange={(e) => patch("require_trade", e.target.checked)}
            />
            <Hint text="Если включено, в зачёт не попадёт тот, кто только задепозитил и не сделал ни одной сделки за сутки.">
              Нужна хотя бы одна сделка за день
            </Hint>
          </label>
        </div>

        <h3>
          <Hint text="Фиксированные суммы приза за номинацию «доходность». 1 место — максимальный %, затем 2, 3 и дальше.">
            Призы доходности, $
          </Hint>
        </h3>
        <div className="form-grid">
          {places.map((i) => (
            <label key={`y${i}`}>
              <Hint text={`Сколько долларов получает ${i + 1} место в номинации доходность при закрытии дня.`}>
                {i + 1} место
              </Hint>
              <input
                type="number"
                min={0}
                value={form.prize_yield[i] ?? 0}
                onChange={(e) => {
                  const copy = [...form.prize_yield];
                  copy[i] = Number(e.target.value);
                  patch("prize_yield", copy);
                }}
              />
              {errors[`y${i}`] ? <span className="field-err">{errors[`y${i}`]}</span> : null}
            </label>
          ))}
        </div>

        <h3>
          <Hint text="Процент от торгового убытка, который компенсируем в номинации «просадка». Считается от PnL, потом режется капом. Кто уже в призах доходности — сюда не берётся.">
            Компенсация просадки, %
          </Hint>
        </h3>
        <div className="form-grid">
          {places.map((i) => (
            <label key={`p${i}`}>
              <Hint text={`Какой процент убытка компенсируем ${i + 1} месту в номинации просадка.`}>
                {i + 1} место
              </Hint>
              <input
                type="number"
                min={0}
                max={100}
                step={0.1}
                value={form.prize_loss_pct[i] ?? 0}
                onChange={(e) => {
                  const copy = [...form.prize_loss_pct];
                  copy[i] = Number(e.target.value);
                  patch("prize_loss_pct", copy);
                }}
              />
              {errors[`p${i}`] ? <span className="field-err">{errors[`p${i}`]}</span> : null}
            </label>
          ))}
        </div>

        <h3>
          <Hint text="Живой рейтинг, который бот шлёт в группу по интервалу. Не итог дня.">
            Часовой пост
          </Hint>
        </h3>
        <p className="note">
          Плейсхолдеры: {"{day}"} {"{time}"} {"{site}"} {"{place}"} {"{uid}"} {"{name}"} {"{pct}"}{" "}
          {"{pnl}"}. HTML: b, i, u, s, code, pre, a. Превью обновляется сразу при правке шаблона.
        </p>
        <label>
          <Hint text="Первая строка часового сообщения. {day} — дата UTC+2, {time} — время снимка.">
            Шапка часового поста
          </Hint>
          <textarea rows={2} value={form.tg_hourly_header} onChange={(e) => patch("tg_hourly_header", e.target.value)} />
        </label>
        <div className="form-grid">
          <label>
            <Hint text="Заголовок блока с лидерами по %. Используется и в часовом посте, и в итогах.">
              Заголовок доходности
            </Hint>
            <input value={form.tg_yield_title} onChange={(e) => patch("tg_yield_title", e.target.value)} />
          </label>
          <label>
            <Hint text="Заголовок блока с максимальной просадкой. И в часовом посте, и в итогах.">
              Заголовок просадки
            </Hint>
            <input value={form.tg_loss_title} onChange={(e) => patch("tg_loss_title", e.target.value)} />
          </label>
        </div>
        <label>
          <Hint text="Одна строка списка доходности. {place} место, {uid}, {name}, {pct}, {pnl}.">
            Строка доходности
          </Hint>
          <input value={form.tg_yield_row} onChange={(e) => patch("tg_yield_row", e.target.value)} />
        </label>
        <label>
          <Hint text="Одна строка списка просадки в часовом посте. Те же плейсхолдеры: place, uid, name, pct, pnl.">
            Строка просадки
          </Hint>
          <input value={form.tg_loss_row} onChange={(e) => patch("tg_loss_row", e.target.value)} />
        </label>
        <div className="form-grid">
          <label>
            <Hint text="Текст, если за день никто не попал в топ доходности.">
              Пустая доходность
            </Hint>
            <input value={form.tg_yield_empty} onChange={(e) => patch("tg_yield_empty", e.target.value)} />
          </label>
          <label>
            <Hint text="Текст, если никто не в минусе — блока просадки не из кого собрать.">
              Пустая просадка
            </Hint>
            <input value={form.tg_loss_empty} onChange={(e) => patch("tg_loss_empty", e.target.value)} />
          </label>
        </div>
        <label>
          <Hint text="Последние строки любого поста. {site} — ссылка на сайт или архив дня.">
            Подвал
          </Hint>
          <textarea rows={2} value={form.tg_footer} onChange={(e) => patch("tg_footer", e.target.value)} />
        </label>
        <div className="preview-box">
          {hourlyErrors.length ? (
            <ul className="err">
              {hourlyErrors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          ) : hourlyText ? (
            <p className="ok">Часовой пост: HTML корректный</p>
          ) : (
            <p className="note">Ждём данные рейтинга…</p>
          )}
          <div
            className="preview tg-preview"
            dangerouslySetInnerHTML={{ __html: toPreviewHtml(hourlyText) }}
          />
        </div>

        <h3>
          <Hint text="Сообщение после 00:00 UTC+2, когда день уже закрыт. Призы и места, не живой топ.">
            Пост итогов дня
          </Hint>
        </h3>
        <label>
          <Hint text="Первая строка финального поста. {day} — закрытая дата.">
            Шапка итогов дня
          </Hint>
          <input value={form.tg_final_header} onChange={(e) => patch("tg_final_header", e.target.value)} />
        </label>
        <div className="form-grid">
          <label>
            <Hint text="Строка призового места по доходности. {prize} — сумма в долларах, {uid}, {place}.">
              Итог, строка доходности
            </Hint>
            <input value={form.tg_final_yield_row} onChange={(e) => patch("tg_final_yield_row", e.target.value)} />
          </label>
          <label>
            <Hint text="Строка компенсации просадки. {prize} — сумма выплаты, не процент.">
              Итог, строка просадки
            </Hint>
            <input value={form.tg_final_loss_row} onChange={(e) => patch("tg_final_loss_row", e.target.value)} />
          </label>
        </div>
        <div className="preview-box">
          <p className="note">
            {tgCtx?.final_source === "frozen"
              ? "Зафиксированный итог закрытого дня."
              : "Черновик: день ещё не закрыт, места посчитаны по текущему рейтингу."}
          </p>
          {finalErrors.length ? (
            <ul className="err">
              {finalErrors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          ) : finalText ? (
            <p className="ok">Итоги дня: HTML корректный</p>
          ) : (
            <p className="note">Ждём данные рейтинга…</p>
          )}
          <div
            className="preview tg-preview"
            dangerouslySetInnerHTML={{ __html: toPreviewHtml(finalText) }}
          />
        </div>

        <p className="note">Отправка в группу берёт уже сохранённые шаблоны. Сначала сохрани, если правил текст.</p>
        <div className="actions">
          <button className="cta" type="submit" disabled={Boolean(busy)}>
            {busy === "save" ? "Сохраняем…" : "Сохранить"}
          </button>
          <button className="cta ghost" type="button" onClick={() => void snapshot()} disabled={Boolean(busy)}>
            {busy === "snap" ? "Снимаем…" : "Снять снимки сейчас"}
          </button>
          <button className="cta ghost" type="button" onClick={() => void freeze()} disabled={Boolean(busy)}>
            {busy === "freeze" ? "Фиксируем…" : "Закрыть день"}
          </button>
          <button className="cta ghost" type="button" disabled={Boolean(busy)} onClick={() => void sendPost("hourly")}>
            {busy === "sendH" ? "Шлём…" : "Отправить часовой"}
          </button>
          <button className="cta ghost" type="button" disabled={Boolean(busy)} onClick={() => void sendPost("final")}>
            {busy === "sendF" ? "Шлём…" : "Отправить итоги"}
          </button>
        </div>
        {status ? <p className="ok">{status}</p> : null}
        {err ? <p className="err">{err}</p> : null}
      </form>
      ) : null}
    </main>
  );
}
