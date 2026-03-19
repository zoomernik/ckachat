# Telegram Video Bot (YouTube / VK / Instagram / RuTube)

Production-ready Telegram bot на Python 3.11+, который:
- принимает ссылку на видео,
- получает метаданные через `yt-dlp`,
- предлагает качества,
- скачивает в очереди,
- отправляет обратно в Telegram (`reply_video` для mp4, иначе `reply_document`).

## Быстрый запуск для BotHost (если нельзя менять env)
1. Создай файл `token.txt` в корне проекта (рядом с `bot.py`).
2. Вставь в него токен бота одной строкой.
3. Перезалей проект и сделай `Clean rebuild`.
4. Убедись, что запущен только 1 инстанс.

Пример файла:
```text
123456:ABCDEF...
```

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
- `video_bot/config.py` - конфиг из env / token.txt
- `video_bot/yt_client.py` - извлечение метаданных/скачивание
- `video_bot/download_queue.py` - очередь задач
- `video_bot/telegram_handlers.py` - обработчики Telegram
- `video_bot/solver.py` - интеграция Deno/EJS solver
- `deploy/ckachat-bot.service` - systemd unit

## Docker
```bash
docker build -t ckachat-bot .
docker run --rm --env-file .env ckachat-bot
```
Проверка health:
```bash
curl http://127.0.0.1:8080/health
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
- Не коммить реальные токены в публичный репозиторий.
