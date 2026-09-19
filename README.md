# HugCollect Bot 🤗

Telegram-бот с интерфейсом в стиле референсов: профиль, меню, подтверждение,
шуточный прогресс-бар, история и промокоды.

Важно: «обнимашки» виртуальные. Бот не отправляет сообщения указанному
пользователю. В проекте сохраняется только локальная история действий.

## Локальный запуск

1. Установи Python.
2. Создай бота через `@BotFather`.
3. Получи токен.
4. В терминале:

Windows PowerShell:
```powershell
$env:BOT_TOKEN="ТОКЕН_БОТА"
python bot.py
```

## Бесплатный хостинг на Render

1. Загрузи эту папку в GitHub.
2. На Render создай **New → Web Service**.
3. Подключи GitHub-репозиторий.
4. Build Command:
   `pip install -r requirements.txt`
5. Start Command:
   `python bot.py`
6. План: **Free**.
7. В Environment Variables добавь:
   - `BOT_TOKEN` = токен от BotFather
   - `SUPPORT_USERNAME` = твой Telegram username, например `@myname`
8. Нажми Deploy.

Когда Render выдаст адрес вида `https://....onrender.com`, приложение
само использует его как webhook через `RENDER_EXTERNAL_URL`.

### Важное ограничение Render Free

Free Web Service может выключаться после периода без входящих HTTP-запросов.
После нового запроса Render запускает сервис снова. Локальные файлы также
не являются постоянным хранилищем, поэтому SQLite в этой демо-версии может
сброситься после перезапуска/redeploy.

Для постоянных профилей позже лучше подключить PostgreSQL.

## Структура

```text
HugCollectBot/
├── bot.py
├── requirements.txt
├── render.yaml
├── README.md
└── assets/
    ├── profile_banner.png
    └── menu_banner.png
```
