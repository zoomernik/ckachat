# Telegram Video Bot (YouTube / VK / Instagram)

Бот принимает ссылку на видео, определяет платформу и отправляет видео прямо в Telegram.

## Что умеет
- Принимает ссылку обычным сообщением.
- Определяет платформу: YouTube, VK, Instagram.
- Скачивает видео через `yt-dlp`.
- Отправляет видео в чат как `sendVideo` (streaming).

## Локальный запуск
```powershell
cd C:\Users\pusho\Desktop\ckachat
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
# укажи токен в .env
python bot.py
```

## Docker запуск
```bash
docker build -t ckachat-bot .
docker run --env TELEGRAM_BOT_TOKEN=your_token_here ckachat-bot
```

## Настройка
1. Создай бота через `@BotFather` и получи токен.
2. Передай переменную окружения `TELEGRAM_BOT_TOKEN`.

## Использование
- Отправь боту ссылку на видео (YouTube / VK / Instagram).
- Бот обработает ссылку и пришлет видео в чат.

## Важно
- Некоторые ссылки могут быть недоступны из-за ограничений самой платформы.
- Для надежной отправки стоит держать итоговый файл до ~48 MB (настроено в коде).
