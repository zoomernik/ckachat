# Telegram Video Bot (YouTube / VK / Instagram / RuTube)

Production-ready Telegram bot на Python 3.11+, который:
- принимает ссылку на видео,
- получает метаданные через `yt-dlp`,
- предлагает качества,
- скачивает в очереди,
- отправляет обратно в Telegram (`reply_video` для mp4, иначе `reply_document`).

## Возможности
- Модульная структура проекта (`video_bot/*`)
- Type hints, логирование, cleanup временных файлов
- 1 активная загрузка на пользователя
- Глобальный лимит параллельных скачиваний
- Лимиты размера и длительности
- Поддержка `ffmpeg` (для yt-dlp окружения)
- Поддержка Deno/EJS solver (опционально через env)
- Docker-ready и Linux/systemd-ready
- Retry/backoff и timeout на задачу скачивания
- Healthcheck endpoint: `GET /health` (по умолчанию `:8080`)

## Структура
- `bot.py` - entrypoint
- `video_bot/config.py` - конфиг из env
- `video_bot/yt_client.py` - извлечение метаданных/скачивание
- `video_bot/download_queue.py` - очередь задач
- `video_bot/telegram_handlers.py` - обработчики Telegram
- `video_bot/solver.py` - интеграция Deno/EJS solver
- `deploy/ckachat-bot.service` - systemd unit

## Локальный запуск
```powershell
cd C:\Users\pusho\Desktop\ckachat
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
# укажи TELEGRAM_BOT_TOKEN
python bot.py
```

## Docker
```bash
docker build -t ckachat-bot .
docker run --rm --env-file .env ckachat-bot
```
Проверка health:
```bash
curl http://127.0.0.1:8080/health
```

## Deno/EJS solver для YouTube (опционально)
Если используешь внешний solver-скрипт:
- `YOUTUBE_SOLVER_MODE=deno_ejs`
- `DENO_SOLVER_SCRIPT=/app/solver/solver.ts`

Скрипт должен печатать JSON в stdout:
```json
{
  "extractor_args": {"youtube": {"player_client": ["web"]}},
  "cookie_file": "/app/cookies.txt"
}
```

## systemd (VPS)
1. Создай пользователя и директорию проекта:
```bash
sudo useradd -r -s /usr/sbin/nologin video-bot || true
sudo mkdir -p /opt/ckachat
```
2. Скопируй проект в `/opt/ckachat`, создай `.env`, установи зависимости в `.venv`.
3. Установи unit:
```bash
sudo cp deploy/ckachat-bot.service /etc/systemd/system/ckachat-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now ckachat-bot
```
4. Логи:
```bash
journalctl -u ckachat-bot -f
```

## Важные переменные
Смотри `.env.example`:
- `MAX_PARALLEL_DOWNLOADS`
- `PER_USER_SINGLE_ACTIVE`
- `MAX_UPLOAD_MB`
- `MAX_DURATION_SECONDS`
- `YOUTUBE_SOLVER_MODE`
- `MAX_DOWNLOAD_ATTEMPTS`
- `RETRY_BACKOFF_SECONDS`
- `JOB_TIMEOUT_SECONDS`
- `HEALTHCHECK_PORT`

## Примечания
- Один и тот же токен нельзя запускать в нескольких процессах одновременно (иначе `409 Conflict`).
- Не коммить `.env` в репозиторий.
