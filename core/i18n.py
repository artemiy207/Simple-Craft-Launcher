"""
i18n.py — локализация Simple Craft Launcher
===========================================
Ключом перевода служит сама русская строка интерфейса, поэтому непереведённая
строка просто остаётся русской (в коде нет искусственных ключей вида "btn.play").

    from i18n import tr, set_language, detect_system_language
    tr("Играть")                      # → "Play", если язык английский
    tr("Сборка «{0}» создана", name)  # подстановки через {0}, {1} …

Добавить перевод: дописать пару "русский текст": "English text" в _EN.
"""

import locale
import os

LANGUAGES = {
    "ru": "Русский",
    "en": "English",
}
DEFAULT_LANGUAGE = "ru"
_language = DEFAULT_LANGUAGE

# ─────────────────────────────────────────────────────────────
# СЛОВАРЬ АНГЛИЙСКОГО (ключ = русская строка интерфейса)
# ─────────────────────────────────────────────────────────────
_EN: dict[str, str] = {
    # ── кнопки и общие надписи ────────────────────────────────
    "Играть":                    "Play",
    "Остановить":                "Stop",
    "Игра идёт":                 "Game is running",
    "Установить":                "Install",
    "Установка...":              "Installing...",
    "Сохранить":                 "Save",
    "Отмена":                    "Cancel",
    "Создать":                   "Create",
    "Удалить":                   "Delete",
    "Переименовать":             "Rename",
    "Обновить":                  "Refresh",
    "Обновить версии":           "Refresh versions",
    "Открыть папку":             "Open folder",
    "Открыть mods":              "Open mods",
    "Открыть":                   "Open",
    "Выбрать":                   "Browse...",
    "Настройки":                 "Settings",
    "Настройки сборки":          "Instance settings",
    "Настройки лаунчера":        "Launcher settings",
    "Папки":                     "Folders",
    "Консоль":                   "Console",
    "Аккаунт":                   "Account",
    "Аккаунты":                  "Accounts",
    "Сборки":                    "Instances",
    "Сборка":                    "Instance",
    "Импорт сборки":             "Import instance",
    "Поделиться сборкой":        "Share instance",
    "Обновить все моды":         "Update all mods",
    "Моды":                      "Mods",
    "О лаунчере":                "About",
    "Поддержать автора":         "Support the author",
    "Копировать":                "Copy",
    "Закрыть":                   "Close",
    "Очистить":                  "Clear",
    "Да":                        "Yes",
    "Нет":                       "No",
    "Готово":                    "Done",
    "Ошибка":                    "Error",
    "Внимание":                  "Warning",
    "Все":                       "All",
    "Имя":                       "Name",
    "Версия":                    "Version",
    "Дата":                      "Date",
    "Загрузчик":                 "Loader",
    "Размер":                    "Size",
    "Статус":                    "Status",
    "Путь":                      "Path",
    "Язык":                      "Language",

    # ── сайдбар / карточки ────────────────────────────────────
    "Поиск сборок...":           "Search instances...",
    "Выбрать сборку для запуска":"Select an instance to play",
    "Выберите сборку":           "Select an instance",
    "Не установлена":            "Not installed",
    "Установлена":               "Installed",
    "Установлена ✓":             "Installed ✓",

    # ── настройки лаунчера ────────────────────────────────────
    "Тема оформления":           "Theme",
    "RAM по умолчанию (МБ)":     "Default RAM (MB)",
    "Глобальный путь к Java":    "Global Java path",
    "Аргументы JVM по умолчанию":"Default JVM arguments",
    "Папка сборок":              "Instances folder",
    "Сворачивать лаунчер при запуске игры": "Minimize launcher when the game starts",
    "Discord Rich Presence":     "Discord Rich Presence",
    "Разрешить присоединение по Discord": "Allow joining via Discord",
    "Скачивать нужную Java автоматически (если её нет в системе)":
        "Download the required Java automatically (if it is missing)",
    "Интерфейс переключается сразу, без перезапуска":
        "Switches instantly, no restart needed",
    "{0} тем • применяется сразу, без перезапуска":
        "{0} themes · applied instantly, no restart",
    "ID приложения Discord":     "Discord application ID",
    "Нужен для Rich Presence: discord.com/developers/applications → New Application → скопировать Application ID":
        "Required for Rich Presence: discord.com/developers/applications → New Application → copy Application ID",

    # ── первый запуск: выбор папки ────────────────────────────
    "Куда ставить сборки?":      "Where should instances be installed?",
    "«Да» — рядом с лаунчером:\n{0}\n\n«Нет» — выбрать другую папку\n«Отмена» — решить позже в «Настройках лаунчера»":
        "“Yes” — next to the launcher:\n{0}\n\n“No” — pick another folder\n"
        "“Cancel” — decide later in Launcher settings",
    "Папка для сборок Minecraft": "Minecraft instances folder",
    "Игра, моды, миры и Java будут храниться в этой папке.\n\n«Да» — рядом с лаунчером:\n{0}\n\n«Нет» — выбрать другую папку\n«Отмена» — решить позже в «Настройках лаунчера»":
        "The game, mods, worlds and Java will be stored in this folder.\n\n"
        "“Yes” — next to the launcher:\n{0}\n\n“No” — pick another folder\n"
        "“Cancel” — decide later in Launcher settings",

    # ── менеджер модов ────────────────────────────────────────
    "Моды · {0}":                "Mods · {0}",
    "Поиск мода, например sodium": "Search mods, e.g. sodium",
    "Найти":                     "Search",
    "Поиск на Modrinth...":      "Searching Modrinth...",
    "Версия {0} · загрузчик {1}": "Version {0} · loader {1}",
    "Ничего не найдено — проверьте интернет и версию сборки":
        "Nothing found — check your internet connection and instance version",
    "Найдено: {0}. {1}":         "Found: {0}. {1}",
    "{0} · загрузок: {1}":       "{0} · downloads: {1}",
    "Скачивание «{0}»...":       "Downloading “{0}”...",
    "Мод «{0}» установлен":      "Mod “{0}” installed",
    "Не удалось установить мод": "Could not install the mod",
    "Удалить мод «{0}»?":        "Delete mod “{0}”?",
    "Мод «{0}» удалён":          "Mod “{0}” deleted",
    "Не удалось удалить мод":    "Could not delete the mod",
    "Проверяю новые версии модов...": "Checking for mod updates...",
    "Обновлено модов: {0}, актуальных: {1}": "Mods updated: {0}, up to date: {1}",
    " · ошибок: {0}":            " · errors: {0}",
    "Установлено через менеджер модов: {0}": "Installed via the mod manager: {0}",
    "Пока пусто — найдите мод выше и нажмите «Установить»":
        "Nothing yet — find a mod above and press “Install”",
    "Обновить все моды":         "Update all mods",
    "Сборка Vanilla: моды не поддерживаются — смените загрузчик на Fabric/Forge в настройках сборки":
        "Vanilla instance: mods are not supported — switch the loader to Fabric/Forge "
        "in the instance settings",

    # ── бэкапы миров ──────────────────────────────────────────
    "Бэкапы миров":              "World backups",
    "Бэкапы миров · {0}":        "World backups · {0}",
    "Сделать бэкап сейчас":      "Back up now",
    "Восстановить":              "Restore",
    "Бэкапов пока нет — они создаются автоматически перед установкой, а также кнопкой ниже":
        "No backups yet — they are created automatically before installing, "
        "and by the button below",
    "Бэкапов: {0}. Хранятся последние 10 в папке сборки.":
        "Backups: {0}. The last 10 are kept in the instance folder.",
    "Делаю бэкап миров...":      "Backing up worlds...",
    "Восстанавливаю миры...":    "Restoring worlds...",
    "Миры восстановлены":        "Worlds restored",
    "Не получилось — смотрите «Консоль»": "Failed — see the Console",

    # ── обмен сборками ────────────────────────────────────────
    "Сохранить сборку в файл":   "Save instance to a file",
    "Архив сборки (этот лаунчер)": "Instance archive (this launcher)",
    "Модпак Modrinth/Prism (.mrpack)": "Modrinth/Prism modpack (.mrpack)",
    "Упаковка сборки...":        "Packing the instance...",
    "Выберите файл сборки":      "Choose an instance file",
    "Архивы сборок":             "Instance archives",

    # ── Discord ───────────────────────────────────────────────
    "Сборка: {0}":               "Instance: {0}",
    "Адрес сервера для присоединения (например play.example.com):":
        "Server address to join (e.g. play.example.com):",
    "Друг приглашает присоединиться.\n\nПодключиться к серверу {0}?":
        "A friend invites you to join.\n\nConnect to the server {0}?",

    # ── «О лаунчере» ──────────────────────────────────────────
    "Версия {0}":                "Version {0}",
    "Автор: {0}":                "Author: {0}",
    "Сборки, моды и Java хранятся в папке:":
        "Instances, mods and Java are stored in:",
    "Исходный код":              "Source code",
    "Связаться с автором":       "Contact the author",
    "Поддержать автора":         "Support the author",
    "Ссылки на поддержку автор ещё не указал.\nОн может вписать их в файл data/donations.json — перезапуск не нужен.":
        "The author has not added support links yet.\n"
        "They can be added in data/donations.json — no restart needed.",
    "Исходный код открыт: авторство и уведомление об авторских правах обязательно сохраняются при любом распространении и в любых изменённых версиях лаунчера (см. файлы LICENSE и NOTICE).":
        "The source code is open: authorship and copyright notices must be preserved "
        "in any distribution and in any modified version of the launcher "
        "(see LICENSE and NOTICE).",

    # ── диалоги и сообщения (вторая порция) ───────────────────
    "Ошибка окружения":         "Environment error",
    "Подготовка...":            "Preparing...",
    "Создание сборки":          "New instance",
    "Название":                 "Name",
    "Моя сборка":               "My instance",
    "Версия Minecraft":         "Minecraft version",
    "RAM (МБ)":                 "RAM (MB)",
    "RAM должен быть числом":   "RAM must be a number",
    "Введите название сборки":  "Enter an instance name",
    "Введите название":         "Enter a name",
    "Путь к Java (оставь пустым — авто)": "Java path (leave empty for auto)",
    "Аргументы JVM":            "JVM arguments",
    "Никнейм (offline)":        "Nickname (offline)",
    "+ Добавить":               "+ Add",
    "Удаление":                 "Delete",
    "Считаю доступную память...": "Checking available memory...",
    "Авто (из PATH)":           "Auto (from PATH)",
    "Добавить":                 "Add",
    "Выберите сборку для запуска": "Select an instance to play",
    "ИГРАТЬ":                   "PLAY",
    "Создайте новую сборку или измените поиск":
        "Create a new instance or change the search",
    "Новая сборка":             "New instance",
    "Ещё не запускалась":       "Never launched",
    "Новое название:":          "New name:",
    "Нельзя устанавливать во время игры": "Cannot install while the game is running",
    "Установка завершена!\nТеперь можно запускать игру.":
        "Installation complete!\nYou can start the game now.",
    "Игра не установлена — начинаю установку...":
        "The game is not installed — starting the installation...",
    "Мало памяти для запуска":  "Not enough memory to launch",
    "Игре не хватило памяти":   "The game ran out of memory",
    "Игра не запустилась":      "The game failed to start",
    "Настройки сохранены":      "Settings saved",
    "Нельзя упаковывать сборку во время игры":
        "The instance cannot be packed while the game is running",
    "Нельзя импортировать сборку во время игры":
        "An instance cannot be imported while the game is running",
    "Распаковка сборки...":     "Unpacking the instance...",
    "Сборка не установлена — нажмите «Играть», чтобы скачать":
        "The instance is not installed — press “Play” to download it",
    "Выход":                    "Exit",
    "Игра запущена. Всё равно закрыть лаунчер?":
        "The game is running. Close the launcher anyway?",
    "Критическая ошибка":       "Critical error",

    # ── статусы внизу и счётчики сборки ───────────────────────
    "не найдена":               "not found",
    "  •  ОЗУ свободно {0} ГБ, подкачка/commit {1} ГБ":
        "  •  RAM free {0} GB, page file/commit {1} GB",
    "  (файл подкачки мал!)":   "  (page file is too small!)",
    "Python {0}  •  Java {1}{2}": "Python {0}  •  Java {1}{2}",
    "моды":                     "mods",
    "ресурспаки":               "resource packs",
    "шейдеры":                  "shaders",
    "миры":                     "worlds",
    "папки сборки пустые":      "instance folders are empty",
    "Папка не найдена:\n{0}":   "Folder not found:\n{0}",

    # ── язык интерфейса и принудительный запуск ───────────────
    "Авто (язык системы)":      "Auto (system language)",
    "Язык":                     "Language",
    "Следить за языком системы (русский → русский, иначе английский)":
        "Follow the system language (Russian → Russian, anything else → English)",
    "Разрешить принудительный запуск при нехватке памяти":
        "Allow a forced launch when memory is low",
    "Принудительный запуск при нехватке памяти (RAM {0} МБ)":
        "Forced launch with low memory (RAM {0} MB)",
    "Запустить игру всё равно?\n\nПамяти мало ({0} МБ вместо {1} МБ) — игра может зависнуть или вылететь.\nЛучше увеличить файл подкачки и перезапустить лаунчер.":
        "Launch the game anyway?\n\nMemory is low ({0} MB instead of {1} MB) — the game may "
        "freeze or crash.\nIt is better to increase the Windows page file and restart the launcher.",
    "Запустить всё равно":      "Launch anyway",
    "Обновление версий":        "Refreshing versions",
    "Ставить язык игры таким же, как язык лаунчера (системы)":
        "Set the in-game language to the launcher (system) language",
}

