<div align="center">

# 🛠 Simple Craft Launcher — для разработчиков

**Техническая документация: архитектура, API ядра, переводы, сборка, правила участия**

![Лицензия: GPL-3.0](https://img.shields.io/badge/%D0%BB%D0%B8%D1%86%D0%B5%D0%BD%D0%B7%D0%B8%D1%8F-GPL--3.0-blue)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-yellow)

📖 Для игроков — [README.md](README.md)

</div>

---

## 📦 Требования

- **Python 3.11+**
- `customtkinter`, `pillow`, `requests`, `minecraft-launcher-lib >= 8` — обязательные
- `pypresence` — только для Discord Rich Presence (ставится отдельно; без неё лаунчер работает)

```bash
pip install customtkinter pillow requests minecraft-launcher-lib pypresence
```

Запуск из исходников:

```bash
python "Simple-Craft-Launcher.py"      # или двойной клик по build.bat
```

## 🗂 Структура

| Файл | Ответственность |
|---|---|
| `Simple-Craft-Launcher.py` | UI (customtkinter): главное окно, карточки сборок, темы, диалоги |
| `core/launcher_core.py` | игровая логика: установка, запуск, Java, бэкапы, моды, `.mrpack` |
| `core/i18n.py` | переводы; **ключом служит русская строка интерфейса** |
| `core/discord_rpc.py` | Rich Presence в отдельном потоке (необязательная зависимость) |
| `data/` | состояние: `settings.json`, `accounts.json`, `versions_cache.json`, лог |

Интерфейс — это класс `App` (главное окно) и диалоги: `CreateInstanceDialog`,
`InstanceSettingsDialog`, `AccountsDialog`, `GlobalSettingsDialog`, `ModsDialog`,
`BackupsDialog`, `AboutDialog`, `ConsoleWindow`, `InstanceCard`, `ProgressOverlay`.

## 🔌 Как UI общается с ядром

Прямых вызовов игровой логики из интерфейса нет — всё идёт через класс `CoreBridge`,
который загружает `core/launcher_core.py` через `importlib` (`_core_file()` учитывает и
распаковку PyInstaller). Это позволяет менять ядро, не трогая UI, и красиво падать,
если модуль недоступен.

```python
CoreBridge.install(inst, progress_cb)      # установка
CoreBridge.is_installed(inst)
CoreBridge.launch(inst, account)
CoreBridge.get_java_path(inst)
CoreBridge.memory_hint() / safe_ram_mb()
CoreBridge.export_instance(...) / import_instance(...) / export_mrpack(...)
CoreBridge.backup_saves(...) / list_backups(...) / restore_backup(...)
CoreBridge.modrinth_search(...) / modrinth_install(...) / modrinth_update_all(...)
CoreBridge.instances_dir() / disk_free_gb(path)
```

## 🧠 API ядра (`core/launcher_core.py`)

```python
install(instance_cfg, progress_cb) -> bool      # игра + загрузчик, с повтором при сбоях сети
is_installed(instance_cfg) -> bool
launch(instance_cfg, account) -> subprocess.Popen
get_java_path(cfg, version) / ensure_java_runtime(cfg, version)
fetch_versions() / latest_release() / offline_uuid(name)
instances_dir() / disk_free_gb(path) / best_install_root(preferred)
get_mc_dir(cfg) / shared_mc_dir()
export_instance(cfg, zip) / import_instance(zip, name)     # свой формат (лёгкий ZIP)
export_mrpack(cfg, path)                                   # формат Modrinth / Prism
backup_saves(cfg, reason) / list_backups(cfg) / restore_backup(cfg, path)
apply_game_language(cfg, ui_language) / game_language_code(lang)   # язык игры (options.txt)
modrinth_search(q, version, loader) / modrinth_best_version(project, version, loader)
modrinth_install(cfg, project_id, title) / modrinth_remove(cfg, id) / modrinth_update_all(cfg)
classify_crash(output_tail) / system_memory() / memory_hint() / safe_ram_mb()
set_logger(cb) / get_last_error()
```

### Формат конфига сборки (`instance.json`)

```json
{
  "name": "MyPack", "version": "1.21.4", "loader": "Fabric",
  "ram": 4096, "java_path": "", "jvm_args": "-XX:+UseG1GC",
  "created": "2026-01-01T12:00:00", "last_played": null, "play_time": 0,
  "server": ""                      // необязательно: адрес для «Присоединиться» из Discord
}
```

### Логика путей

- `instances_dir()` — папка сборок из `data/settings.json` (ключ `instances_dir`).
  Если ключ пуст, берётся папка лаунчера; если на её диске меньше 5 ГБ свободно —
  самый свободный диск (B: в приоритете). Так игра не уезжает на переполненный `C:`.
- `get_mc_dir(cfg)` — папка конкретной сборки; поддерживает переопределение через
  `game_dir` в конфиге сборки и «общий» режим (`isolation: "shared"`) → `<рядом>/minecraft`.
- Java-рантайм Mojang ставится внутрь сборки (`<сборка>/runtime/...`), а не в систему.

## 🌐 Переводы (`core/i18n.py`)

Принцип простой: **ключ перевода — сама русская строка**, поэтому непереведённый текст
остаётся русским и ничего не ломается.

```python
tr("Играть")                       # → "Play" при английском языке
tr("Сборка: {0}", name)            # подстановки через {0}, {1} …
i18n.set_language("en")            # применить язык
i18n.detect_system_language()      # язык системы (первый запуск)
```

Как добавить перевод:

1. Найти строку в UI и обернуть её: `tr("Новая надпись")`.
2. В `core/i18n.py` дописать в словарь `_EN`: `"Новая надпись": "New label",`.
3. Готово — переключение языка в «Настройках лаунчера» применяется сразу, без перезапуска.

Новый язык: добавить код в `LANGUAGES` (`{"ru": "Русский", "en": "English", "de": "Deutsch"}`)
и словарь рядом с `_EN`; неизвестные строки автоматически берутся из русского.

## 🎨 Темы и иконки

- Все цвета — в словаре `THEMES` (файл UI): `BG`, `PANEL`, `CARD`, `CARD_HOVER`, `CARD_SEL`,
  `CARD_BORDER`, `TEXT`, `MUTED`, `ACCENT`, `ACCENT_H`, `RED`, `GREEN`, `MODE` (`dark`/`light`).
- Активная тема — singleton `T`. Применение: `T.apply(name)`, перерисовка окна —
  `App._rebuild_ui()`; живой предпросмотр в настройках — `GlobalSettingsDialog._preview_theme`.
- Иконки кнопок: `load_icon("play.png", (18,18))` — **перекрашивает** силуэт в цвет темы
  (`T.ICON`), поэтому подходят однотонные PNG с прозрачным фоном; если файла нет,
  `load_icon_opt` вернёт `None` и кнопка станет текстовой.
- Цветные картинки (логотип) — только `load_image_icon(...)`: перекраска превратила бы
  логотип в однотонный силуэт.
- Иконка окна/панели задач: `App._set_window_icon()` собирает мультиразмерный `.ico`
  (16…256) из `assets/images/app_icon.ico` или `logo.png` в `data/cache/window_icon_<версия>.ico`
  и вызывает `iconbitmap`; плюс `SetCurrentProcessExplicitAppUserModelID` — иначе Windows
  показывает на панели задач значок `python.exe`.
- **Анимации загрузки**: `ProgressOverlay.busy(status)` — пока точный процент неизвестен,
  полоса «бежит» и в подписи крутятся точки; `busy_if_unknown(value, status)` переключается
  на точный прогресс, когда он появился (`App._apply_progress`). Кнопка «Обновить версии»
  на время загрузки списка показывает «Обновление версий…» и блокируется
  (`App._animate_refresh`).

## 🎫 Discord Rich Presence

1. `discord.com/developers/applications` → **New Application** (имя увидят друзья в статусе).
2. Скопировать **Application ID** из General Information.
3. «Настройки лаунчера» → **«ID приложения Discord»**, включить **Discord Rich Presence**.
4. Иконка статуса: Rich Presence → **Art Assets** → загрузить PNG с именем **`logo`**
   (лаунчер запрашивает именно этот ключ; без него статус просто без картинки).
5. Галочка **«Разрешить присоединение по Discord»** добавляет кнопку «Присоединиться»:
   лаунчер спросит адрес сервера и сохранит его в `instance.json` (поле `server`), после чего
   запуск идёт с `--quickPlayMultiplayer` (Minecraft 1.20+).

Реализация — `core/discord_rpc.py`: подключение в отдельном потоке, обновление раз в 15 секунд,
приём `ACTIVITY_JOIN`, аккуратное отключение. Если `pypresence` не установлен, класс просто
сообщает об этом в лог — остальной лаунчер не затрагивается.

## 🏗 Сборка EXE

```bat
build_exe.bat      →  dist\SimpleCraftLauncher.exe
```

Внутри: `pyinstaller --onefile --noconsole --icon=icon.ico --add-data "assets;assets"
--add-data "core;core"`. Папки `data/` и `instances/` создаются рядом с `.exe`
автоматически. Для сборки нужен `icon.ico` в корне проекта.

## 🗄 Ключи `data/settings.json`

`theme`, `ram`, `java_path`, `auto_java`, `jvm_args`, `close_on_launch`,
`selected_instance`, `language`, `language_auto`, `sync_game_language`, `discord_rpc`,
`discord_join`, `discord_client_id`, `force_launch`, `folder_chosen`, `instances_dir`,
`window_width`, `window_height`.

- `language_auto: true` — язык интерфейса берётся из системы (`detect_system_language()`:
  русская Windows → `ru`, любая другая → `en`). Выбор языка вручную выключает авто.
- `sync_game_language: true` — лаунчер прописывает язык игры в `options.txt` сборки
  (`ru` → `ru_ru`, `en` → `en_us`) при каждом запуске: игра на том же языке, что лаунчер.
- `force_launch: true` — разрешает запуск игры даже когда памяти/подкачки мало
  (иначе лаунчер спрашивает подтверждение и предупреждает о возможном вылете).

## ✅ Проверка изменений

Автотестов пока нет; минимальный набор перед коммитом:

```bash
python -m py_compile "Simple-Craft-Launcher.py" core/launcher_core.py core/i18n.py core/discord_rpc.py
python "Simple-Craft-Launcher.py"
```

Вручную стоит пройти: создание сборки → установка → запуск → окно «Моды» (поиск/установка) →
«Бэкапы миров» → импорт/экспорт сборки → переключение темы и языка. Всё, что делает ядро,
видно в окне «Консоль» и в `data/launcher.log` (пути установки, выбранная Java, ошибки сети).

## 🤝 Правила участия

- PR приветствуются: держите стиль кода (комментарии и docstring по-русски, отступы 4 пробела),
  видимые пользователю строки — через `tr(...)`.
- Не удаляйте уведомления об авторстве и файлы `LICENSE` / `NOTICE`.
- Для новых функций, затрагивающих пути, помните про главное правило проекта: **ничего
  тяжёлого не ставится на диск `C:` по умолчанию** — всё в папке сборок, выбранной владельцем.

---

## 📜 Лицензия, авторство и что делать, если кто-то нарушит копирайт

Проект распространяется под **GNU GPL-3.0**. Это значит, что любой, кто публикует лаунчер или
его изменённую версию, обязан:

1. оставить **открытым исходный код** своей версии;
2. сохранить **уведомления об авторских правах** — файлы `LICENSE` и `NOTICE`, заголовки
   исходников, имя автора в окне «О лаунчере»;
3. не выдавать изменённую версию за оригинальную.

### Пошагово, если авторство убрали или исходники закрыли

**1. Собери доказательства (сразу).** Сохрани ссылку на репозиторий/сборку, сделай скриншоты
страницы, скачай архив их кода, зафиксируй дату. Найди в их файлах характерные строки твоего
проекта — например `SimpleCraft`, `_set_window_icon`, `Игра ставится на диск лаунчера`,
`MODS_META_FILE = ".simplecraft-mods.json"`: это прямое доказательство копирования. Твоя
git-история с датами коммитов — самое сильное доказательство первенства.

**2. Напиши по-человечески.** В большинстве случаев хватает обычного сообщения: люди часто просто
не знают про GPL. Готовый текст:

> Здравствуйте! В вашем проекте используется код Simple Craft Launcher
> (github.com/artemiy207/Simple-Craft-Launcher), распространяемый под GNU GPL-3.0.
> По условиям этой лицензии нужно: сохранить файлы `LICENSE` и `NOTICE`, указать автора
> (Артемий «tyomik») и держать исходный код вашей версии открытым.
> Пожалуйста, приведите это в порядок в течение 7 дней. Если произошло недоразумение — ответьте,
> разберёмся.

**3. Если игнорируют — жалоба площадке.** На GitHub: кнопка **Report repository** →
**Copyright / DMCA** (форма: <https://github.com/contact/dmca>). Достаточно указать, что удалены
уведомления об авторских правах — репозиторий и релизы блокируются до разбирательства.
Для форумов, Discord-серверов и видео — их собственные формы «report copyright» либо письмо
хостингу с тем же текстом и ссылками.

**4. Что требовать нельзя.** Если кто-то сделал форк, честно указал автора и оставил код
открытым — это **не нарушение**: GPL именно для этого и создана. Требовать можно соблюдения
условий лицензии, но не удаления форка.

**5. Профилактика.** Не удаляй git-историю, указывай автора в `README`/`NOTICE`/шапках файлов,
оставляй в коде уникальные строки (имена функций и констант проекта) — тогда доказать
копирование и потребовать соблюдения лицензии легко.

> Это не юридическая консультация: если кто-то, например, **продаёт** твой лаунчер, имеет смысл
> обратиться к юристу по интеллектуальному праву. Но начинать всегда стоит с пунктов 1–3.

---

# 🇬🇧 English (for developers)

**Requirements:** Python 3.11+, `customtkinter`, `pillow`, `requests`,
`minecraft-launcher-lib >= 8`, optionally `pypresence` for Discord RPC.

**Layout:** `Simple-Craft-Launcher.py` (UI, customtkinter) · `core/launcher_core.py`
(install/launch/Java/backups/mods/.mrpack) · `core/i18n.py` (translations, the key is the Russian
source string) · `core/discord_rpc.py` (Rich Presence, optional) · `data/` (settings, accounts,
logs).

**Architecture:** the UI never calls the game logic directly — everything goes through
`CoreBridge`, which loads `core/launcher_core.py` with `importlib` (works from source and inside a
PyInstaller bundle). See the API list above; the same names are available on `CoreBridge`.

**Paths:** `instances_dir()` takes the `instances_dir` key from `data/settings.json`, falls back to
the launcher folder and then to the drive with the most free space (the project rule: nothing heavy
goes to `C:` by default). `get_mc_dir()` accepts a per-instance `game_dir`.

**Adding a translation:** wrap the UI string with `tr("…")` (placeholders `tr("Instance: {0}", n)`)
and add `"Russian source": "English text"` to `_EN` in `core/i18n.py`; missing entries fall back to
Russian. A new language = a new dict plus an entry in `LANGUAGES`.

**Themes:** colours live in `THEMES`, the active one is the `T` singleton (`T.apply(name)`, redraw
via `App._rebuild_ui()`). `load_icon()` tints monochrome icons to the theme colour (used for
buttons), `load_image_icon()` keeps the original colours (used for the logo).

**Discord:** create an application at `discord.com/developers/applications`, copy the
**Application ID** into the launcher settings, upload a Rich Presence art asset named **`logo`** if
you want the icon, and enable the optional “allow joining” switch for party/join support.

**Build:** `build_exe.bat` → `dist\SimpleCraftLauncher.exe`
(`pyinstaller --onefile --noconsole --icon=icon.ico --add-data "assets;assets"
--add-data "core;core"`).

**Checks:** no automated tests yet —
`python -m py_compile "Simple-Craft-Launcher.py" core/launcher_core.py core/i18n.py core/discord_rpc.py`
plus a manual smoke run (create instance → install → play → mods → backups → share/import → switch
theme and language). The Console window and `data/launcher.log` show everything the core does.

## 📜 License and enforcement (short version)

GPL-3.0: every distribution and every modified version must **keep the source open** and **keep the
authorship notices** (`LICENSE`, `NOTICE`, file headers, the author name in the About window).

If your authorship gets removed:

1. **Collect evidence** — link, screenshots, archived copy, date, and unique strings of your code
   found in theirs; your git history proves priority.
2. **Write to them politely** — in most cases a 7-day request is enough (see the Russian template
   above).
3. **If ignored — report to the platform** — GitHub: *Report repository* → *Copyright / DMCA*
   (<https://github.com/contact/dmca>).
4. A fork that keeps the notices and stays open is **not** a violation, and you cannot demand that
   it be taken down.


