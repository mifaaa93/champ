"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiPath } from "@/lib/api";
import { telegramError } from "@/lib/telegramUser";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faFacebook,
  faTelegram,
  faVk,
  faWhatsapp,
  faXTwitter,
} from "@fortawesome/free-brands-svg-icons";
import { faEnvelope } from "@fortawesome/free-solid-svg-icons";
import "@/app/event.css";

type PrizeRow = { place: string; amount: number; suffix?: string };
type TopRow = {
  place: number;
  name: string;
  dep: number;
  pnl?: number;
  loss?: number;
  return_pct?: number;
  dummy?: boolean;
  is_you?: boolean;
  is_friend?: boolean;
};
type Activity = { name: string; action: string; rank?: number | null; extra?: string; time?: string; scope?: string };
type Neighbor = { rank: number; uid: number; name: string; dep: number; is_you: boolean; dummy?: boolean };
type MetricRow = { place: number; name: string; pct: number; pnl: number };
type Profile = {
  uid: number;
  name: string;
  rank: number;
  dep: number;
  balance?: number;
  pnl?: number;
  return_pct?: number;
  beaten: number;
  total: number;
  neighbors: Neighbor[];
  in_ranking?: boolean;
  need_deposit?: number;
  ranking_reason?: "need_deposit" | "waiting_result";
  rank_a?: number;
  rank_b?: number;
};
type EventData = {
  name: string;
  event_end: string;
  min_deposit?: number;
  prize_pool: number;
  prize_table: PrizeRow[];
  stats_players: number;
  top_visible?: number;
  stats_deposits?: number;
  telegram_channel_url: string;
  rami_url: string;
  rules: string[];
  activity: Activity[];
  top: TopRow[];
  top_a?: TopRow[];
  top_b?: TopRow[];
  show_a?: boolean;
  show_b?: boolean;
  metrics?: { day: string; yield: MetricRow[]; loss: MetricRow[] };
};

function money(n: number) {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) {
    const m = abs / 1_000_000;
    const s = m % 1 === 0 ? m.toFixed(0) : m.toFixed(1);
    return `${sign}$${s}M`;
  }
  return `${sign}$${Math.round(abs).toLocaleString("en-US")}`;
}

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function pct(n: number) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

function scopeLabel(scope?: string) {
  if (scope === "A") return " · доходность";
  if (scope === "B") return " · потери";
  return null;
}

function activityLine(act: Activity) {
  const scope = scopeLabel(act.scope);
  if (act.action === "обогнал" && act.extra) {
    return (
      <>
        <b>{act.name}</b> обогнал <b>{act.extra}</b>
        {act.rank ? <> и поднялся на <b>#{act.rank}</b></> : null}
        {scope}
      </>
    );
  }
  if (act.action === "поднялся на" && act.rank) {
    return (
      <>
        <b>{act.name}</b> поднялся на <b>#{act.rank}</b> место
        {scope}
      </>
    );
  }
  if (act.action === "занял место" && act.rank) {
    return (
      <>
        <b>{act.name}</b> занял <b>#{act.rank}</b> место
        {scope}
      </>
    );
  }
  if (act.action === "пополнил депозит на") {
    return (
      <>
        <b>{act.name}</b> пополнил депозит на {act.extra ? <b>{act.extra}</b> : null}
        {scope}
      </>
    );
  }
  return (
    <>
      <b>{act.name}</b> {act.action}{" "}
      {act.rank ? <b>#{act.rank}</b> : null}
      {act.extra ? <b> {act.extra}</b> : null}
      {scope}
    </>
  );
}

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((x: unknown) => (typeof x === "string" ? x : (x as { msg?: string }).msg))
      .filter(Boolean)
      .join("; ");
  }
  return "";
}

