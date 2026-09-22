# Чемпионат Pocket Option

Дневной чемпионат по трейдингу для партнёрского контура Pocket Option.

- Сайт: регистрация, живой рейтинг, правила, архив
- Worker: снимки Partners API, расчёт дня, freeze в 23:59 UTC+2
- Telegram: топ-7 каждый час (когда задан токен бота)

Сутки считаются по **UTC+2** (как календарь Partners API). Вход: регистрация на сайте + депозит за сегодня (по умолчанию от $50, настраивается). Вывод не дисквалифицирует, но снижает место в рейтинге доходности.

## Запуск

```bash
cp .env.example .env
# заполнить PARTNERS_TOKEN, PARTNERS_ID, ADMIN_TOKEN
# по желанию TG_BOT_TOKEN и TG_CHAT_ID

docker compose up --build
```

- Сайт: http://localhost:3000
- API: http://localhost:8000/health
- Админка: http://localhost:3000/admin (токен `ADMIN_TOKEN` из `.env`)

## Что настраивается без релиза

Через `/admin` (заголовок `X-Admin-Token`):

- `top_n` (сейчас 7)
- `min_day_deposit` (сейчас 50)
- призы доходности и % компенсации просадки
- кап компенсации
- интервал публикации

## Формула рейтинга

```
PnL = (balance_now − balance_start) − Δdeposits − Δbonuses
%   = PnL / basis × 100
```

`basis` = стартовый баланс дня, либо депозит дня если старт был 0.  
Вывод **не** прибавляется обратно — кэшаут роняет счёт.

## Тесты ядра

```bash
docker compose run --rm api pytest
```
