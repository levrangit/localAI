
Локальный агент управления Firefox на Ubuntu.

## Архитектура

Firefox запускается с Remote Debugging на `127.0.0.1:9222`. Агент на Python слушает `127.0.0.1:8765` и работает с Firefox напрямую через CDP. Расширение Firefox не требуется для управления страницей.

Схема:

`команда → localAI:8765 → Firefox Remote Debugging:9222 → текущая вкладка`

## Запуск Firefox

Для профиля проекта используется `/home/leo/localAI/run/firefox-profile`.

```bash
env DISPLAY=:10 XAUTHORITY=/home/leo/.Xauthority XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \\
firefox --no-remote --new-instance \\
  --profile /home/leo/localAI/run/firefox-profile \\
  --remote-debugging-port 9222 \\
  --remote-allow-hosts 127.0.0.1 \\
  --remote-allow-origins http://127.0.0.1:9222 \\
  --new-window 'https://chat.deepseek.com/'
```

## Запуск агента

```bash
cd /home/leo/localAI
./scripts/run-agent.sh
```

Проверка:

```bash
curl http://127.0.0.1:8765/health
./scripts/browser-command.sh list_tabs
./scripts/browser-command.sh read_page
```

## Команды

- `list_tabs` — список всех открытых вкладок с постоянным номером `tab` внутри текущего запуска агента.
- `get_active_tab` — выбранная вкладка; можно передать `tab`, `target_id` или `url`.
- `read_page` — URL, заголовок и `body.innerText` страницы.
- Любую команду можно направить в конкретную вкладку через `"tab": 1`, `"tab": 2` и т. д.
- Команды выполняются параллельно: у агента пул из 8 рабочих потоков, поэтому операции в разных вкладках не блокируют друг друга.
- `read_selection` — текущее выделение.
- `find_text` — поиск текста в содержимом страницы с контекстом.
- `click` — поиск кнопки/ссылки/элемента с ролью button по тексту или aria-label и клик.
- `type_text` — ввод текста в активный input, textarea или contenteditable.
- `paste_text` — сейчас использует тот же DOM-механизм ввода, что и `type_text`.

## Ограничения

Номер `tab` назначается агентом при обнаружении новой вкладки и сохраняется до её закрытия или перезапуска агента. Закрытые вкладки удаляются из списка, новые получают следующий номер.

Пример CLI:

```bash
./scripts/browser-command.sh list_tabs
./scripts/browser-command.sh read_page --tab 1
./scripts/browser-command.sh read_page --tab 2
./scripts/browser-command.sh find_text --tab 3 "нужный текст"
./scripts/browser-command.sh type_text --tab 2 "текст для второй вкладки"
```

CDP `/json/list` не сообщает надёжный признак реально активной вкладки Firefox. Поэтому команда без `tab`, `target_id` или `url` работает с первой обнаруженной вкладкой. Позже можно добавить определение именно визуально активной вкладки через Firefox Remote Agent/BiDi.

## Git

Рабочая копия находится на `leoVM` в `/home/leo/localAI`, ветка `main`.
