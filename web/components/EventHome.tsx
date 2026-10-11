"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiPath } from "@/lib/api";
import "@/app/event.css";

type PrizeRow = { place: string; amount: number; suffix?: string };
type TopRow = { place: number; name: string; dep: number; turn: number };
type Activity = { name: string; action: string; rank?: number | null; extra?: string; time?: string };
type Neighbor = { rank: number; uid: number; name: string; dep: number; is_you: boolean };
type Profile = {
  uid: number;
  name: string;
  rank: number;
  dep: number;
  turn: number;
  beaten: number;
  total: number;
  neighbors: Neighbor[];
};
type EventData = {
  name: string;
  event_end: string;
  prize_pool: number;
  prize_table: PrizeRow[];
  stats_players: number;
  stats_turnover: number;
  telegram_channel_url: string;
  rami_url: string;
  rules: string[];
  activity: Activity[];
  top: TopRow[];
};

function money(n: number) {
  if (Math.abs(n) >= 1_000_000) {
    const m = n / 1_000_000;
    const s = m % 1 === 0 ? m.toFixed(0) : m.toFixed(1);
    return `$${s}M`;
  }
  return `$${Math.round(n).toLocaleString("en-US")}`;
}

function pad(n: number) {
  return String(n).padStart(2, "0");
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
    null | "format" | "missing" | "name" | "prizes" | "rules" | "share"
  >(null);
  const [regName, setRegName] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [invite, setInvite] = useState<{ name: string; rank: number; dep: number } | null>(null);
  const [clock, setClock] = useState({ d: "00", h: "00", m: "00", s: "00" });
  const [shareCopied, setShareCopied] = useState(false);
  const [lookupErr, setLookupErr] = useState("");

  const load = useCallback(async () => {
    const res = await fetch(apiPath("/public/event"), { cache: "no-store" });
    if (!res.ok) throw new Error("event");
    setData((await res.json()) as EventData);
  }, []);

  useEffect(() => {
    void load().catch(() => setData(null));
  }, [load]);

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

  const top3 = useMemo(() => {
    const t = data?.top || [];
    return {
      first: t.find((x) => x.place === 1),
      second: t.find((x) => x.place === 2),
      third: t.find((x) => x.place === 3),
      rest: t.filter((x) => x.place >= 4),
    };
  }, [data]);

  const rami = data?.rami_url || "https://t.me/rami_username";
  const channel = data?.telegram_channel_url || "https://t.me/your_channel";
  const shareUrl =
    typeof window !== "undefined" && profile
      ? `${window.location.origin}/?ref=${profile.uid}`
      : "";
  const shareText = profile
    ? `Я в турнире! Моё место: #${profile.rank}, депозит: ${money(profile.dep)}. Сможешь обогнать?`
    : "";

  async function applyProfile(you: Profile) {
    setProfile(you);
    setModal(null);
    requestAnimationFrame(() => {
      document.getElementById("result-section")?.scrollIntoView({ behavior: "smooth" });
    });
  }

  async function search() {
    const raw = uid.trim();
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
        setModal("name");
        return;
      }
      if (st === "ok" && (body as { you?: Profile }).you) {
        await applyProfile((body as { you: Profile }).you);
      }
    } catch {
      setLookupErr("Проверка временно недоступна. Попробуй ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  async function registerName() {
    const name = regName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const res = await fetch(apiPath("/public/event/register"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid: Number(uid.trim()), nickname: name, website: "" }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.status === 404) {
        setModal("missing");
        return;
      }
      if (!res.ok) {
        setLookupErr(detailText((body as { detail?: unknown }).detail) || "Не удалось сохранить имя");
        setModal(null);
        return;
      }
      const you = (body as { you?: Profile }).you;
      if (you) await applyProfile(you);
    } catch {
      setLookupErr("Не удалось сохранить имя. Попробуй ещё раз.");
      setModal(null);
    } finally {
      setBusy(false);
    }
  }

  async function share() {
    if (!profile) return;
    setShareCopied(false);
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ title: data?.name || "Турнир", text: shareText, url: shareUrl });
        return;
      } catch (e) {
        if ((e as { name?: string }).name === "AbortError") return;
      }
    }
    setModal("share");
  }

  function card(row: TopRow | undefined, cls: string, medal: string, rankText: string, crown: boolean) {
    if (!row) return null;
    return (
      <div className={`top-card ${cls}`}>
        {crown ? <div className="crown">👑</div> : null}
        <div className="avatar-wrapper">
          <div className="initials-avatar">{row.name.charAt(0).toUpperCase()}</div>
        </div>
        <div className="bot-name">
          {medal ? <span className="medal-badge">{medal}</span> : null}
          {row.name}
        </div>
        <div className="bot-rank">{rankText}</div>
        <div className="bot-stats">
          <div className="stat-box">
            <div className="stat-label-small">Деп</div>
            <div className="stat-val">{money(row.dep)}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label-small">Оборот</div>
            <div className="stat-val">{money(row.turn)}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="po">
      <div className="container">
        <header className="po-header">
          <div className="logo">⚡ {data?.name || "PO TOURNAMENT"}</div>
          <div className="prize-badge">ПРИЗОВОЙ ФОНД: {money(data?.prize_pool || 0)}</div>
        </header>

        {invite ? (
          <div className="invite-banner">
            Тебя позвал <b>{invite.name}</b> · место #{invite.rank} · деп {money(invite.dep)}. Сможешь обогнать?
          </div>
        ) : null}

        <div className="countdown-section">
          <div className="countdown-label">⏰ До конца турнира осталось</div>
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
              {money(data?.stats_turnover || 0)}
            </div>
            <div className="live-stat-label">Общий оборот</div>
          </div>
          <div className="live-stat">
            <div className="live-stat-value" style={{ color: "var(--neon-gold)" }}>
              {money(data?.prize_pool || 0)}
            </div>
            <div className="live-stat-label">Призовой фонд</div>
          </div>
        </div>

        <div className="activity-feed">
          <div className="activity-header">
            <div className="activity-title">
              <span className="live-dot" />
              ПОСЛЕДНИЕ ДЕЙСТВИЯ
            </div>
            <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Обновляется в реальном времени</div>
          </div>
          <div className="activity-list">
            {(data?.activity || []).slice(0, 5).map((act, i) => (
              <div className="activity-item" key={`${act.name}-${i}`}>
                <span className="activity-avatar">👤</span>
                <span className="activity-text">
                  <b>{act.name}</b> {act.action}{" "}
                  {act.rank ? (
                    <>
                      <b>#{act.rank}</b> место
                    </>
                  ) : null}
                  {act.extra ? <b> {act.extra}</b> : null}
                </span>
                <span className="activity-time">{act.time}</span>
              </div>
            ))}
          </div>
        </div>

        <h2 className="section-title">🔥 ЭЛИТА СЕТИ: ТОП-10 ЛИДОВ СЕЗОНА</h2>
        <div className="top3-grid">
          {card(top3.second, "second", "🥈", "2 МЕСТО", false)}
          {card(top3.first, "first", "", "1 МЕСТО", true)}
          {card(top3.third, "third", "🥉", "3 МЕСТО", false)}
        </div>
        <div className="rest-top10">
          {top3.rest.map((row) => (
            <div className="mini-card" key={row.place}>
              <div className="rank">{row.place}</div>
              <div className="info">
                <div className="name">{row.name}</div>
                <div className="id">ID: HIDDEN</div>
              </div>
              <div className="dep">{money(row.dep)}</div>
            </div>
          ))}
        </div>

        <div className="action-buttons">
          <a href={channel} target="_blank" rel="noreferrer" className="action-btn telegram">
            Телеграм канал
          </a>
          <a href={rami} target="_blank" rel="noreferrer" className="action-btn rami">
            <span className="btn-icon">💬</span>
            Написать Rami
          </a>
          <button type="button" className="action-btn prizes" onClick={() => setModal("prizes")}>
            <span className="btn-icon">🏆</span>
            Призы
          </button>
          <button type="button" className="action-btn rules" onClick={() => setModal("rules")}>
            <span className="btn-icon">📋</span>
            Правила турнира
          </button>
          {profile ? (
            <button type="button" className="action-btn share" onClick={() => void share()}>
              <span className="btn-icon">🔗</span>
              Поделиться результатом
            </button>
          ) : null}
        </div>

        <div className="search-section">
          <h2 className="section-title" style={{ marginBottom: 15 }}>
            НАЙДИ СЕБЯ В СИСТЕМЕ
          </h2>
          <p className="search-subtitle">
            Введи свой уникальный ID от Pocket Option, чтобы узнать свой ранг, статистику и место в
            турнирной таблице.
          </p>
          <div className="search-wrapper">
            <input
              className="search-input"
              value={uid}
              onChange={(e) => setUid(e.target.value.replace(/\D/g, "").slice(0, 10))}
              onKeyDown={(e) => {
                if (e.key === "Enter") void search();
              }}
              placeholder="Введите ваш ID..."
              inputMode="numeric"
            />
            <button type="button" className="search-btn" onClick={() => void search()} disabled={busy}>
              {busy ? "…" : "ПОИСК"}
            </button>
          </div>
          <p className="hint">* ID в Pocket Option состоит из 9–10 цифр.</p>
          {lookupErr ? <p className="hint" style={{ color: "#ff6b7d" }}>{lookupErr}</p> : null}
        </div>

        {profile ? (
          <div className="result-section" id="result-section">
            <div className="welcome-msg">
              Привет, <span>{profile.name}</span>! 👋
            </div>
            <div className="profile-grid">
              <div className="rank-card">
                <div className="rank-label">Ваш порядковый номер</div>
                <div className="rank-value">#{profile.rank}</div>
                <div className="rank-sub">
                  Вы опередили <b>{profile.beaten.toLocaleString("en-US")}</b> трейдеров
                </div>
              </div>
              <div className="stats-card">
                <div className="stat-row">
                  <span className="stat-label">Ваш ID</span>
                  <span className="stat-value id">{profile.uid}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Сумма депов</span>
                  <span className="stat-value dep">{money(profile.dep)}</span>
                </div>
                {profile.turn > 0 ? (
                  <div className="stat-row">
                    <span className="stat-label">Оборот (30 дней)</span>
                    <span className="stat-value turn">{money(profile.turn)}</span>
                  </div>
                ) : null}
              </div>
            </div>
            <div className="neighbors-block">
              <div className="neighbors-header">
                <h3>📊 ВАШЕ ОКРУЖЕНИЕ В РЕЙТИНГЕ</h3>
                <p>Ближайшие соседи по таблице (остальные скрыты системой)</p>
              </div>
              {profile.neighbors.map((n) => (
                <div className={n.is_you ? "neighbor-row current" : "neighbor-row"} key={`${n.rank}-${n.uid}`}>
                  <div className="n-rank">#{n.rank}</div>
                  <div className="n-name-block">
                    <div className="n-name">
                      {n.name}
                      {n.is_you ? " (ВЫ)" : ""}
                    </div>
                    <div className="n-id">{n.uid}</div>
                  </div>
                  <div className="n-dep">{money(n.dep)}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <footer className="po-footer">
          <p>Закрытая лига. Сутки и снимок счёта — UTC+2.</p>
        </footer>
      </div>

      <div className={`modal-overlay${modal === "format" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal error" onClick={(e) => e.stopPropagation()}>
          <h2>⚠️ ОШИБКА ФОРМАТА ID</h2>
          <p>
            Введённый ID не похож на идентификатор Pocket Option. ID должен состоять из 9–10 цифр.
            Посмотри на скриншоты и перепроверь, всё ли ты правильно сделал.
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
          <h2>⚠️ ID НЕ НАЙДЕН</h2>
          <p>
            К сожалению, твоего ID нет в моей базе, видимо ты зарегистрировался не правильно или
            скопировал свой ID не в том месте. Посмотри на скриншоты и перепроверь, всё ли ты
            правильно сделал.
          </p>
          <HelpShots />
          <RamiHelp url={rami} />
          <button type="button" className="modal-btn danger" onClick={() => setModal(null)}>
            ПОНЯТНО
          </button>
        </div>
      </div>

      <div className={`modal-overlay${modal === "name" ? " active" : ""}`}>
        <div className="modal success">
          <h2>👋 ДОБРО ПОЖАЛОВАТЬ!</h2>
          <p>
            Ваш ID верен, но вы еще не участвовали в этом сезоне. Введите ваше имя (или никнейм),
            чтобы мы могли вас идентифицировать для розыгрышей.
          </p>
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
          <button type="button" className="modal-btn" onClick={() => void registerName()} disabled={busy}>
            ЗАРЕГИСТРИРОВАТЬСЯ
          </button>
        </div>
      </div>

      <div className={`modal-overlay${modal === "prizes" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <h2 style={{ background: "linear-gradient(90deg, var(--neon-gold), var(--neon-orange))", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            🏆 ПРИЗОВОЙ ФОНД
          </h2>
          <p>Топ-10 участников сезона получают денежные призы:</p>
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
          <p style={{ fontSize: 12, color: "var(--text-dim)" }}>
            * Призы выплачиваются в течение 7 дней после окончания турнира
          </p>
          <button type="button" className="modal-btn" onClick={() => setModal(null)}>
            ЗАКРЫТЬ
          </button>
        </div>
      </div>

      <div className={`modal-overlay${modal === "rules" ? " active" : ""}`} onClick={() => setModal(null)}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <h2 style={{ background: "linear-gradient(90deg, var(--neon-cyan), var(--neon-purple))", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            📋 ПРАВИЛА ТУРНИРА
          </h2>
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
          <div className="share-sheet">
            <a
              href={`https://t.me/share/url?url=${encodeURIComponent(shareUrl)}&text=${encodeURIComponent(shareText)}`}
              target="_blank"
              rel="noreferrer"
            >
              Telegram
            </a>
            <a
              href={`https://wa.me/?text=${encodeURIComponent(`${shareText} ${shareUrl}`)}`}
              target="_blank"
              rel="noreferrer"
            >
              WhatsApp
            </a>
            <a
              href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`}
              target="_blank"
              rel="noreferrer"
            >
              Facebook
            </a>
            <a
              href={`fb-messenger://share/?link=${encodeURIComponent(shareUrl)}`}
            >
              Messenger
            </a>
            <button
              type="button"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(`${shareText} ${shareUrl}`);
                  setShareCopied(true);
                } catch {
                  setShareCopied(false);
                }
              }}
            >
              {shareCopied ? "Скопировано" : "Копировать"}
            </button>
          </div>
          <button type="button" className="modal-btn" onClick={() => setModal(null)}>
            ЗАКРЫТЬ
          </button>
        </div>
      </div>
    </div>
  );
}
