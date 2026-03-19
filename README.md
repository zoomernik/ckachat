# Telegram Video Bot (YouTube / VK / Instagram)

Бот принимает ссылку на видео, определяет платформу и отправляет видео прямо в Telegram.

## Что умеет
- Принимает ссылку обычным сообщением.
- Определяет платформу: YouTube, VK, Instagram.
- Скачивает видео через `yt-dlp`.
- Отправляет видео в чат как `sendVideo` (streaming).

## Установка
```powershell
cd C:\Users\pusho\Desktop\ckachat
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка
1. Создай бота через `@BotFather` и получи токен.
2. Создай файл `.env` на основе шаблона:
```powershell
Copy-Item .env.example .env
```
3. В `.env` укажи:
```env
TELEGRAM_BOT_TOKEN=твой_токен
```

## Запуск
```powershell
python bot.py
```

## Использование
- Отправь боту ссылку на видео (YouTube / VK / Instagram).
- Бот обработает ссылку и пришлет видео в чат.

## Важно
- Некоторые ссылки могут быть недоступны из-за ограничений самой платформы.
- Для надежной отправки стоит держать итоговый файл до ~48 MB (настроено в коде).