function HelpShots() {
  return (
    <div className="screenshots">
      <figure className="screenshot-ph">
        <img src="/help/step-profile.png" alt="Открой профиль в приложении" />
        <figcaption className="screenshot-cap">1. Открой профиль</figcaption>
      </figure>
      <figure className="screenshot-ph">
        <img src="/help/step-id.png" alt="Скопируй ID из профиля" />
        <figcaption className="screenshot-cap">2. Найди и скопируй ID</figcaption>
      </figure>
    </div>
  );
}

function RamiHelp({ url }: { url: string }) {
  const href = url || "https://t.me/rami_username";
  const label = href.replace(/^https?:\/\//, "");
  return (
    <p>
      Если тебе нужна моя помощь, напиши мне и я помогу тебе:{" "}
      <a className="help-link" href={href} target="_blank" rel="noreferrer">
        {label}
      </a>
    </p>
  );
}

export function EventHome() {
  const params = useSearchParams();
  const refUid = (params.get("ref") || "").replace(/\D/g, "");

  const [data, setData] = useState<EventData | null>(null);
  const [uid, setUid] = useState("");
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState<
    null | "format" | "missing" | "name" | "prizes" | "rules" | "share" | "need_deposit"
  >(null);
  const [regName, setRegName] = useState("");
  const [regTg, setRegTg] = useState("");
  const [regErr, setRegErr] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [invite, setInvite] = useState<{ name: string; rank: number; dep: number } | null>(null);
  const [clock, setClock] = useState({ d: "00", h: "00", m: "00", s: "00" });
  const [shareCopied, setShareCopied] = useState(false);
  const [lookupErr, setLookupErr] = useState("");
  const [board, setBoard] = useState<"A" | "B">("A");
  const loadController = useRef<AbortController | null>(null);
  const registering = useRef(false);

  const load = useCallback(async () => {
    loadController.current?.abort();
    const ctrl = new AbortController();
    loadController.current = ctrl;
    let saved = "";
    try {
      saved = window.localStorage.getItem("po_champ_uid") || "";
    } catch {
      saved = "";
    }
    const query = new URLSearchParams();
    if (/^\d{9,10}$/.test(saved)) query.set("uid", saved);
    if (/^\d{9,10}$/.test(refUid)) query.set("ref", refUid);
    const q = query.toString() ? `?${query.toString()}` : "";
    const res = await fetch(apiPath(`/public/event${q}`), { cache: "no-store", signal: ctrl.signal });
    if (!res.ok) throw new Error("event");
    const json = (await res.json()) as EventData & { you?: Profile | null };
    if (ctrl.signal.aborted) return;
    setData(json);
    setProfile(json.you?.uid ? json.you : null);
  }, []);

  useEffect(() => {
    document.documentElement.classList.add("po-root");
    document.body.classList.add("po-root");
    return () => {
      document.documentElement.classList.remove("po-root");
      document.body.classList.remove("po-root");
    };
  }, []);

  useEffect(() => {
    if (modal !== "name") return;
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") setModal(null);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [modal]);

  useEffect(() => {
    void load().catch(() => {});
    const id = window.setInterval(() => void load().catch(() => {}), 30000);
    return () => {
      loadController.current?.abort();
      window.clearInterval(id);
    };
  }, [load]);

  useEffect(() => {
    let saved = "";
    try {
      saved = window.localStorage.getItem("po_champ_uid") || "";
    } catch {
      saved = "";
    }
    if (!/^\d{9,10}$/.test(saved)) return;
    setUid(saved);
  }, []);

  useEffect(() => {
    if (!refUid || refUid.length < 9) return;
    void fetch(apiPath(`/public/event/invite/${refUid}`), { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (j?.name) setInvite({ name: j.name, rank: j.rank, dep: j.dep });
      })
      .catch(() => {});
  }, [refUid]);

  useEffect(() => {
    const iso = data?.event_end;
    if (!iso) return;
    const end = new Date(iso).getTime();
    const tick = () => {
      const diff = Math.max(0, end - Date.now());
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setClock({ d: pad(d), h: pad(h), m: pad(m), s: pad(s) });
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [data?.event_end]);

  const showA = data?.show_a !== false;
  const showB = data?.show_b !== false;
  const activeBoard: "A" | "B" = board === "B" && showB ? "B" : showA ? "A" : "B";

  const top3 = useMemo(() => {
    const t = activeBoard === "B" ? data?.top_b || [] : data?.top_a || data?.top || [];
    return {
      first: t.find((x) => x.place === 1),
      second: t.find((x) => x.place === 2),
      third: t.find((x) => x.place === 3),
      rest: t.filter((x) => x.place >= 4),
    };
  }, [data, activeBoard]);

  const rami = data?.rami_url || "https://t.me/rami_username";
  const channel = data?.telegram_channel_url || "https://t.me/your_channel";
  const minDep = data?.min_deposit || 50;
  const topLimit = data?.top_visible || 10;
  const shareUrl =
    typeof window !== "undefined" && profile ? `${window.location.origin}/?ref=${profile.uid}` : "";
  const shareRank =
    activeBoard === "B" ? profile?.rank_b || 0 : profile?.rank_a || 0;
  const shareText = profile
    ? `Я в чемпионате! Моё место ${activeBoard === "B" ? "по потерям" : "по доходности"}: ${profile.in_ranking === false || shareRank === 0 ? "пока вне этого топа" : `#${shareRank}`}, депозит: ${money(profile.dep)}. Сможешь обогнать?`
    : "";

  function rememberUid(value: string | number) {
    try {
      window.localStorage.setItem("po_champ_uid", String(value));
    } catch {
      /* private mode */
    }
  }

  async function applyProfile(you: Profile, status?: string, scroll = true) {
    setProfile(you);
    rememberUid(you.uid);
    setModal(status === "need_deposit" ? "need_deposit" : null);
    void load().catch(() => {});
    if (!scroll) return;
    requestAnimationFrame(() => {
      document.getElementById("result-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function searchUid(rawInput: string, scroll = true) {
    const raw = rawInput.trim();
    setLookupErr("");
    if (!/^\d{9,10}$/.test(raw)) {
      setModal("format");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(apiPath(`/public/event/lookup/${raw}`), { cache: "no-store" });
      const body = await res.json().catch(() => ({}));
      if (res.status === 400) {
        setModal("format");
        return;
      }
      if (!res.ok) {
        setLookupErr(detailText((body as { detail?: unknown }).detail) || "Не удалось проверить ID");
        return;
      }
      const st = (body as { status?: string; you?: Profile }).status;
      if (st === "not_in_base") {
        setModal("missing");
        return;
      }
      if (st === "need_name") {
        setRegName("");
        setRegTg("");
        setRegErr("");
        setModal("name");
        return;
      }
      const you = (body as { you?: Profile }).you;
      if ((st === "ok" || st === "need_deposit" || st === "waiting_result") && you) {
        await applyProfile(you, st, scroll);
        return;
      }
      setLookupErr("Не удалось найти результат. Попробуй ещё раз.");
    } catch {
      setLookupErr("Проверка временно недоступна. Попробуй ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  function search() {
    return searchUid(uid, true);
  }

  function goJoin() {
    const target = profile ? "result-section" : "join";
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "center" });
    if (!profile) {
      window.setTimeout(() => document.getElementById("join-uid")?.focus(), 450);
    }
  }

  async function registerName() {
    if (registering.current || busy) return;
    const name = regName.trim();
    const tgErr = telegramError(regTg, false);
    if (!name) {
      setRegErr("Введи имя");
      return;
    }
    if (tgErr) {
      setRegErr(tgErr);
      return;
    }
    setRegErr("");
    registering.current = true;
    setBusy(true);
    try {
      const res = await fetch(apiPath("/public/event/register"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          uid: Number(uid.trim()),
          nickname: name,
          telegram: regTg.trim(),
          website: "",
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.status === 404) {
        setModal("missing");
        return;
      }
      if (!res.ok) {
        setRegErr(detailText((body as { detail?: unknown }).detail) || "Не удалось сохранить");
        return;
      }
      const you = (body as { you?: Profile }).you;
      const st = (body as { status?: string }).status;
      if (you) {
        rememberUid(uid.trim());
        await applyProfile(you, st);
      }
    } catch {
      setRegErr("Не удалось сохранить. Попробуй ещё раз.");
    } finally {
      registering.current = false;
      setBusy(false);
    }
  }

  async function share() {
    if (!profile) return;
    setShareCopied(false);
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ title: data?.name || "Чемпионат", text: shareText, url: shareUrl });
        return;
      } catch (e) {
        if ((e as { name?: string }).name === "AbortError") return;
      }
    }
    setModal("share");
  }

  async function copyShareUrl() {
    const value = shareUrl;
    let copied = false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        copied = true;
      }
    } catch {
      copied = false;
    }
    if (!copied) {
      const area = document.createElement("textarea");
      area.value = value;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      copied = document.execCommand("copy");
      area.remove();
    }
    setShareCopied(copied);
    window.setTimeout(() => setShareCopied(false), 2500);
  }

  function card(row: TopRow | undefined, cls: string, rankText: string, crown: boolean) {
    if (!row) return null;
    const pnl = row.pnl || 0;
    const loss = row.loss || Math.max(0, -pnl);
    const onLoss = activeBoard === "B";
    return (
      <div className={`top-card ${cls}`}>
        {crown ? <div className="crown">👑</div> : null}
        <div className="avatar-wrapper">
          <div className="initials-avatar">{row.name.charAt(0).toUpperCase()}</div>
        </div>
        <div className="bot-name">{row.name}{row.is_you ? " · Это вы" : row.is_friend ? " · Это ваш друг" : ""}</div>
        <div className="bot-rank">{rankText}</div>
        <div className="bot-stats">
          <div className="stat-box">
            <div className="stat-label-small">Депозит</div>
            <div className="stat-val deposit">{money(row.dep)}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label-small">{onLoss ? "Потеря" : "Прибыль"}</div>
            <div className={`stat-val ${onLoss || pnl < 0 ? "loss" : "profit"}`}>
              {money(onLoss ? loss : pnl)}
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-label-small">Доходность</div>
            <div className={`stat-val ${(row.return_pct || 0) >= 0 ? "profit" : "loss"}`}>
              {pct(row.return_pct || 0)}
            </div>
          </div>
        </div>
      </div>
    );
  }

  const activity = data?.activity || [];
  const yRows = data?.metrics?.yield || [];
  const lRows = data?.metrics?.loss || [];
  const showMetrics = yRows.length > 0 || lRows.length > 0;

  return (
    <div className="po">
      <div className="live-indicator">
        <span className="dot" />
        LIVE • обновление каждые 30 сек
      </div>
      <div className="container">
        <header className="po-header">
          <div className="logo">⚡ {data?.name || "PO CHAMPIONSHIP"}</div>
          <div className="join-wrap">
            <button type="button" className="join-btn" onClick={goJoin}>
              Участвовать
            </button>
            {profile?.name ? <div className="join-hello">Привет, {profile.name}</div> : null}
          </div>
          <div className="prize-badge">ПРИЗОВОЙ ПУЛ: {money(data?.prize_pool || 0)}</div>
        </header>

        {invite ? (
          <div className="invite-banner">
            Тебя позвал <b>{invite.name}</b> · место #{invite.rank} · деп {money(invite.dep)}. Сможешь обогнать?
          </div>
        ) : null}

        <div className="countdown-section">
          <div className="countdown-label">До конца чемпионата осталось</div>
          <div className="countdown-sublabel">Время UTC+2 • вход от ${minDep} депозита за сезон</div>
          <div className="countdown-timer">
            <div className="countdown-item">
              <div className="countdown-value">{clock.d}</div>
              <div className="countdown-unit">Дней</div>
            </div>
            <div className="countdown-item">
              <div className="countdown-value">{clock.h}</div>
              <div className="countdown-unit">Часов</div>
            </div>
            <div className="countdown-item">
              <div className="countdown-value">{clock.m}</div>
              <div className="countdown-unit">Минут</div>
            </div>
            <div className="countdown-item">
              <div className="countdown-value">{clock.s}</div>
              <div className="countdown-unit">Секунд</div>
            </div>
          </div>
        </div>

        <div className="live-stats-bar">
          <div className="live-stat">
            <div className="live-stat-value">
              <span className="live-dot" />
              {(data?.stats_players || 0).toLocaleString("en-US")}
            </div>
            <div className="live-stat-label">Участников</div>
          </div>
          <div className="live-stat">
            <div className="live-stat-value" style={{ color: "var(--neon-purple)" }}>
              {money(data?.stats_deposits || 0)}
            </div>
            <div className="live-stat-label">Депозитов за сезон</div>
          </div>
          <div className="live-stat">
            <div className="live-stat-value" style={{ color: "var(--neon-gold)" }}>
              Топ-{topLimit}
            </div>
            <div className="live-stat-label">Глубина рейтинга</div>
          </div>
        </div>

        {activity.length ? (
          <div className="activity-feed">
            <div className="activity-header">
              <div className="activity-title">
                <span className="live-dot" />
                ПОСЛЕДНИЕ ДЕЙСТВИЯ
              </div>
              <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Живые события рейтинга</div>
            </div>
            <div className="activity-list">
              {activity.map((act, i) => (
                <div className="activity-item" key={`${act.name}-${act.action}-${i}`}>
                  <span className="activity-text">{activityLine(act)}</span>
                  <span className="activity-time">{act.time}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <h2 className="section-title">
          {activeBoard === "B" ? `ТОП-${topLimit} ПО ПОТЕРЯМ` : `ТОП-${topLimit} ПО ПРИБЫЛИ`}
        </h2>
        {showA && showB ? (
          <div className="board-switch">
            <button type="button" className={`board-tab${activeBoard === "A" ? " active-a" : ""}`} onClick={() => setBoard("A")}>
              Доходность %
            </button>
            <button type="button" className={`board-tab${activeBoard === "B" ? " active-b" : ""}`} onClick={() => setBoard("B")}>
              Потери $
            </button>
          </div>
        ) : null}
        <p className="board-note">
          {activeBoard === "B"
            ? "Номинация B: кто потерял больше. Компенсация считается от этой потери."
            : "Номинация A: максимальная сумма прибыли. Процент показывается дополнительно. В топ входят участники с депозитом сезона от $" + minDep + "."}
        </p>
        <div className="top3-grid">
          {card(top3.second, "second", "2 МЕСТО", false)}
          {card(top3.first, "first", "1 МЕСТО", true)}
          {card(top3.third, "third", "3 МЕСТО", false)}
        </div>
        <div className="rest-top-table">
          <div className="table-header">
            <div>Место</div>
            <div>Трейдер</div>
            <div style={{ textAlign: "right" }}>{activeBoard === "B" ? "Потеря" : "Прибыль"}</div>
            <div style={{ textAlign: "right" }}>Депозит</div>
            <div style={{ textAlign: "right" }}>Доходность</div>
          </div>
          {top3.rest.map((row) => (
            <div className="table-row" key={`${activeBoard}-${row.place}`}>
              <div className="row-rank">{row.place}</div>
              <div>
                <div className="row-name">
                  {row.name}{row.is_you ? " · Это вы" : row.is_friend ? " · Это ваш друг" : ""}
                </div>
              </div>
              <div className={`row-val ${activeBoard === "B" ? "loss" : (row.pnl || 0) >= 0 ? "profit" : "loss"}`}>
                {activeBoard === "B" ? money(row.loss || Math.max(0, -(row.pnl || 0))) : money(row.pnl || 0)}
              </div>
              <div className="row-val deposit">{money(row.dep)}</div>
              <div className={`row-val ${(row.return_pct || 0) >= 0 ? "profit" : "loss"}`}>
                {pct(row.return_pct || 0)}
              </div>
            </div>
          ))}
        </div>

        {showMetrics ? (
          <div className="metrics-grid">
            <div className="metrics-col">
              <h3>Доходность дня</h3>
              {yRows.length ? (
                yRows.map((r) => (
                  <div className="metrics-row" key={`y-${r.place}`}>
                    <span>#{r.place} {r.name}</span>
                    <span className="row-val profit">{pct(r.pct)} · {money(r.pnl)}</span>
                  </div>
                ))
              ) : (
                <p className="metrics-empty">Пока нет данных за сегодня</p>
              )}
            </div>
            <div className="metrics-col">
              <h3>Просадка дня</h3>
              {lRows.length ? (
                lRows.map((r) => (
                  <div className="metrics-row" key={`l-${r.place}`}>
                    <span>#{r.place} {r.name}</span>
                    <span className="row-val loss">{pct(r.pct)} · {money(r.pnl)}</span>
                  </div>
                ))
              ) : (
                <p className="metrics-empty">Пока нет данных за сегодня</p>
              )}
            </div>
          </div>
        ) : null}

        <div className="action-buttons">
          <a href={channel} target="_blank" rel="noreferrer" className="action-btn telegram">
            Telegram канал
          </a>
          <a href={rami} target="_blank" rel="noreferrer" className="action-btn rami">
            Написать Rami
          </a>
          <button type="button" className="action-btn prizes" onClick={() => setModal("prizes")}>
            <span className="btn-icon">🏆</span>
            Призы
          </button>
          <button type="button" className="action-btn rules" onClick={() => setModal("rules")}>
            <span className="btn-icon">📋</span>
            Правила
          </button>
          {profile ? (
            <button type="button" className="action-btn share" onClick={() => void share()}>
              <span className="btn-icon">🔗</span>
              Поделиться
            </button>
          ) : null}
        </div>

        <div className="search-section" id="join">
          <h2 className="section-title" style={{ marginBottom: 15, fontSize: 24 }}>
            НАЙДИ СЕБЯ В РЕЙТИНГЕ
          </h2>
          <p className="search-subtitle">
            Введи свой UID от Pocket Option, чтобы увидеть статистику и место в таблице. В рейтинг —
            депозит от ${minDep} за сезон.
          </p>
          <form
            className="search-wrapper"
            onSubmit={(e) => {
              e.preventDefault();
              void search();
            }}
          >
            <input
              id="join-uid"
              className="search-input"
              value={uid}
              onChange={(e) => setUid(e.target.value.replace(/\D/g, "").slice(0, 10))}
              placeholder="Введите ваш UID..."
              inputMode="numeric"
            />
            <button type="submit" className="search-btn" disabled={busy}>
              {busy ? "ПРОВЕРЯЕМ…" : "УЧАСТВОВАТЬ"}
            </button>
          </form>
          <p className="hint">* UID в Pocket Option состоит из 9–10 цифр.</p>
          {lookupErr ? <p className="hint" style={{ color: "#ff6b7d" }}>{lookupErr}</p> : null}
        </div>

        {profile ? (
          <div className="result-section" id="result-section">
            <div className="welcome-msg">
              Привет, <span>{profile.name}</span>! 👋
            </div>
            {profile.in_ranking === false && profile.ranking_reason === "need_deposit" ? (
              <div className="need-banner">
                Чтобы попасть в рейтинг сезона, нужен депозит от ${minDep} с начала таймера. Сейчас{" "}
                {money(profile.dep)}
                {profile.need_deposit ? `, осталось ${money(profile.need_deposit)}` : ""}.
              </div>
            ) : null}
            {profile.in_ranking === false && profile.ranking_reason !== "need_deposit" ? (
              <div className="need-banner">
                Депозит для участия внесён. Пока нет результата по доходности или потерям; место появится после расчёта.
              </div>
            ) : null}
            <div className="stats-card">
              <h3>Ваша статистика</h3>
              {showA ? (
                <div className="stat-row">
                  <span className="stat-label">Место по доходности</span>
                  <span className="stat-value" style={{ color: "var(--neon-green)" }}>
                    {profile.in_ranking === false || !profile.rank_a
                      ? "вне топа"
                      : `#${profile.rank_a}`}
                  </span>
                </div>
              ) : null}
              {showB ? (
                <div className="stat-row">
                  <span className="stat-label">Место по потерям</span>
                  <span className="stat-value loss">
                    {profile.in_ranking === false || !profile.rank_b ? "вне топа" : `#${profile.rank_b}`}
                  </span>
                </div>
              ) : null}
              <div className="stat-row">
                <span className="stat-label">UID</span>
                <span className="stat-value id">{profile.uid}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Депозит за сезон</span>
                <span className="stat-value deposit">{money(profile.dep)}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Баланс</span>
                <span className="stat-value deposit">{money(profile.balance || 0)}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Прибыль дня</span>
                <span className={`stat-value ${(profile.pnl || 0) >= 0 ? "profit" : "loss"}`}>
                  {money(profile.pnl || 0)}
                </span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Доходность дня</span>
                <span className={`stat-value ${(profile.return_pct || 0) >= 0 ? "profit" : "loss"}`}>
                  {pct(profile.return_pct || 0)}
                </span>
              </div>
            </div>
          </div>
        ) : null}

        <footer className="po-footer">
          <p>Закрытая лига. Сутки и снимок счёта — UTC+2. В рейтинг от ${minDep} за сезон.</p>
        </footer>
      </div>

      <div className={`modal-overlay${modal === "format" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal error" onClick={(e) => e.stopPropagation()}>
          <h2>ОШИБКА ФОРМАТА UID</h2>
          <p>
            Введённый UID не похож на идентификатор Pocket Option. Должен состоять из 9–10 цифр.
            Посмотри на скриншоты и перепроверь.
          </p>
          <HelpShots />
          <RamiHelp url={rami} />
          <button type="button" className="modal-btn danger" onClick={() => setModal(null)}>
            ПОНЯТНО
          </button>
        </div>
      </div>

      <div className={`modal-overlay${modal === "missing" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal error" onClick={(e) => e.stopPropagation()}>
          <h2>UID НЕ НАЙДЕН</h2>
          <p>
            К сожалению, твоего ID нет в моей базе, видимо ты зарегистрировался не правильно или
            скопировал свой ID не в том месте. Посмотри на скриншоты и перепроверь.
          </p>
          <HelpShots />
          <RamiHelp url={rami} />
          <button type="button" className="modal-btn danger" onClick={() => setModal(null)}>
            ПОНЯТНО
          </button>
        </div>
      </div>

      <div className={`modal-overlay${modal === "need_deposit" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <h2>НУЖЕН ДЕПОЗИТ ${minDep}</h2>
          <p>
            UID найден, но в рейтинг сезона попадают счета с депозитом от ${minDep} с начала таймера.
          </p>
          <button type="button" className="modal-btn" onClick={() => setModal(null)}>
            ПОНЯТНО
          </button>
        </div>
      </div>

      <div className={`modal-overlay${modal === "name" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal success" onClick={(e) => e.stopPropagation()}>
          <h2>ДОБРО ПОЖАЛОВАТЬ!</h2>
          <button type="button" className="modal-close" aria-label="Закрыть" onClick={() => setModal(null)}>×</button>
          <p>Ваш UID найден. Введите имя. Telegram можно не указывать: ссылка, @username или username.</p>
          <input
            className="modal-input"
            value={regName}
            onChange={(e) => setRegName(e.target.value.slice(0, 32))}
            onKeyDown={(e) => {
              if (e.key === "Enter") void registerName();
            }}
            placeholder="Ваше имя / Никнейм"
            autoFocus
          />
          <input
            className="modal-input"
            value={regTg}
            onChange={(e) => setRegTg(e.target.value.slice(0, 200))}
            onKeyDown={(e) => {
              if (e.key === "Enter") void registerName();
            }}
            placeholder="Telegram, необязательно"
          />
          {regErr ? <p className="err">{regErr}</p> : null}
          <button type="button" className="modal-btn" onClick={() => void registerName()} disabled={busy}>
            ЗАРЕГИСТРИРОВАТЬСЯ
          </button>
        </div>
      </div>

      <div className={`modal-overlay${modal === "prizes" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <h2>ПРИЗОВОЙ ФОНД</h2>
          <p>Призы выплачиваем мы. Распределение призового пула:</p>
          <div className="prize-list">
            {(data?.prize_table || []).map((p) => (
              <div className="prize-item" key={p.place}>
                <span className="prize-place">{p.place}</span>
                <span className="prize-amount">
                  {money(p.amount)}
                  {p.suffix ? ` ${p.suffix}` : ""}
                </span>
              </div>
            ))}
          </div>
          <button type="button" className="modal-btn" onClick={() => setModal(null)}>
            ЗАКРЫТЬ
          </button>
        </div>
      </div>

      <div className={`modal-overlay${modal === "rules" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <h2>ПРАВИЛА ЧЕМПИОНАТА</h2>
          <div className="rules-list">
            {(data?.rules || []).map((text, i) => (
              <div className="rule-item" key={i}>
                <span className="rule-number">{pad(i + 1)}</span>
                <span className="rule-text">{text}</span>
              </div>
            ))}
          </div>
          <button type="button" className="modal-btn" onClick={() => setModal(null)}>
            ПОНЯТНО
          </button>
        </div>
      </div>

      <div className={`modal-overlay${modal === "share" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <h2>Поделиться</h2>
          <p>Отправь ссылку другу — он увидит твоё место и сможет соревноваться с тобой.</p>
          <div className="share-link-box">
            <label htmlFor="share-url">Ссылка приглашения</label>
            <div className="share-link-row">
              <input id="share-url" value={shareUrl} readOnly onFocus={(e) => e.currentTarget.select()} />
              <button type="button" onClick={() => void copyShareUrl()}>
                {shareCopied ? "Скопировано" : "Копировать"}
              </button>
            </div>
          </div>
          <div className="share-sheet">
            <a
              className="share-telegram"
              href={`https://t.me/share/url?url=${encodeURIComponent(shareUrl)}&text=${encodeURIComponent(shareText)}`}
              target="_blank"
              rel="noreferrer"
            >
              <FontAwesomeIcon icon={faTelegram} aria-hidden="true" /> Telegram
            </a>
            <a
              className="share-whatsapp"
              href={`https://wa.me/?text=${encodeURIComponent(`${shareText} ${shareUrl}`)}`}
              target="_blank"
              rel="noreferrer"
            >
              <FontAwesomeIcon icon={faWhatsapp} aria-hidden="true" /> WhatsApp
            </a>
            <a className="share-vk" href={`https://vk.com/share.php?url=${encodeURIComponent(shareUrl)}&title=${encodeURIComponent(shareText)}`} target="_blank" rel="noreferrer">
              <FontAwesomeIcon icon={faVk} aria-hidden="true" /> VK
            </a>
            <a className="share-facebook" href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`} target="_blank" rel="noreferrer">
              <FontAwesomeIcon icon={faFacebook} aria-hidden="true" /> Facebook
            </a>
            <a className="share-x" href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(shareText)}&url=${encodeURIComponent(shareUrl)}`} target="_blank" rel="noreferrer">
              <FontAwesomeIcon icon={faXTwitter} aria-hidden="true" /> X / Twitter
            </a>
            <a className="share-email" href={`mailto:?subject=${encodeURIComponent(data?.name || "Чемпионат")}&body=${encodeURIComponent(`${shareText}\n${shareUrl}`)}`}>
              <FontAwesomeIcon icon={faEnvelope} aria-hidden="true" /> Email
            </a>
          </div>
          <button type="button" className="modal-btn" onClick={() => setModal(null)}>
            ЗАКРЫТЬ
          </button>
        </div>
      </div>
    </div>
  );
}