# ─────────────────────────────────────────────────────────────
# ФУНКЦИИ
# ─────────────────────────────────────────────────────────────
def get_language() -> str:
    """Текущий язык интерфейса («ru» или «en»)."""
    return _language


def set_language(code: str) -> str:
    """Устанавливает язык; неизвестный код откатывается на язык по умолчанию."""
    global _language
    _language = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _language


def detect_system_language() -> str:
    """
    Язык интерфейса по системе: русский → «ru», любой другой → «en».
    (Так лаунчер «копирует» язык системы: у кого английская Windows — английский.)
    """
    try:
        if os.name == "nt":
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            # младшие 10 бит — код языка: 0x19 = русский
            return "ru" if (lang_id & 0x3FF) == 0x19 else "en"
    except Exception:
        pass
    try:
        code = (locale.getdefaultlocale()[0] or "").lower()
        return "ru" if code.startswith("ru") else "en"
    except Exception:
        return DEFAULT_LANGUAGE


def tr(text: str, *args, **kwargs) -> str:
    """
    Переводит строку интерфейса. Русский — исходный текст как есть,
    английский — значение из _EN (нет перевода → остаётся русский текст).
    Аргументы подставляются через .format(): tr("Мод {0} удалён", name).
    """
    out = text if _language == "ru" else _EN.get(text, text)
    if args or kwargs:
        try:
            return out.format(*args, **kwargs)
        except Exception:
            return out
    return out


def tr_list(items) -> list:
    """Переводит список строк (для значений CTkComboBox/SegmentedButton)."""
    return [tr(item) for item in items]


def reverse_lookup(translated: str) -> str:
    """Обратный перевод: английский вариант → русская строка (для ComboBox/Segmented)."""
    if _language == "ru":
        return translated
    for ru, en in _EN.items():
        if en == translated:
            return ru
    return translated

