"""
Simple Craft Launcher  v1.0
============================
Copyright (C) 2026 Артемий «tyomik»  ·  лицензия GPL-3.0 (см. LICENSE и NOTICE)

Главный файл UI-лаунчера.
Вся игровая логика (скачивание, запуск Minecraft) делегируется в:
    core/launcher_core.py   — установка, запуск, Java, бэкапы, моды, .mrpack
    core/i18n.py            — переводы (русский / английский)
    core/discord_rpc.py     — статус в Discord (Rich Presence)
"""

import os, sys, json, time, shutil, platform, subprocess, threading, webbrowser
import tkinter as tk
from tkinter import messagebox, colorchooser, filedialog

# Безопасный вывод: если stdout/stderr перенаправлены (лог в файл, IDE),
# символы вроде «→» иначе падают с UnicodeEncodeError в cp1251-консоли.
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────
# АВТОУСТАНОВКА
# ─────────────────────────────────────────────────────────────
def _install_requirements():
    # Словарь: {Название_в_pip: Название_для_импорта_в_коде}
    packages = {
        "customtkinter": "customtkinter", 
        "pillow": "PIL", 
        "requests": "requests",
        "minecraft-launcher-lib": "minecraft_launcher_lib"
    }
    missing = []
    upgrade = False

    for pip_name, mod_name in packages.items():
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(pip_name)

    # minecraft-launcher-lib 8.0+ — единый API mod_loader
    # (Fabric / Forge / NeoForge / Quilt) и скачивание Java-рантаймов
    try:
        import minecraft_launcher_lib as _mll
        if not hasattr(_mll, "mod_loader"):
            if "minecraft-launcher-lib" not in missing:
                missing.append("minecraft-launcher-lib")
            upgrade = True
    except ImportError:
        pass

    # pypresence — только для Discord Rich Presence. Ставим ОТДЕЛЬНО, чтобы
    # сбой установки (нет интернета) не мешал запуску лаунчера.
    try:
        import pypresence  # noqa: F401
    except ImportError:
        print("[SCL] Ставлю pypresence (Discord Rich Presence)...", flush=True)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   "--disable-pip-version-check", "pypresence"])
        except Exception as e:
            print(f"[SCL] pypresence не установился ({e}) — Discord RPC недоступен",
                  flush=True)

    if missing:
        print(f"[SCL] Установка отсутствующих библиотек: {missing}...", flush=True)
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
        if upgrade:
            cmd.append("--upgrade")
        cmd += missing
        try:
            subprocess.check_call(cmd)
        except Exception as e:
            # Если pip упал, покажем красивое окошко вместо тихого краша
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(tr("Ошибка окружения"), 
                f"Не удалось автоматически установить нужные библиотеки: {missing}\n\n"
                f"Лог ошибки: {e}\n\n"
                f"Пожалуйста, откройте консоль (cmd) и введите вручную:\n"
                f"pip install {' '.join(missing)}")
            sys.exit(1)

_install_requirements()

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageColor

# ─────────────────────────────────────────────────────────────
# JSON HELPERS
# ─────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ─────────────────────────────────────────────────────────────
# ПУТИ (игра ставится на диск лаунчера — например B:, а не C:)
# ─────────────────────────────────────────────────────────────
ROOT          = os.path.dirname(os.path.abspath(__file__))
DATA_DIR      = os.path.join(ROOT, "data")
CORE_DIR      = os.path.join(ROOT, "core")
ASSETS_IMG    = os.path.join(ROOT, "assets", "images")
ASSETS_FONTS  = os.path.join(ROOT, "assets", "fonts")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

MIN_FREE_GB   = 5.0                            # меньше — ставим игру на другой диск
DRIVE_ORDER   = "BCDEFGHIJKLMNOPQRSTUVWXYZ"    # B: проверяется первым
DESIRED_DIR   = "SimpleCraftLauncher"          # папка, создаваемая на другом диске


def disk_free_gb(path: str) -> float:
    """Свободно на диске, где лежит path (ГБ). -1 — не смогли определить."""
    probe = os.path.abspath(path or ROOT)
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return -1.0
        probe = parent
    try:
        return shutil.disk_usage(probe).free / (1024 ** 3)
    except Exception:
        return -1.0


def _drive_alive(path: str) -> bool:
    """Существует ли диск (том), на который указывает путь."""
    drive, _ = os.path.splitdrive(os.path.abspath(path))
    return os.path.exists((drive + os.sep) if drive else os.sep)


def pick_instances_dir() -> str:
    """
    Где держать сборки игры:
      1. папка из настроек (если её диск на месте);
      2. рядом с лаунчером (диск B:) — если там есть место;
      3. самый свободный диск (B: в приоритете) — чтобы не забивать диск C:.
    """
    saved_raw = load_json(SETTINGS_FILE, {})
    saved = str((saved_raw or {}).get("instances_dir") or "").strip() \
        if isinstance(saved_raw, dict) else ""
    if saved:
        saved = os.path.abspath(os.path.expanduser(saved))
        if _drive_alive(saved):
            return saved

    root_free = disk_free_gb(ROOT)
    if 0 <= root_free < MIN_FREE_GB:
        best, best_free = "", root_free
        for letter in DRIVE_ORDER:
            drive = f"{letter}:\\"
            if not os.path.exists(drive):
                continue
            free = disk_free_gb(drive)
            if free > best_free:
                best, best_free = drive, free
        if best:
            return os.path.join(best, DESIRED_DIR, "instances")
    return os.path.join(ROOT, "instances")


INSTANCES_DIR = pick_instances_dir()

# Запоминаем папку в настройках, чтобы CORE ставил игру ровно туда же
_cfg_now = load_json(SETTINGS_FILE, {})
if isinstance(_cfg_now, dict) and \
        os.path.abspath(str(_cfg_now.get("instances_dir") or "")) != INSTANCES_DIR:
    _cfg_now["instances_dir"] = INSTANCES_DIR
    save_json(SETTINGS_FILE, _cfg_now)

for d in (DATA_DIR, INSTANCES_DIR, CORE_DIR):
    os.makedirs(d, exist_ok=True)

def asset(rel: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(ROOT, rel)

# ─────────────────────────────────────────────────────────────
# ЛОКАЛИЗАЦИЯ (core/i18n.py)
# ─────────────────────────────────────────────────────────────
def _core_file(name: str) -> str:
    """Путь к файлу в core/ — работает и из исходников, и из собранного EXE."""
    if hasattr(sys, "_MEIPASS"):
        packed = os.path.join(sys._MEIPASS, "core", name)
        if os.path.exists(packed):
            return packed
    return os.path.join(CORE_DIR, name)


def _load_i18n():
    """Загружает словарь переводов; если файла нет, интерфейс остаётся русским."""
    try:
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("scl_i18n", _core_file("i18n.py"))
        mod  = ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"[SCL] Локализация недоступна ({e}) — интерфейс на русском", flush=True)

        class _Fallback:
            LANGUAGES         = {"ru": "Русский"}
            DEFAULT_LANGUAGE  = "ru"

            def get_language(self):           return "ru"
            def set_language(self, code):     return "ru"
            def detect_system_language(self): return "ru"
            def tr_list(self, items):         return list(items)
            def reverse_lookup(self, text):   return text

            def tr(self, text, *args, **kwargs):
                try:
                    return text.format(*args, **kwargs) if (args or kwargs) else text
                except Exception:
                    return text

        return _Fallback()


i18n = _load_i18n()
tr   = i18n.tr


def _load_core_module(name: str, fallback=None):
    """Загружает необязательный модуль из core/ (например discord_rpc.py)."""
    try:
        import importlib.util as ilu
        file_name = name if name.endswith(".py") else name + ".py"
        spec = ilu.spec_from_file_location(f"scl_{name}", _core_file(file_name))
        mod  = ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"[SCL] Модуль {name} недоступен: {e}", flush=True)
        return fallback


discord_rpc_mod = _load_core_module("discord_rpc")

# ─────────────────────────────────────────────────────────────
# О ПРОЕКТЕ + ПОДДЕРЖКА АВТОРА
# ─────────────────────────────────────────────────────────────
APP_NAME    = "Simple Craft Launcher"
APP_VERSION = "1.0"
APP_AUTHOR  = "tyomik"        # ← имя в окне «О лаунчере»
APP_CONTACT = "@artemiy_2007"               # ← e-mail/Telegram автора (необязательно)
APP_REPO    = "https://github.com/artemiy207/Simple-Craft-Launcher"               # ← ссылка на репозиторий с исходниками (необязательно)

# ▼▼▼  ССЫЛКИ НА ПОДДЕРЖКУ АВТОРА (окно «О лаунчере» → «Поддержать автора»)
# Пустая строка → кнопка не показывается. Можно менять и без правки кода:
# файл data/donations.json (образец формата — в документации).
DONATION_LINKS = [
    ("Boosty",         "https://boosty.to/tyomik"),
    ("DonationAlerts", "https://dalink.to/tyomik_3212"),
    ("GitHub",         "https://github.com/artemiy207/Simple-Craft-Launcher"),
]


def donation_links() -> list:
    """
    Ссылки поддержки: если есть data/donations.json — берём оттуда, иначе из
    DONATION_LINKS. Формат файла:
        [{"title": "Boosty", "url": "https://boosty.to/ник"}, ...]
    """
    custom = load_json(os.path.join(DATA_DIR, "donations.json"), None)
    if isinstance(custom, dict):
        custom = custom.get("links") or []
    if isinstance(custom, list):
        result = []
        for item in custom:
            if isinstance(item, dict):
                title, url = str(item.get("title") or "").strip(), \
                             str(item.get("url") or "").strip()
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                title, url = str(item[0]).strip(), str(item[1]).strip()
            else:
                continue
            if title and url:
                result.append((title, url))
        return result
    return [(t, str(u).strip()) for t, u in DONATION_LINKS if str(u).strip()]

# ─────────────────────────────────────────────────────────────
# ВЕРСИИ MINECRAFT (список для UI)
# ─────────────────────────────────────────────────────────────
# Новая нумерация Minecraft: год.обновление.патч (26.3 / 26.1.2 / 1.21.4 …)
MOJANG_VERSION_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
DEFAULT_MINECRAFT_VERSIONS = [
    "26.3", "26.2", "26.1.2", "26.1.1", "26.1",
    "1.21.11", "1.21.10", "1.21.9", "1.21.8", "1.21.7",
    "1.21.6", "1.21.5",
    "1.21.4", "1.21.3", "1.21.2", "1.21.1", "1.21",
    "1.20.6", "1.20.5", "1.20.4", "1.20.3", "1.20.2", "1.20.1", "1.20",
    "1.19.4", "1.19.3", "1.19.2", "1.19",
    "1.18.2", "1.18.1", "1.18",
    "1.17.1", "1.17",
    "1.16.5", "1.16.4", "1.16.3", "1.16.2", "1.16.1", "1.16",
    "1.15.2", "1.15",
    "1.14.4", "1.14",
    "1.13.2", "1.13",
    "1.12.2", "1.12",
    "1.11.2", "1.11",
    "1.10.2", "1.10",
    "1.9.4",  "1.9",
    "1.8.9",  "1.8",
    "1.7.10", "1.7.2",
]
VERSIONS_CACHE_FILE = os.path.join(DATA_DIR, "versions_cache.json")

def _merge_versions(primary: list, fallback: list) -> list:
    """Объединяет списки версий без дублей, сохраняя порядок (свежие — первыми)."""
    result = []
    for version in [*primary, *fallback]:
        if version and version not in result:
            result.append(version)
    return result

def load_versions_cache() -> list:
    """Список версий с прошлого удачного обновления — чтобы работать офлайн."""
    data = load_json(VERSIONS_CACHE_FILE, [])
    if not isinstance(data, list):
        return []
    return [v for v in data if isinstance(v, str) and v]

def save_versions_cache(versions: list) -> None:
    try:
        save_json(VERSIONS_CACHE_FILE, versions)
    except Exception:
        pass

# Офлайн-кэш + встроенный список; после обращения к Mojang список заменится на актуальный
MINECRAFT_VERSIONS = _merge_versions(load_versions_cache(), DEFAULT_MINECRAFT_VERSIONS)

def default_minecraft_version() -> str:
    """Самая свежая release-версия Minecraft (список обновляется с серверов Mojang)."""
    return MINECRAFT_VERSIONS[0] if MINECRAFT_VERSIONS else "26.3"

LOADERS = ["Vanilla", "Fabric", "Forge", "NeoForge", "Quilt"]

# ─────────────────────────────────────────────────────────────
# ТЕМЫ
# ─────────────────────────────────────────────────────────────
DEFAULT_THEME = "Prism Dark"

THEMES = {
    "Prism Dark": {
        "BG": "#16181b", "PANEL": "#1d2023", "CARD": "#25282c",
        "CARD_HOVER": "#2e3237", "CARD_SEL": "#283a4d", "CARD_BORDER": "#4a9eff",
        "BORDER": "#32363b",
        "TEXT": "#e6e8ea", "MUTED": "#9aa0a6",
        "ACCENT": "#4a9eff", "ACCENT_H": "#2f89f0",
        "RED": "#e05252", "RED_H": "#c43c3c", "RED_D": "#432323",
        "GREEN": "#4fbf87", "MODE": "dark",
    },
    "AMOLED": {
        "BG": "#000000", "PANEL": "#0b0b0c", "CARD": "#141416",
        "CARD_HOVER": "#1d1d20", "CARD_SEL": "#12283f", "CARD_BORDER": "#4a9eff",
        "BORDER": "#232326",
        "TEXT": "#f2f3f5", "MUTED": "#8b8f95",
        "ACCENT": "#4a9eff", "ACCENT_H": "#2f89f0",
        "RED": "#e05252", "RED_H": "#c43c3c", "RED_D": "#3a1d1d",
        "GREEN": "#4fbf87", "MODE": "dark",
    },
    "Graphite": {
        "BG": "#1f1f21", "PANEL": "#262629", "CARD": "#2e2e32",
        "CARD_HOVER": "#38383d", "CARD_SEL": "#33383f", "CARD_BORDER": "#9aa0a6",
        "BORDER": "#3c3c41",
        "TEXT": "#e4e4e6", "MUTED": "#a0a0a6",
        "ACCENT": "#b9bfc6", "ACCENT_H": "#cbd1d8",
        "RED": "#d9695f", "RED_H": "#bf5349", "RED_D": "#3d2724",
        "GREEN": "#7bbf8f", "MODE": "dark",
    },
    "Prism Light": {
        "BG": "#f3f4f6", "PANEL": "#ffffff", "CARD": "#ffffff",
        "CARD_HOVER": "#eef1f5", "CARD_SEL": "#e4eef9", "CARD_BORDER": "#2f7fd1",
        "BORDER": "#dcdfe4",
        "TEXT": "#1f2328", "MUTED": "#6b7280",
        "ACCENT": "#2f7fd1", "ACCENT_H": "#256bb5",
        "RED": "#d9534f", "RED_H": "#c9302c", "RED_D": "#f6d7d6",
        "GREEN": "#2e9e5b", "MODE": "light",
    },
    "Nord": {
        "BG": "#2e3440", "PANEL": "#3b4252", "CARD": "#434c5e",
        "CARD_HOVER": "#4c566a", "CARD_SEL": "#3a4a63", "CARD_BORDER": "#88c0d0",
        "TEXT": "#eceff4", "MUTED": "#a3adc2",
        "ACCENT": "#88c0d0", "ACCENT_H": "#79a9b8",
        "RED": "#bf616a", "RED_H": "#a8505a", "RED_D": "#4b2b2f",
        "GREEN": "#a3be8c", "MODE": "dark",
    },
    "Dracula": {
        "BG": "#1e1f29", "PANEL": "#282a36", "CARD": "#343746",
        "CARD_HOVER": "#3f4256", "CARD_SEL": "#443a5c", "CARD_BORDER": "#bd93f9",
        "TEXT": "#f8f8f2", "MUTED": "#a0a4b8",
        "ACCENT": "#bd93f9", "ACCENT_H": "#a97fe8",
        "RED": "#ff5555", "RED_H": "#e03e3e", "RED_D": "#4d1d22",
        "GREEN": "#50fa7b", "MODE": "dark",
    },
    "Sunset": {
        "BG": "#1a1113", "PANEL": "#241618", "CARD": "#2f1d20",
        "CARD_HOVER": "#3d2629", "CARD_SEL": "#492a20", "CARD_BORDER": "#ff7b54",
        "TEXT": "#ffe8dd", "MUTED": "#c9a08f",
        "ACCENT": "#ff7b54", "ACCENT_H": "#e8663f",
        "RED": "#f2545b", "RED_H": "#d43b42", "RED_D": "#4d1a1c",
        "GREEN": "#7bd88f", "MODE": "dark",
    },
    "Ocean": {
        "BG": "#071a22", "PANEL": "#0c2530", "CARD": "#12323f",
        "CARD_HOVER": "#173f4f", "CARD_SEL": "#0f3d4d", "CARD_BORDER": "#22d3ee",
        "TEXT": "#d7f5fb", "MUTED": "#7fb8c7",
        "ACCENT": "#22d3ee", "ACCENT_H": "#0ea5c4",
        "RED": "#f87171", "RED_H": "#dc2626", "RED_D": "#4a1d1d",
        "GREEN": "#34d399", "MODE": "dark",
    },
    "Cyberpunk": {
        "BG": "#0b0812", "PANEL": "#150f22", "CARD": "#1f1633",
        "CARD_HOVER": "#2a1e45", "CARD_SEL": "#3a1160", "CARD_BORDER": "#ff2e97",
        "TEXT": "#f2e9ff", "MUTED": "#a08fc0",
        "ACCENT": "#ff2e97", "ACCENT_H": "#e01f83",
        "RED": "#ff5c5c", "RED_H": "#e03e3e", "RED_D": "#4d1030",
        "GREEN": "#00f5a0", "MODE": "dark",
    },
    "Monokai": {
        "BG": "#1f1f1c", "PANEL": "#272822", "CARD": "#31322b",
        "CARD_HOVER": "#3d3e35", "CARD_SEL": "#3b3a26", "CARD_BORDER": "#f4bf75",
        "TEXT": "#f8f8f2", "MUTED": "#a9a99a",
        "ACCENT": "#f4bf75", "ACCENT_H": "#e0a95a",
        "RED": "#f92672", "RED_H": "#d81e60", "RED_D": "#4d1a2e",
        "GREEN": "#a6e22e", "MODE": "dark",
    },
    "Sakura": {
        "BG": "#fdf2f6", "PANEL": "#fbe4ec", "CARD": "#ffffff",
        "CARD_HOVER": "#f6d7e3", "CARD_SEL": "#fbe0ea", "CARD_BORDER": "#f472b6",
        "TEXT": "#3f2b35", "MUTED": "#9b7b8a",
        "ACCENT": "#f472b6", "ACCENT_H": "#e0509f",
        "RED": "#ef4444", "RED_H": "#dc2626", "RED_D": "#f9c9d8",
        "GREEN": "#12a06b", "MODE": "light",
    },
    "Mint": {
        "BG": "#effaf6", "PANEL": "#dff5ec", "CARD": "#ffffff",
        "CARD_HOVER": "#cdeee1", "CARD_SEL": "#d7f5e8", "CARD_BORDER": "#10b981",
        "TEXT": "#14342b", "MUTED": "#5f8b7c",
        "ACCENT": "#10b981", "ACCENT_H": "#0d9668",
        "RED": "#ef4444", "RED_H": "#dc2626", "RED_D": "#f7d0d0",
        "GREEN": "#16a34a", "MODE": "light",
    },
}

# Цвета бейджей загрузчиков — подобраны так, чтобы читаться в любой теме
LOADER_COLORS = {
    "Vanilla":  "#4ade80",
    "Fabric":   "#dbb69b",
    "Forge":    "#f59e0b",
    "NeoForge": "#fb7185",
    "Quilt":    "#c084fc",
}

def loader_color(loader: str) -> str:
    return LOADER_COLORS.get(loader or "Vanilla", "#94a3b8")

def _hex_to_rgb(color: str) -> tuple:
    text = (color or "#000000").lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except Exception:
        return (0, 0, 0)

def blend_hex(color_a: str, color_b: str, t: float) -> str:
    """Смешивает два цвета: t=0 → color_a, t=1 → color_b."""
    r1, g1, b1 = _hex_to_rgb(color_a)
    r2, g2, b2 = _hex_to_rgb(color_b)
    return "#%02x%02x%02x" % (
        max(0, min(255, round(r1 + (r2 - r1) * t))),
        max(0, min(255, round(g1 + (g2 - g1) * t))),
        max(0, min(255, round(b1 + (b2 - b1) * t))),
    )

class T:
    """Активная тема — singleton с горячей заменой."""
    _d = THEMES[DEFAULT_THEME].copy()
    NAME = DEFAULT_THEME

    BG=PANEL=CARD=CARD_HOVER=CARD_SEL=CARD_BORDER=BORDER=""
    TEXT=MUTED=ACCENT=ACCENT_H=RED=RED_H=RED_D=GREEN=""
    ICON="#e6ecf5"
    MODE="dark"; FONT="Montserrat"

    @classmethod
    def apply(cls, name: str):
        d = THEMES.get(name, THEMES[DEFAULT_THEME])
        cls.NAME = name if name in THEMES else DEFAULT_THEME
        cls._d = d.copy()
        cls.BG=d["BG"]; cls.PANEL=d["PANEL"]; cls.CARD=d["CARD"]
        cls.CARD_HOVER=d["CARD_HOVER"]; cls.CARD_SEL=d["CARD_SEL"]
        cls.CARD_BORDER=d["CARD_BORDER"]; cls.TEXT=d["TEXT"]
        cls.MUTED=d["MUTED"]; cls.ACCENT=d["ACCENT"]
        cls.ACCENT_H=d["ACCENT_H"]; cls.RED=d["RED"]
        cls.RED_H=d["RED_H"]; cls.RED_D=d["RED_D"]; cls.GREEN=d["GREEN"]
        cls.MODE=d["MODE"]
        # тонкая рамка/разделитель: своя из темы или авто-подмес от текста к карточке
        cls.BORDER = d.get("BORDER") or blend_hex(d["CARD"], d["TEXT"],
                                                  0.12 if d["MODE"] == "dark" else 0.10)
        # цвет однотонных иконок: на тёмных темах — светлые, на светлых — тёмные
        cls.ICON = "#e6ecf5" if d["MODE"] == "dark" else "#22303c"
        ctk.set_appearance_mode(cls.MODE)

T.apply(DEFAULT_THEME)

# ─────────────────────────────────────────────────────────────
# ШРИФТ
# ─────────────────────────────────────────────────────────────
def _load_font():
    fp = asset(os.path.join("assets", "fonts", "Montserrat-Bold.ttf"))
    if os.path.exists(fp) and platform.system() == "Windows":
        try:
            import ctypes as _ct
            _ct.windll.gdi32.AddFontResourceW(fp)
        except Exception:
            pass

_load_font()

# ─────────────────────────────────────────────────────────────
# ИКОНКИ
# ─────────────────────────────────────────────────────────────
# Что положить в assets/images: PNG с прозрачным фоном, однотонный глиф
# (лаунчер сам перекрасит его под тему — тёмная тема → белый, светлая → тёмный).
# размер в скобках — как иконка отрисовывается в интерфейсе.
REQUIRED_ICONS = {
    "logo.png":      ((34, 34), "логотип в топбаре"),
    "add.png":       ((18, 18), "кнопки «Добавить» и «Новая сборка» (плюс)"),
    "settings.png":  ((18, 18), "настройки лаунчера и сборки (шестерёнка)"),
    "folders.png":   ((18, 18), "кнопки «Папки» / «Открыть папку»"),
    "console.png":   ((18, 18), "кнопка «Консоль» (терминал)"),
    "play.png":      ((18, 18), "все кнопки «Играть» (треугольник)"),
    "stop.png":      ((18, 18), "кнопки «Остановить» и «Игра идёт» (квадрат)"),
    "mods.png":      ((18, 18), "кнопка «Открыть mods» (пазл)"),
    "edit.png":      ((18, 18), "кнопка «Переименовать» (карандаш)"),
    "delete.png":    ((18, 18), "кнопка «Удалить» (корзина)"),
    "user.png":      ((18, 18), "аккаунт: кнопка внизу и строки в списке"),
    "refresh.png":   ((16, 16), "кнопка «Обновить версии» (стрелки по кругу)"),
    "box_icon.png":  ((34, 34), "иконка сборки по умолчанию (лучше 256x256)"),
    "app_icon.ico":  ((0, 0),   "иконка окна и EXE (ico, 256x256)"),
}

def missing_icons() -> list:
    """Файлы иконок, которых пока нет в assets/images (не критично — будет текст)."""
    return [name for name in REQUIRED_ICONS
            if not os.path.exists(asset(os.path.join("assets", "images", name)))]

_ICON_CACHE: dict[str, ctk.CTkImage] = {}

def _tint(img: Image.Image, color: str) -> Image.Image:
    """Перекрашивает однотонную иконку в нужный цвет (для тёмных и светлых тем)."""
    img = img.convert("RGBA")
    rgb = ImageColor.getrgb(color)
    img.putdata([(rgb[0], rgb[1], rgb[2], a) for _r, _g, _b, a in img.getdata()])
    return img

def _make_placeholder(size=(20,20)) -> Image.Image:
    img  = Image.new("RGBA", size, (0,0,0,0))
    draw = ImageDraw.Draw(img)
    s    = min(size)
    draw.ellipse([2,2,s-3,s-3], fill=(255,255,255,180))
    return img

def load_icon(filename: str, size=(20,20), color: str | None = None) -> ctk.CTkImage:
    """Иконка из assets/images, перекрашенная под текущую тему."""
    tint = color or getattr(T, "ICON", "#e6ecf5")
    key  = f"{filename}_{size}_{tint}"
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    path = asset(os.path.join("assets","images",filename))
    try:
        img = _tint(Image.open(path), tint)
    except Exception:
        img = _make_placeholder(size)
    ci = ctk.CTkImage(light_image=img, dark_image=img, size=size)
    _ICON_CACHE[key] = ci
    return ci

def load_icon_opt(filename: str, size=(18,18), color: str | None = None):
    """Иконка, если файл существует; иначе None — кнопка станет просто текстовой."""
    if not os.path.exists(asset(os.path.join("assets","images",filename))):
        return None
    return load_icon(filename, size, color)

def load_image_icon(filename: str, size=(34,34)):
    """
    Иконка в исходных цветах (без перекраски под тему) — для логотипа:
    цветной логотип перекрашивать нельзя, иначе он превращается в белое пятно.
    """
    path = asset(os.path.join("assets","images",filename))
    if not os.path.exists(path):
        return None
    key = f"raw_{filename}_{size}"
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    try:
        img = _square_image(Image.open(path).convert("RGBA"), max(size))
    except Exception:
        return None
    ci = ctk.CTkImage(light_image=img, dark_image=img, size=size)
    _ICON_CACHE[key] = ci
    return ci

def load_instance_icon(instance_name: str, size=(56,56)) -> ctk.CTkImage:
    """Пробует загрузить icon.png инстанса, иначе box_icon.png."""
    if instance_name:
        custom = os.path.join(INSTANCES_DIR, instance_name, "icon.png")
        if os.path.exists(custom):
            try:
                img = Image.open(custom).convert("RGBA")
                return ctk.CTkImage(light_image=img, dark_image=img, size=size)
            except Exception:
                pass
    return load_icon("box_icon.png", size=size)

# ─────────────────────────────────────────────────────────────
# ИКОНКА ОКНА
# ─────────────────────────────────────────────────────────────
_WINDOW_ICON_SIZES = [(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)]

def _square_image(img: Image.Image, size: int = 256) -> Image.Image:
    """Вписывает картинку в квадрат с сохранением пропорций (без обрезки)."""
    img = img.convert("RGBA")
    w, h = img.size or (1, 1)
    scale = min(size / max(w, 1), size / max(h, 1))
    resized = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(resized, ((size - resized.width) // 2,
                           (size - resized.height) // 2), resized)
    return canvas

def prepare_window_icon(src_ico: str, src_png: str, out_path: str) -> str:
    """
    Готовит мультиразмерный .ico (16…256) из app_icon.ico или logo.png.
    Windows не показывает .ico, внутри которого только одна картинка 256×256,
    поэтому такой файл кэшируем в data/cache и отдаём в iconbitmap.
    Возвращает путь к готовому файлу или "" если не получилось.
    """
    try:
        newest = max([os.path.getmtime(p) for p in (src_ico, src_png)
                      if os.path.exists(p)] or [0])
        if os.path.exists(out_path) and os.path.getmtime(out_path) >= newest:
            try:
                with Image.open(out_path) as probe:
                    if len(probe.info.get("sizes", ()) or ()) > 1:
                        return out_path
            except Exception:
                pass

        source = None
        if os.path.exists(src_ico):
            with Image.open(src_ico) as im:
                source = im.convert("RGBA").copy()
        if source is None and os.path.exists(src_png):
            with Image.open(src_png) as im:
                source = im.convert("RGBA").copy()
        if source is None:
            return ""

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        _square_image(source, 256).save(out_path, format="ICO", sizes=_WINDOW_ICON_SIZES)
        return out_path
    except Exception as e:
        log.log(f"Не удалось собрать иконку окна: {e}", "WARN")
        return ""

# ─────────────────────────────────────────────────────────────
# LOGGER  (print + опциональный textbox)
# ─────────────────────────────────────────────────────────────
class Logger:
    FILE      = os.path.join(DATA_DIR, "launcher.log")
    FILE_LIMIT = 2 * 1024 * 1024       # 2 МБ, потом уходим в launcher.log.1

    def __init__(self):
        self._box = None

    def attach(self, box):
        self._box = box

    def log(self, msg: str, level="INFO"):
        line = f"[{level}] {msg}"

        try:
            print(line, flush=True)
        except Exception:
            pass

        # Дублируем в файл — чтобы разбираться с ошибками после закрытия лаунчера
        try:
            if os.path.exists(self.FILE) and os.path.getsize(self.FILE) > self.FILE_LIMIT:
                bak = self.FILE + ".1"
                if os.path.exists(bak):
                    os.remove(bak)
                os.replace(self.FILE, bak)
            with open(self.FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

        if self._box:
            try:
                self._box.configure(state="normal")
                self._box.insert("end", line + "\n")
                self._box.see("end")
                self._box.configure(state="disabled")
            except Exception:
                pass

log = Logger()

# ─────────────────────────────────────────────────────────────
# SETTINGS MANAGER
# ─────────────────────────────────────────────────────────────
class Settings:
    FILE = os.path.join(DATA_DIR, "settings.json")
    DEFAULTS = {
        "theme":             DEFAULT_THEME,
        "ram":               4096,
        "java_path":         "",
        "auto_java":         True,
        "jvm_args":          "-XX:+UseG1GC -XX:+ParallelRefProcEnabled",
        "close_on_launch":   False,
        "selected_instance": None,
        "language":          "",          # пусто = язык системы при первом запуске
        "discord_rpc":       False,
        "discord_join":      False,
        "discord_client_id": "",
        "language_auto":     True,        # следовать за языком системы
        "sync_game_language": True,       # ставить язык игры как в системе
        "force_launch":      False,       # разрешать запуск игры при нехватке памяти
        "folder_chosen":     False,       # владелец уже выбрал папку сборок?
        "window_width":      1200,
        "window_height":     700,
        "instances_dir":     INSTANCES_DIR,
    }

    @classmethod
    def load(cls) -> dict:
        data = load_json(cls.FILE, {})
        merged = cls.DEFAULTS.copy()
        if isinstance(data, dict):
            merged.update(data)
        return merged

    @classmethod
    def save(cls, data: dict):
        save_json(cls.FILE, data)

def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def effective_ram_mb(instance_cfg: dict | None = None) -> int:
    """RAM сборки (значение сборки, иначе глобальное) — но не больше безопасного для системы."""
    cfg = Settings.load()
    instance_ram = _safe_int((instance_cfg or {}).get("ram"), 0)
    global_ram = _safe_int(cfg.get("ram"), 4096)
    wanted = max(1024, min(32768, instance_ram or global_ram))
    return CoreBridge.safe_ram_mb(wanted)

# ─────────────────────────────────────────────────────────────
# ACCOUNT MANAGER
# ─────────────────────────────────────────────────────────────
class AccountMgr:
    FILE = os.path.join(DATA_DIR, "accounts.json")

    @classmethod
    def load(cls) -> list:
        data = load_json(cls.FILE, [])
        # Защита: если файл битый или список пуст, создаем дефолт
        if not data or not isinstance(data, list):
            data = [{"name": "Player", "type": "offline",
                     "uuid": CoreBridge.offline_uuid("Player")}]
        return data

    @classmethod
    def save(cls, data: list):
        save_json(cls.FILE, data)

    @classmethod
    def add(cls, name: str, acc_type="offline") -> list:
        accounts = cls.load()
        for a in accounts:
            if a["name"] == name:
                raise Exception(f"Аккаунт «{name}» уже существует")
        # Стабильный offline-UUID: один и тот же ник — один и тот же игрок всегда
        accounts.append({"name": name, "type": acc_type,
                         "uuid": CoreBridge.offline_uuid(name)})
        cls.save(accounts)
        return accounts

    @classmethod
    def remove(cls, name: str) -> list:
        accounts = [a for a in cls.load() if a["name"] != name]
        if not accounts:
            # Запрещаем удалять последний аккаунт подчистую (всегда должен быть 1)
            accounts = [{"name": "Player", "type": "offline",
                         "uuid": CoreBridge.offline_uuid("Player")}]
        cls.save(accounts)
        return accounts

# ─────────────────────────────────────────────────────────────
# INSTANCE MANAGER
# ─────────────────────────────────────────────────────────────
class InstanceMgr:

    @staticmethod
    def path(name: str) -> str:
        return os.path.join(INSTANCES_DIR, name)

    @staticmethod
    def cfg_path(name: str) -> str:
        return os.path.join(INSTANCES_DIR, name, "instance.json")

    @classmethod
    def create(cls, name: str, version=None, loader="Vanilla",
               ram=4096, java="", jvm_args="") -> dict:
        version = version or default_minecraft_version()
        p = cls.path(name)
        if os.path.exists(p) and os.path.exists(cls.cfg_path(name)):
            raise Exception("Сборка с таким именем уже существует")
            
        # создаём стандартную структуру папок
        for sub in ("mods", "resourcepacks", "shaderpacks", "saves", "screenshots", "logs"):
            os.makedirs(os.path.join(p, sub), exist_ok=True)
            
        data = {
            "name": name, "version": version, "loader": loader,
            "ram": ram, "java_path": java, "jvm_args": jvm_args,
            "created": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "last_played": None, "play_time": 0,
        }
        save_json(cls.cfg_path(name), data)
        log.log(f"Создана сборка: {name}  [{loader} {version}]")
        return data

    @classmethod
    def delete(cls, name: str):
        p = cls.path(name)
        if os.path.exists(p):
            shutil.rmtree(p)
        log.log(f"Удалена сборка: {name}")

    @classmethod
    def rename(cls, old: str, new: str):
        if os.path.exists(cls.path(new)):
            raise Exception("Сборка с таким именем уже существует")
        os.rename(cls.path(old), cls.path(new))
        cfg  = cls.cfg_path(new)
        data = load_json(cfg, {})
        data["name"] = new
        save_json(cfg, data)
        log.log(f"Переименована: {old} → {new}")

    @classmethod
    def load_all(cls) -> list:
        result = []
        if not os.path.isdir(INSTANCES_DIR):
            return result
        for folder in sorted(os.listdir(INSTANCES_DIR)):
            cfg = cls.cfg_path(folder)
            if os.path.isdir(cls.path(folder)) and os.path.exists(cfg):
                result.append(load_json(cfg, {}))
        return result

    @classmethod
    def save_cfg(cls, data: dict):
        save_json(cls.cfg_path(data["name"]), data)

# ─────────────────────────────────────────────────────────────
# CORE BRIDGE  — обращение к будущему launcher_core.py
# ─────────────────────────────────────────────────────────────
class CoreBridge:
    """
    Тонкая прослойка между UI и игровой логикой.
    Когда core/launcher_core.py будет реализован — UI трогать не нужно.
    """
    # _core_file учитывает и распаковку EXE (--onefile), и запуск из исходников
    CORE_PATH = _core_file("launcher_core.py")
    _MODULE   = None

    @classmethod
    def _ensure_core_file(cls) -> bool:
        """Модуль игровой логики обязателен: без него лаунчер ничего не сможет."""
        if os.path.exists(cls.CORE_PATH):
            return True
        log.log(f"Не найден модуль ядра: {cls.CORE_PATH} — "
                f"скачайте папку core/ из репозитория проекта", "ERROR")
        return False

    @classmethod
    def _get_core(cls):
        """Загружает core/launcher_core.py один раз и держит модуль в кэше."""
        if cls._MODULE is None:
            if not cls._ensure_core_file():
                raise FileNotFoundError(f"Не найден модуль ядра: {cls.CORE_PATH}")
            import importlib.util as ilu
            spec = ilu.spec_from_file_location("launcher_core", cls.CORE_PATH)
            mod  = ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "set_logger"):          # логи CORE → в окно «Консоль»
                mod.set_logger(log.log)
            cls._MODULE = mod
        return cls._MODULE

    @classmethod
    def install(cls, instance_cfg: dict, progress_cb=None) -> bool:
        try:
            return bool(cls._get_core().install(instance_cfg, progress_cb))
        except Exception as e:
            log.log(f"CORE install error: {e}", "ERROR")
            return False

    @classmethod
    def is_installed(cls, instance_cfg: dict) -> bool:
        try:
            core = cls._get_core()
            if hasattr(core, "is_installed"):
                return bool(core.is_installed(instance_cfg))
        except Exception as e:
            log.log(f"CORE installed check error: {e}", "WARN")
        return False

    @classmethod
    def get_last_error(cls) -> str:
        """Текст последней ошибки CORE — показываем его пользователю."""
        try:
            core = cls._get_core()
            if hasattr(core, "get_last_error"):
                return str(core.get_last_error() or "")
        except Exception:
            pass
        return ""

    @classmethod
    def export_instance(cls, instance_cfg: dict, archive_path: str,
                        progress_cb=None) -> bool:
        """Сборка → один ZIP-файл (можно передать другу)."""
        try:
            core = cls._get_core()
            if hasattr(core, "export_instance"):
                return bool(core.export_instance(instance_cfg, archive_path, progress_cb))
            log.log("CORE не умеет экспорт сборок", "ERROR")
        except Exception as e:
            log.log(f"CORE export error: {e}", "ERROR")
        return False

    @classmethod
    def import_instance(cls, archive_path: str, name: str = "",
                        progress_cb=None) -> str:
        """ZIP-файл → новая сборка. Возвращает имя сборки ("" — ошибка)."""
        try:
            core = cls._get_core()
            if hasattr(core, "import_instance"):
                return str(core.import_instance(archive_path, name, progress_cb) or "")
            log.log("CORE не умеет импорт сборок", "ERROR")
        except Exception as e:
            log.log(f"CORE import error: {e}", "ERROR")
        return ""

    @classmethod
    def instances_dir(cls) -> str:
        """Папка сборок по мнению CORE (совпадает с data/settings.json)."""
        try:
            core = cls._get_core()
            if hasattr(core, "instances_dir"):
                return str(core.instances_dir())
        except Exception:
            pass
        return INSTANCES_DIR

    @classmethod
    def disk_free_gb(cls, path: str) -> float:
        """Свободное место (ГБ) — для подсказок в настройках."""
        try:
            core = cls._get_core()
            if hasattr(core, "disk_free_gb"):
                return float(core.disk_free_gb(path))
        except Exception:
            pass
        return disk_free_gb(path)

    @classmethod
    def export_mrpack(cls, instance_cfg: dict, archive_path: str,
                      progress_cb=None) -> bool:
        """Сборка → .mrpack (Modrinth / Prism Launcher)."""
        return cls._call_bool("export_mrpack", instance_cfg, archive_path, progress_cb)

    @classmethod
    def backup_saves(cls, instance_cfg: dict, reason: str = "ручной",
                     progress_cb=None) -> str:
        """Бэкап миров сборки; возвращает путь к архиву."""
        try:
            core = cls._get_core()
            if hasattr(core, "backup_saves"):
                return str(core.backup_saves(instance_cfg, reason, progress_cb) or "")
        except Exception as e:
            log.log(f"CORE backup error: {e}", "ERROR")
        return ""

    @classmethod
    def list_backups(cls, instance_cfg: dict) -> list:
        try:
            core = cls._get_core()
            if hasattr(core, "list_backups"):
                return list(core.list_backups(instance_cfg) or [])
        except Exception as e:
            log.log(f"CORE list backups error: {e}", "WARN")
        return []

    @classmethod
    def restore_backup(cls, instance_cfg: dict, archive_path: str,
                       progress_cb=None) -> bool:
        return cls._call_bool("restore_backup", instance_cfg, archive_path, progress_cb)

    @classmethod
    def modrinth_search(cls, query: str, version: str = "", loader: str = "Vanilla",
                        limit: int = 20, offset: int = 0) -> list:
        try:
            core = cls._get_core()
            if hasattr(core, "modrinth_search"):
                return list(core.modrinth_search(query, version, loader, limit, offset) or [])
        except Exception as e:
            log.log(f"Modrinth поиск: {e}", "ERROR")
        return []

    @classmethod
    def modrinth_install(cls, instance_cfg: dict, project_id: str, title: str = "",
                         progress_cb=None) -> bool:
        return cls._call_bool("modrinth_install", instance_cfg, project_id, title,
                              "", "", progress_cb)

    @classmethod
    def modrinth_remove(cls, instance_cfg: dict, project_id: str) -> bool:
        return cls._call_bool("modrinth_remove", instance_cfg, project_id)

    @classmethod
    def modrinth_update_all(cls, instance_cfg: dict, progress_cb=None) -> dict:
        try:
            core = cls._get_core()
            if hasattr(core, "modrinth_update_all"):
                return dict(core.modrinth_update_all(instance_cfg, progress_cb) or {})
        except Exception as e:
            log.log(f"Обновление модов: {e}", "ERROR")
        return {}

    @classmethod
    def mods_meta(cls, instance_cfg: dict) -> dict:
        """Что установлено через менеджер модов (для списка в UI)."""
        try:
            core = cls._get_core()
            if hasattr(core, "read_mods_meta"):
                return dict(core.read_mods_meta(instance_cfg) or {})
        except Exception:
            pass
        return {}

    @classmethod
    def apply_game_language(cls, instance_cfg: dict, ui_language: str) -> str:
        """Ставит язык игры (options.txt) таким же, как язык лаунчера/системы."""
        try:
            core = cls._get_core()
            if hasattr(core, "apply_game_language"):
                return str(core.apply_game_language(instance_cfg, ui_language) or "")
        except Exception as e:
            log.log(f"Язык игры: {e}", "WARN")
        return ""

    @classmethod
    def _call_bool(cls, name: str, *args) -> bool:
        """Вызывает функцию CORE и приводит результат к bool (с логом ошибок)."""
        try:
            core = cls._get_core()
            func = getattr(core, name, None)
            if func is None:
                log.log(f"CORE не умеет {name}", "ERROR")
                return False
            return bool(func(*args))
        except Exception as e:
            log.log(f"CORE {name} error: {e}", "ERROR")
            return False

    @classmethod
    def offline_uuid(cls, name: str) -> str:
        """UUID offline-аккаунта (md5 от 'OfflinePlayer:<ник>') — стабильный."""
        try:
            core = cls._get_core()
            if hasattr(core, "offline_uuid"):
                return core.offline_uuid(name)
        except Exception as e:
            log.log(f"CORE offline_uuid error: {e}", "WARN")

        import hashlib
        digest = bytearray(hashlib.md5(
            ("OfflinePlayer:" + (name or "Player")).encode("utf-8")).digest())
        digest[6] = (digest[6] & 0x0F) | 0x30
        digest[8] = (digest[8] & 0x3F) | 0x80
        h = digest.hex()
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

    @classmethod
    def launch(cls, instance_cfg: dict, account: dict):
        try:
            return cls._get_core().launch(instance_cfg, account)
        except Exception as e:
            log.log(f"CORE launch error: {e}", "ERROR")
            return None

    @classmethod
    def fetch_versions(cls) -> list:
        try:
            versions = cls._get_core().fetch_versions()
            return versions if isinstance(versions, list) else []
        except Exception as e:
            log.log(f"CORE versions error: {e}", "WARN")
            return []

    @classmethod
    def latest_release(cls) -> str:
        """Самая свежая release-версия со стороны core (пусто — нет сети)."""
        try:
            core = cls._get_core()
            if hasattr(core, "latest_release"):
                return str(core.latest_release() or "")
        except Exception as e:
            log.log(f"CORE latest_release error: {e}", "WARN")
        return ""

    @classmethod
    def memory_hint(cls) -> str:
        """Строка про память системы (ОЗУ + файл подкачки) для интерфейса."""
        try:
            core = cls._get_core()
            if hasattr(core, "memory_hint"):
                return str(core.memory_hint() or "")
        except Exception:
            pass
        return ""

    @classmethod
    def safe_ram_mb(cls, requested: int) -> int:
        """Сколько МБ можно реально отдать игре."""
        try:
            core = cls._get_core()
            if hasattr(core, "safe_ram_mb"):
                return int(core.safe_ram_mb(requested))
        except Exception:
            pass
        return int(requested)

    @classmethod
    def classify_crash(cls, output_tail: str) -> tuple:
        """Причина падения игры по её выводу: (код, объяснение)."""
        try:
            core = cls._get_core()
            if hasattr(core, "classify_crash"):
                return core.classify_crash(output_tail)
        except Exception as e:
            log.log(f"CORE classify_crash error: {e}", "WARN")
        return ("unknown", "Игра завершилась с ошибкой.")

# Прогреваем core на старте, чтобы ошибки в нём были видны сразу (UI не ломаем)
try:
    CoreBridge._get_core()
except Exception as _e:
    log.log(f"Не удалось загрузить core/launcher_core.py: {_e}", "ERROR")

def fetch_mojang_release_versions() -> list:
    try:
        import requests
        resp = requests.get(MOJANG_VERSION_MANIFEST, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        return [
            item["id"] for item in data.get("versions", [])
            if item.get("type") == "release" and item.get("id")
        ]
    except Exception as e:
        log.log(f"Mojang versions error: {e}", "WARN")
        return []

def refresh_minecraft_versions() -> tuple[bool, list]:
    """Обновляет список версий с серверов Mojang; без сети — из офлайн-кэша."""
    global MINECRAFT_VERSIONS
    versions = fetch_mojang_release_versions()
    if not versions:
        versions = CoreBridge.fetch_versions()
    if not versions:
        MINECRAFT_VERSIONS = _merge_versions(load_versions_cache(), DEFAULT_MINECRAFT_VERSIONS)
        return False, MINECRAFT_VERSIONS
    MINECRAFT_VERSIONS = _merge_versions(versions, DEFAULT_MINECRAFT_VERSIONS)
    save_versions_cache(versions)
    return True, MINECRAFT_VERSIONS

# ─────────────────────────────────────────────────────────────
# УТИЛИТЫ UI
# ─────────────────────────────────────────────────────────────
def font(size=13, weight="normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=T.FONT, size=size, weight=weight)

def open_folder(path: str):
    if not os.path.exists(path):
        messagebox.showwarning("SCL", tr("Папка не найдена:\n{0}", path))
        return
    try:
        s = platform.system()
        if   s == "Windows": os.startfile(path)
        elif s == "Darwin":  subprocess.Popen(["open",     path])
        else:                subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror(tr("Ошибка"), str(e))

# ═══════════════════════════════════════════════════════════════
#  ВИДЖЕТЫ
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────
# INSTANCE CARD
# ─────────────────────────────────────────────────────────────
class InstanceCard(ctk.CTkFrame):
    def __init__(self, parent, data: dict, on_select, on_play):
        super().__init__(parent,
            width=206, height=246,
            fg_color=T.CARD, corner_radius=10,
            border_width=1, border_color=T.BORDER)
        self.data      = data
        self.on_select = on_select
        self.on_play   = on_play
        self.selected  = False
        self.grid_propagate(False)

        self._ico = load_instance_icon(data.get("name",""), size=(58,58))
        self._lbl_ico = ctk.CTkLabel(self, image=self._ico, text="")
        self._lbl_ico.pack(pady=(14,6))

        self._lbl_name = ctk.CTkLabel(self,
            text=data.get("name","?"),
            font=font(13,"bold"), wraplength=170)
        self._lbl_name.pack()

        loader  = data.get("loader","Vanilla")
        version = data.get("version","")
        self._lbl_ver = ctk.CTkLabel(self,
            text=f" {loader} {version} ",
            text_color="#101418",
            fg_color=loader_color(loader), corner_radius=6,
            font=font(10,"bold"), height=20)
        self._lbl_ver.pack(pady=(6,0))

        self._lbl_ram = ctk.CTkLabel(self,
            text=f"RAM {effective_ram_mb(data)} МБ",
            text_color=T.MUTED, font=font(10))
        self._lbl_ram.pack(pady=(4,0))

        # статус установки — заполняется из App.set_installed()
        self._lbl_state = ctk.CTkLabel(self, text="",
            text_color=T.MUTED, font=font(9))
        self._lbl_state.pack(pady=(2,0))

        # ── кнопка быстрого запуска ──────────────────────────
        ico_play = load_icon_opt("play.png", (14,14))
        self._btn_play = ctk.CTkButton(self,
            text=tr("Играть"), width=112, height=28,
            image=ico_play,
            compound="left" if ico_play else "center",
            corner_radius=8, font=font(11,"bold"),
            fg_color=T.ACCENT, hover_color=T.ACCENT_H,
            command=self._quick_play)
        self._btn_play.pack(pady=(9,0))

        for w in (self, self._lbl_ico, self._lbl_name, self._lbl_ver,
                  self._lbl_ram, self._lbl_state):
            w.bind("<Button-1>",        self._click)
            w.bind("<Double-Button-1>", self._dbl)
            w.bind("<Enter>",           self._enter)
            w.bind("<Leave>",           self._leave)
            w.bind("<Button-3>",        self._rclick)

    def set_selected(self, v: bool):
        self.selected = v
        if v:
            self.configure(fg_color=T.CARD_SEL, border_color=T.CARD_BORDER)
        else:
            self.configure(fg_color=T.CARD, border_color=T.BORDER)

    def set_installed(self, installed: bool, note: str = ""):
        """Индикатор «установлена / нет» на карточке."""
        if installed:
            text = "Установлена" + (f" • {note}" if note else "")
            self._lbl_state.configure(text=text, text_color=T.GREEN)
        else:
            self._lbl_state.configure(text=tr("Не установлена"), text_color=T.MUTED)

    def _click(self,_e):  self.on_select(self.data)
    def _dbl(self,_e):    self.on_play(self.data)
    def _quick_play(self): self.on_play(self.data)
    def _enter(self,_e):
        if not self.selected:
            self.configure(fg_color=T.CARD_HOVER, border_color=T.CARD_BORDER)
    def _leave(self,_e):
        if not self.selected:
            self.configure(fg_color=T.CARD, border_color=T.BORDER)
    def _rclick(self, e):
        menu = tk.Menu(self, tearoff=0,
                       bg=T.CARD, fg=T.TEXT,
                       activebackground=T.CARD_HOVER,
                       activeforeground=T.TEXT,
                       bd=0, relief="flat")
        menu.add_command(label=tr("Играть"),       command=lambda: self.on_play(self.data))
        menu.add_command(label=tr("Настройки"),    command=lambda: self.on_select(self.data, open_settings=True))
        menu.add_separator()
        menu.add_command(label=tr("Открыть папку"), command=lambda: open_folder(InstanceMgr.path(self.data["name"])))
        menu.add_command(label=tr("Открыть mods"),  command=lambda: open_folder(
            os.path.join(InstanceMgr.path(self.data["name"]), "mods")))
        menu.add_separator()
        menu.add_command(label=tr("Удалить"),      command=lambda: self.on_select(self.data, delete=True))
        try: menu.tk_popup(e.x_root, e.y_root)
        finally: menu.grab_release()

# ─────────────────────────────────────────────────────────────
# PROGRESS BAR OVERLAY  (показывается во время установки)
# ─────────────────────────────────────────────────────────────
class ProgressOverlay(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent,
            fg_color=T.PANEL, corner_radius=10,
            border_width=1, border_color=T.BORDER)
        ctk.CTkLabel(self, text=tr("Установка..."),
                     font=font(14,"bold")).pack(pady=(20,8))
        self._bar = ctk.CTkProgressBar(self, width=340,
                                       fg_color=T.CARD,
                                       progress_color=T.ACCENT)
        self._bar.set(0)
        self._bar.pack(padx=30, pady=4)
        self._lbl = ctk.CTkLabel(self, text=tr("Подготовка..."),
                                 text_color=T.MUTED, font=font(11))
        self._lbl.pack(pady=(4,20))

        # анимация «работа идёт»: полоса бежит, в подписи крутятся точки
        self._anim_job  = None
        self._sweep     = 0.0
        self._dots      = 0
        self._busy_text = tr("Подготовка...")

    def busy(self, status: str = ""):
        """Показывает анимацию, пока точный процент неизвестен."""
        if status:
            self._busy_text = status
        if self._anim_job is None:
            self._tick()

    def _tick(self):
        try:
            self._sweep = (self._sweep + 0.06) % 1.20
            self._bar.set(min(1.0, self._sweep))
            self._dots = (self._dots + 1) % 4
            self._lbl.configure(text=f"{self._busy_text}{'.' * self._dots}")
            self._anim_job = self.after(350, self._tick)
        except Exception:
            self._anim_job = None

    def _stop_anim(self):
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

    def update(self, value: float, status: str):
        """Известен процент — останавливаем анимацию и показываем точное значение."""
        self._stop_anim()
        self._bar.set(max(0.0, min(1.0, value)))
        self._lbl.configure(text=status)
        self.update_idletasks()

    def busy_if_unknown(self, value: float, status: str):
        """Прогресс ещё нулевой — анимируем; иначе показываем точный процент."""
        if value <= 0.001:
            self.busy(status or tr("Подготовка..."))
        else:
            self.update(value, status)

# ═══════════════════════════════════════════════════════════════
#  ДИАЛОГОВЫЕ ОКНА
# ═══════════════════════════════════════════════════════════════

class _BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, w=520, h=400):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{w}x{h}")
        self.configure(fg_color=T.BG)
        self.resizable(False, False)
        self.grab_set()
        # центрировать относительно родителя
        self.after(50, self._center, parent)

    def _center(self, parent):
        try:
            px = parent.winfo_rootx() + parent.winfo_width()//2
            py = parent.winfo_rooty() + parent.winfo_height()//2
            self.geometry(f"+{px - self.winfo_width()//2}+{py - self.winfo_height()//2}")
        except Exception:
            pass

    def _header(self, text: str, icon: str | None = None):
        img = load_icon_opt(icon, (20,20)) if icon else None
        ctk.CTkLabel(self, text=text, image=img,
                     compound="left" if img else "center",
                     font=font(20,"bold")).pack(pady=(22,16))

    def _btn_row(self, ok_text="Создать", ok_cmd=None, cancel_cmd=None):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(8,20))
        ctk.CTkButton(row, text=tr("Отмена"),
                      fg_color=T.CARD, hover_color=T.CARD_HOVER,
                      command=cancel_cmd or self.destroy
                      ).pack(side="left", expand=True, fill="x", padx=(0,6))
        ctk.CTkButton(row, text=ok_text,
                      fg_color=T.ACCENT, hover_color=T.ACCENT_H,
                      font=font(13,"bold"),
                      command=ok_cmd
                      ).pack(side="left", expand=True, fill="x")

# ─────────────────────────────────────────────────────────────
# ДИАЛОГ СОЗДАНИЯ СБОРКИ
# ─────────────────────────────────────────────────────────────
class CreateInstanceDialog(_BaseDialog):
    def __init__(self, parent, on_created):
        super().__init__(parent, "Новая сборка", w=520, h=460)
        self.on_created = on_created
        self._build()

    def _build(self):
        self._header(tr("Создание сборки"), "add.png")
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24)

        def row(label):
            ctk.CTkLabel(body, text=label,
                         text_color=T.MUTED, font=font(12),
                         anchor="w").pack(fill="x", pady=(8,1))

        row(tr("Название"))
        self._name = ctk.CTkEntry(body, placeholder_text=tr("Моя сборка"),
                                  font=font(13))
        self._name.pack(fill="x")

        row(tr("Версия Minecraft"))
        versions = MINECRAFT_VERSIONS or DEFAULT_MINECRAFT_VERSIONS
        self._ver = ctk.CTkComboBox(body,
            values=versions, font=font(13),
            dropdown_font=font(12),
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H,
            border_color=T.CARD_HOVER)
        self._ver.set(default_minecraft_version())
        self._ver.pack(fill="x")

        row(tr("Загрузчик"))
        self._loader = ctk.CTkSegmentedButton(body,
            values=LOADERS, font=font(12),
            selected_color=T.ACCENT, selected_hover_color=T.ACCENT_H,
            unselected_color=T.CARD, unselected_hover_color=T.CARD_HOVER)
        self._loader.set("Vanilla")
        self._loader.pack(fill="x", pady=(2,0))

        row(tr("RAM (МБ)"))
        default_ram = effective_ram_mb({})
        self._ram = ctk.CTkEntry(body, placeholder_text="4096", font=font(13))
        self._ram.insert(0, str(default_ram))
        self._ram.pack(fill="x")
        ctk.CTkLabel(body, text=f"система сейчас позволяет до {CoreBridge.safe_ram_mb(32768)} МБ",
                     text_color=T.MUTED, font=font(10), anchor="w").pack(fill="x")

        self._btn_row(tr("Создать"), self._submit)

    def _submit(self):
        name   = self._name.get().strip()
        ver    = self._ver.get()
        loader = self._loader.get()
        try:
            ram = int(self._ram.get())
        except ValueError:
            messagebox.showerror(tr("Ошибка"),tr( "RAM должен быть числом"), parent=self)
            return
        if not name:
            messagebox.showerror(tr("Ошибка"),tr( "Введите название сборки"), parent=self)
            return
        try:
            data = InstanceMgr.create(name, ver, loader, ram)
            self.on_created(data)
            self.destroy()
        except Exception as e:
            messagebox.showerror(tr("Ошибка"), str(e), parent=self)

# ─────────────────────────────────────────────────────────────
# ДИАЛОГ НАСТРОЕК СБОРКИ
# ─────────────────────────────────────────────────────────────
class InstanceSettingsDialog(_BaseDialog):
    def __init__(self, parent, data: dict, on_saved):
        super().__init__(parent, f"Настройки — {data['name']}", w=540, h=520)
        self.data     = data.copy()
        self.on_saved = on_saved
        self._build()

    def _build(self):
        self._header(self.data['name'], "settings.png")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=24)

        def row(label):
            ctk.CTkLabel(scroll, text=label,
                         text_color=T.MUTED, font=font(12), anchor="w"
                         ).pack(fill="x", pady=(10,1))

        row(tr("Название"))
        self._name = ctk.CTkEntry(scroll, font=font(13))
        self._name.insert(0, self.data.get("name",""))
        self._name.pack(fill="x")

        row(tr("Версия Minecraft"))
        versions = MINECRAFT_VERSIONS or DEFAULT_MINECRAFT_VERSIONS
        self._ver = ctk.CTkComboBox(scroll,
            values=versions, font=font(13),
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H,
            border_color=T.CARD_HOVER)
        self._ver.set(self.data.get("version", default_minecraft_version()))
        self._ver.pack(fill="x")

        row(tr("Загрузчик"))
        self._loader = ctk.CTkSegmentedButton(scroll,
            values=LOADERS, font=font(12),
            selected_color=T.ACCENT, selected_hover_color=T.ACCENT_H,
            unselected_color=T.CARD, unselected_hover_color=T.CARD_HOVER)
        self._loader.set(self.data.get("loader","Vanilla"))
        self._loader.pack(fill="x", pady=(2,0))

        row(tr("RAM (МБ)"))
        self._ram = ctk.CTkEntry(scroll, font=font(13))
        self._ram.insert(0, str(self.data.get("ram", 4096)))
        self._ram.pack(fill="x")
        ctk.CTkLabel(scroll, text=f"система сейчас позволяет до {CoreBridge.safe_ram_mb(32768)} МБ",
                     text_color=T.MUTED, font=font(10), anchor="w").pack(fill="x")

        row(tr("Путь к Java (оставь пустым — авто)"))
        self._java = ctk.CTkEntry(scroll, font=font(12),
                                  placeholder_text="C:\\Program Files\\Java\\...")
        self._java.insert(0, self.data.get("java_path",""))
        self._java.pack(fill="x")

        row(tr("Аргументы JVM"))
        self._jvm = ctk.CTkEntry(scroll, font=font(12),
            placeholder_text="-XX:+UseG1GC -XX:+ParallelRefProcEnabled")
        self._jvm.insert(0, self.data.get("jvm_args",""))
        self._jvm.pack(fill="x")

        self._btn_row(tr("Сохранить"), self._submit)

    def _submit(self):
        new_name = self._name.get().strip()
        old_name = self.data["name"]
        try:
            ram = int(self._ram.get())
        except ValueError:
            messagebox.showerror(tr("Ошибка"),tr("RAM должен быть числом"), parent=self)
            return
        if not new_name:
            messagebox.showerror(tr("Ошибка"),tr("Введите название"), parent=self)
            return
        try:
            if new_name != old_name:
                InstanceMgr.rename(old_name, new_name)
                self.data["name"] = new_name
            self.data.update({
                "version":   self._ver.get(),
                "loader":    self._loader.get(),
                "ram":       ram,
                "java_path": self._java.get().strip(),
                "jvm_args":  self._jvm.get().strip(),
            })
            InstanceMgr.save_cfg(self.data)
            self.on_saved(self.data)
            self.destroy()
        except Exception as e:
            messagebox.showerror(tr("Ошибка"), str(e), parent=self)

# ─────────────────────────────────────────────────────────────
# ДИАЛОГ АККАУНТОВ
# ─────────────────────────────────────────────────────────────
class AccountsDialog(_BaseDialog):
    def __init__(self, parent, on_select):
        super().__init__(parent, "Аккаунты", w=440, h=480)
        self.on_select = on_select
        self.accounts  = AccountMgr.load()
        self._build()

    def _build(self):
        self._header(tr("Аккаунты"), "user.png")

        self._list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list.pack(fill="both", expand=True, padx=20)

        self._refresh()

        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", padx=20, pady=(8,16))
        self._new_name = ctk.CTkEntry(add_row,
            placeholder_text=tr("Никнейм (offline)"), font=font(13))
        self._new_name.pack(side="left", fill="x", expand=True, padx=(0,8))
        ctk.CTkButton(add_row, text=tr("+ Добавить"), width=100,
                      fg_color=T.ACCENT, hover_color=T.ACCENT_H,
                      command=self._add).pack(side="left")

    def _refresh(self):
        for w in self._list.winfo_children():
            w.destroy()
        for acc in self.accounts:
            row = ctk.CTkFrame(self._list,
                fg_color=T.CARD, corner_radius=8)
            row.pack(fill="x", pady=4)
            ico_user = load_icon_opt("user.png", (16,16))
            ctk.CTkLabel(row,
                text=f"  {acc['name']}" if ico_user else acc["name"],
                image=ico_user, compound="left" if ico_user else "center",
                font=font(13)
            ).pack(side="left", padx=12, pady=10)
            ctk.CTkLabel(row,
                text=acc.get("type","offline"),
                text_color=T.MUTED, font=font(11)
            ).pack(side="left")
            ctk.CTkButton(row, text=tr("Выбрать"), width=80,
                fg_color=T.ACCENT, hover_color=T.ACCENT_H,
                command=lambda a=acc: self._select(a)
            ).pack(side="right", padx=6)
            ico_del = load_icon_opt("delete.png", (14,14))
            ctk.CTkButton(row, text="×" if ico_del else "Удалить",
                width=32 if ico_del else 76,
                image=ico_del, compound="center",
                fg_color=T.RED_D, hover_color=T.RED_H,
                command=lambda n=acc["name"]: self._delete(n)
            ).pack(side="right", padx=(0,4))

    def _add(self):
        name = self._new_name.get().strip()
        if not name:
            return
        try:
            self.accounts = AccountMgr.add(name)
            self._new_name.delete(0,"end")
            self._refresh()
        except Exception as e:
            messagebox.showerror(tr("Ошибка"), str(e), parent=self)

    def _delete(self, name):
        if messagebox.askyesno(tr("Удаление"), f"Удалить аккаунт «{name}»?", parent=self):
            self.accounts = AccountMgr.remove(name)
            self._refresh()

    def _select(self, acc: dict):
        self.on_select(acc)
        self.destroy()

# ─────────────────────────────────────────────────────────────
# ДИАЛОГ ГЛОБАЛЬНЫХ НАСТРОЕК
# ─────────────────────────────────────────────────────────────
class GlobalSettingsDialog(_BaseDialog):
    def __init__(self, parent, on_saved):
        super().__init__(parent, "Настройки лаунчера", w=560, h=580)
        self.on_saved = on_saved
        self.cfg      = Settings.load()
        self._build()

    def _build(self):
        self._header(tr("Настройки лаунчера"), "settings.png")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=24)

        def row(label, hint=""):
            ctk.CTkLabel(scroll, text=label,
                         text_color=T.MUTED, font=font(12), anchor="w"
                         ).pack(fill="x", pady=(12,1))
            if hint:
                ctk.CTkLabel(scroll, text=hint,
                             text_color=T.MUTED, font=font(10), anchor="w"
                             ).pack(fill="x")

        # ── Язык интерфейса ────────────────────────────────
        row(tr("Язык"), tr("Следить за языком системы (русский → русский, иначе английский)"))
        self._auto_lang_label = tr("Авто (язык системы)")
        self._lang = ctk.CTkComboBox(scroll,
            values=[self._auto_lang_label] + [i18n.LANGUAGES[code] for code in i18n.LANGUAGES],
            font=font(13), button_color=T.ACCENT, button_hover_color=T.ACCENT_H,
            border_color=T.CARD_HOVER)
        if self.cfg.get("language_auto", True):
            self._lang.set(self._auto_lang_label)
        else:
            self._lang.set(i18n.LANGUAGES.get(i18n.get_language(), i18n.LANGUAGES["ru"]))
        self._lang.pack(fill="x")

        # ── Тема ───────────────────────────────────────────
        row(tr("Тема оформления"),
            tr("{0} тем • применяется сразу, без перезапуска", len(THEMES)))
        self._theme = ctk.CTkComboBox(scroll,
            values=list(THEMES.keys()), font=font(13),
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H,
            border_color=T.CARD_HOVER,
            command=self._preview_theme)
        self._theme.set(self.cfg.get("theme", DEFAULT_THEME))
        self._theme.pack(fill="x")

        # ── RAM ────────────────────────────────────────────
        row(tr("RAM по умолчанию (МБ)"), "Используется если не задано в настройках сборки")
        ram_row = ctk.CTkFrame(scroll, fg_color="transparent")
        ram_row.pack(fill="x")
        self._ram_slider = ctk.CTkSlider(ram_row,
            from_=512, to=32768, number_of_steps=63,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H,
            progress_color=T.ACCENT,
            command=self._ram_slide)
        self._ram_slider.set(self.cfg.get("ram",4096))
        self._ram_slider.pack(side="left", fill="x", expand=True)
        self._ram_lbl = ctk.CTkLabel(ram_row,
            text=f"{int(self.cfg.get('ram',4096))} МБ",
            font=font(12), width=72)
        self._ram_lbl.pack(side="left", padx=(8,0))

        # сколько памяти реально доступно системе (в фоне, чтобы окно не подвисало)
        self._mem_lbl = ctk.CTkLabel(scroll, text=tr("Считаю доступную память..."),
                                     text_color=T.MUTED, font=font(10), anchor="w")
        self._mem_lbl.pack(fill="x", pady=(2,0))
        threading.Thread(target=self._load_mem_info, daemon=True).start()

        # ── Java ───────────────────────────────────────────
        row(tr("Глобальный путь к Java"), "Можно переопределить в настройках сборки")
        self._java = ctk.CTkEntry(scroll, font=font(12),
            placeholder_text=tr("Авто (из PATH)"))
        self._java.insert(0, self.cfg.get("java_path",""))
        self._java.pack(fill="x")

        # ── JVM Args ───────────────────────────────────────
        row(tr("Аргументы JVM по умолчанию"))
        self._jvm = ctk.CTkEntry(scroll, font=font(12))
        self._jvm.insert(0, self.cfg.get("jvm_args",
            "-XX:+UseG1GC -XX:+ParallelRefProcEnabled"))
        self._jvm.pack(fill="x")

        # ── Папка сборок (диск) ────────────────────────────
        row(tr("Папка сборок"), "Где лежат и устанавливаются сборки. По умолчанию — "
                            "диск лаунчера (B:), чтобы не забивать диск C:")
        dir_row = ctk.CTkFrame(scroll, fg_color="transparent")
        dir_row.pack(fill="x")
        self._dir = ctk.CTkEntry(dir_row, font=font(11))
        self._dir.insert(0, self.cfg.get("instances_dir") or INSTANCES_DIR)
        self._dir.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(dir_row, text=tr("Выбрать"), width=84, height=28,
            fg_color=T.CARD, hover_color=T.CARD_HOVER,
            font=font(11), text_color=T.TEXT,
            command=self._pick_dir).pack(side="left", padx=(6,0))
        ctk.CTkButton(dir_row, text=tr("Открыть"), width=84, height=28,
            fg_color=T.CARD, hover_color=T.CARD_HOVER,
            font=font(11), text_color=T.TEXT,
            command=lambda: open_folder(self._dir.get().strip() or INSTANCES_DIR)
        ).pack(side="left", padx=(6,0))
        self._dir_lbl = ctk.CTkLabel(scroll, text="", text_color=T.MUTED,
                                     font=font(10), anchor="w")
        self._dir_lbl.pack(fill="x", pady=(2,0))
        self._dir.bind("<KeyRelease>", lambda _e: self._dir_info())
        self._dir_info()

        # ── Java: автоскачивание нужной версии ─────────────
        self._auto_java_sw = ctk.CTkSwitch(scroll,
            text=tr("Скачивать нужную Java автоматически (если её нет в системе)"),
            font=font(13),
            progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H)
        if self.cfg.get("auto_java", True):
            self._auto_java_sw.select()
        self._auto_java_sw.pack(anchor="w", pady=(8,0))

        # ── Закрывать лаунчер при запуске ─────────────────
        row("")
        self._close_sw = ctk.CTkSwitch(scroll,
            text=tr("Сворачивать лаунчер при запуске игры"),
            font=font(13),
            progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H)
        if self.cfg.get("close_on_launch"):
            self._close_sw.select()
        self._close_sw.pack(anchor="w", pady=(4,0))

        # ── Discord RPC ────────────────────────────────────
        self._discord_sw = ctk.CTkSwitch(scroll,
            text=tr("Discord Rich Presence"),
            font=font(13),
            progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H)
        if self.cfg.get("discord_rpc"):
            self._discord_sw.select()
        self._discord_sw.pack(anchor="w", pady=(8,0))

        self._discord_join_sw = ctk.CTkSwitch(scroll,
            text=tr("Разрешить присоединение по Discord"),
            font=font(13),
            progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H)
        if self.cfg.get("discord_join"):
            self._discord_join_sw.select()
        self._discord_join_sw.pack(anchor="w", pady=(4,0))

        self._force_sw = ctk.CTkSwitch(scroll,
            text=tr("Разрешить принудительный запуск при нехватке памяти"),
            font=font(13),
            progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H)
        if self.cfg.get("force_launch"):
            self._force_sw.select()
        self._force_sw.pack(anchor="w", pady=(8,0))

        self._game_lang_sw = ctk.CTkSwitch(scroll,
            text=tr("Ставить язык игры таким же, как язык лаунчера (системы)"),
            font=font(13),
            progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H)
        if self.cfg.get("sync_game_language", True):
            self._game_lang_sw.select()
        self._game_lang_sw.pack(anchor="w", pady=(4,0))

        row(tr("ID приложения Discord"),
            tr("Нужен для Rich Presence: discord.com/developers/applications → "
               "New Application → скопировать Application ID"))
        self._discord_id = ctk.CTkEntry(scroll, font=font(12),
                                        placeholder_text="123456789012345678")
        self._discord_id.insert(0, self.cfg.get("discord_client_id", ""))
        self._discord_id.pack(fill="x")

        # ── О лаунчере / поддержать автора ─────────────────
        ctk.CTkButton(scroll, text=tr("О лаунчере"), height=32,
            fg_color=T.CARD, hover_color=T.CARD_HOVER,
            font=font(12), text_color=T.TEXT,
            command=self._open_about).pack(fill="x", pady=(16,0))

        self._btn_row(tr("Сохранить"), self._submit)

    def _language_choice(self) -> tuple[str, bool]:
        """(код языка, следовать ли за языком системы) по выбору в списке."""
        chosen = self._lang.get()
        if chosen == getattr(self, "_auto_lang_label", ""):
            return (i18n.detect_system_language(), True)
        for code, name in i18n.LANGUAGES.items():
            if name == chosen:
                return (code, False)
        return (i18n.get_language(), False)

    def _language_code(self) -> str:
        """Код выбранного языка (для совместимости)."""
        return self._language_choice()[0]

    def _open_about(self):
        AboutDialog(self.master)

    def _pick_dir(self):
        """Выбор папки сборок на любом диске."""
        chosen = filedialog.askdirectory(
            title=tr("Папка для сборок Minecraft"),
            initialdir=self._dir.get().strip() or INSTANCES_DIR)
        if chosen:
            self._dir.delete(0, "end")
            self._dir.insert(0, os.path.normpath(chosen))
            self._dir_info()

    def _dir_info(self):
        """Показывает свободное место на выбранном диске."""
        path  = self._dir.get().strip() or INSTANCES_DIR
        free  = disk_free_gb(path)
        drive = os.path.splitdrive(os.path.abspath(path))[0] or "?"
        if free < 0:
            self._dir_lbl.configure(text=f"{drive} — диск не найден",
                                    text_color=T.RED_D)
            return
        text = f"{drive} свободно {free:.1f} ГБ"
        if free < MIN_FREE_GB:
            text += " — мало места, лучше выбрать диск B:"
        self._dir_lbl.configure(text=text,
                               text_color=T.RED_D if free < MIN_FREE_GB else T.MUTED)

    def _load_mem_info(self):
        """Показывает, сколько памяти доступно системе и сколько безопасно ставить."""
        try:
            hint = CoreBridge.memory_hint()
            safe = CoreBridge.safe_ram_mb(32768)
            text = f"{hint} • безопасно для игры: до {safe} МБ" if hint else ""
            if hint and "файла подкачки меньше" in hint:
                text += " — увеличьте файл подкачки Windows"
        except Exception:
            text = ""
        try:
            self.after(0, lambda: self._mem_lbl.configure(text=text))
        except Exception:
            pass

    def _preview_theme(self, name: str):
        """Мгновенный предпросмотр: тема применяется к главному окну сразу."""
        if name not in THEMES:
            return
        app = self.master
        if hasattr(app, "_apply_theme"):
            app._apply_theme(name, save=False)

    def _ram_slide(self, v):
        self._ram_lbl.configure(text=f"{int(v)} МБ")

    def _submit(self):
        new_dir = os.path.abspath(self._dir.get().strip() or INSTANCES_DIR)
        try:
            os.makedirs(new_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("SCL",
                f"Не удалось использовать папку:\n{new_dir}\n\n{e}")
            return
        lang_code, lang_auto = self._language_choice()
        self.cfg.update({
            "theme":           self._theme.get(),
            "ram":             int(self._ram_slider.get()),
            "java_path":       self._java.get().strip(),
            "auto_java":       self._auto_java_sw.get() == 1,
            "jvm_args":        self._jvm.get().strip(),
            "close_on_launch": self._close_sw.get() == 1,
            "discord_rpc":     self._discord_sw.get() == 1,
            "discord_join":    self._discord_join_sw.get() == 1,
            "discord_client_id": self._discord_id.get().strip(),
            "force_launch":    self._force_sw.get() == 1,
            "sync_game_language": self._game_lang_sw.get() == 1,
            "language":        lang_code,
            "language_auto":   lang_auto,
            "folder_chosen":   True,
            "instances_dir":   new_dir,
        })
        Settings.save(self.cfg)
        self.on_saved(self.cfg)
        self.destroy()

# ─────────────────────────────────────────────────────────────
# КОНСОЛЬ ВЫВОДА (открывается по кнопке)
# ─────────────────────────────────────────────────────────────
class ConsoleWindow(_BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, "Консоль", w=700, h=480)
        self.title("SCL — Консоль")
        self.resizable(True, True)
        self.grab_release()          # консоль не блокирует

        self._box = ctk.CTkTextbox(self, font=("Consolas",11),
                                   fg_color=T.PANEL, state="disabled")
        self._box.pack(fill="both", expand=True, padx=10, pady=10)
        log.attach(self._box)

        ctk.CTkButton(self, text=tr("Очистить"),
                      fg_color=T.CARD, hover_color=T.CARD_HOVER,
                      command=self._clear).pack(pady=(0,10))

    def _clear(self):
        self._box.configure(state="normal")
        self._box.delete("1.0","end")
        self._box.configure(state="disabled")

class AboutDialog(_BaseDialog):
    """О лаунчере: автор, версия, лицензия, репозиторий и «Поддержать автора»."""

    def __init__(self, parent):
        super().__init__(parent, tr("О лаунчере"), w=580, h=470)
        self._build()

    def _build(self):
        self._header(tr("О лаунчере"), "box_icon.png")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=24)

        info = ctk.CTkFrame(scroll, fg_color=T.PANEL, corner_radius=10)
        info.pack(fill="x")

        def line(text, bold=False, color=None):
            ctk.CTkLabel(info, text=text,
                         font=font(12, "bold" if bold else "normal"),
                         text_color=color or T.TEXT, anchor="w",
                         justify="left", wraplength=470
                         ).pack(fill="x", padx=14, pady=(6, 0))

        line(APP_NAME, bold=True)
        line(tr("Версия {0}", APP_VERSION))
        line(tr("Автор: {0}", APP_AUTHOR))
        line(tr("Сборки, моды и Java хранятся в папке:"), color=T.MUTED)
        line(INSTANCES_DIR, color=T.MUTED)
        ctk.CTkLabel(info, text="", font=font(4)).pack()

        ctk.CTkLabel(scroll,
            text=tr("Исходный код открыт: авторство и уведомление об авторских правах "
                    "обязательно сохраняются при любом распространении и в любых "
                    "изменённых версиях лаунчера (см. файлы LICENSE и NOTICE)."),
            font=font(10), text_color=T.MUTED, justify="left", wraplength=490,
            anchor="w").pack(fill="x", pady=(10, 0))

        if APP_REPO:
            self._link_row(scroll, tr("Исходный код"), APP_REPO)
        if APP_CONTACT:
            self._link_row(scroll, tr("Связаться с автором"), APP_CONTACT)

        # ── поддержать автора ──────────────────────────────
        links = donation_links()
        ctk.CTkLabel(scroll, text=tr("Поддержать автора"),
                     font=font(13, "bold"), text_color=T.TEXT, anchor="w"
                     ).pack(fill="x", pady=(14, 2))
        if not links:
            ctk.CTkLabel(scroll,
                text=tr("Ссылки на поддержку автор ещё не указал.\n"
                        "Он может вписать их в файл data/donations.json — "
                        "перезапуск не нужен."),
                font=font(10), text_color=T.MUTED, justify="left", anchor="w"
                ).pack(fill="x")
        for title, url in links:
            self._link_row(scroll, title, url)

        self._btn_row(tr("Закрыть"), self.destroy)

    @staticmethod
    def _link_row(parent, title: str, url: str):
        """Строка со ссылкой: открывается в браузере по клику."""
        def open_it():
            try:
                webbrowser.open(url)
            except Exception as e:
                log.log(f"Не удалось открыть ссылку {url}: {e}", "WARN")

        ctk.CTkButton(parent, text=f"{title}  →  {url}", anchor="w",
            height=30, corner_radius=8, font=font(11),
            fg_color=T.CARD, hover_color=T.CARD_HOVER, text_color=T.TEXT,
            command=open_it).pack(fill="x", pady=2)

class ModsDialog(_BaseDialog):
    """Менеджер модов: поиск на Modrinth, установка, удаление, обновление всех."""

    def __init__(self, parent, app, inst: dict):
        super().__init__(parent, tr("Моды"), w=780, h=640)
        self.app      = app
        self.inst     = inst
        self._busy    = False
        self._results = []
        self._build()
        self.after(250, self._search)

    def _build(self):
        self._header(tr("Моды · {0}", self.inst.get("name", "")), "mods.png")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=18)
        self._query = ctk.CTkEntry(top, font=font(12),
                                   placeholder_text=tr("Поиск мода, например sodium"))
        self._query.pack(side="left", fill="x", expand=True)
        self._query.bind("<Return>", lambda _e: self._search())
        ctk.CTkButton(top, text=tr("Найти"), width=90, height=30,
                      fg_color=T.ACCENT, hover_color=T.ACCENT_H,
                      font=font(11), command=self._search).pack(side="left", padx=(6, 0))

        self._status = ctk.CTkLabel(self, text="", text_color=T.MUTED,
                                    font=font(10), anchor="w")
        self._status.pack(fill="x", padx=18, pady=(6, 0))

        self._list = ctk.CTkScrollableFrame(self, fg_color=T.PANEL)
        self._list.pack(fill="both", expand=True, padx=18, pady=(4, 6))

        self._inst_lbl = ctk.CTkLabel(self, text="", text_color=T.TEXT,
                                      font=font(12, "bold"), anchor="w")
        self._inst_lbl.pack(fill="x", padx=18)
        self._installed = ctk.CTkScrollableFrame(self, fg_color=T.PANEL, height=112)
        self._installed.pack(fill="x", padx=18, pady=(2, 6))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(row, text=tr("Обновить все моды"), height=32,
                      fg_color=T.CARD, hover_color=T.CARD_HOVER, text_color=T.TEXT,
                      font=font(11), command=self._update_all).pack(side="left")
        ctk.CTkButton(row, text=tr("Открыть mods"), height=32,
                      fg_color=T.CARD, hover_color=T.CARD_HOVER, text_color=T.TEXT,
                      font=font(11), command=self._open_mods).pack(side="left", padx=6)
        ctk.CTkButton(row, text=tr("Закрыть"), height=32,
                      fg_color=T.CARD, hover_color=T.CARD_HOVER, text_color=T.TEXT,
                      font=font(11), command=self.destroy).pack(side="right")

        self._render_installed()

    # ── вспомогательное ───────────────────────────────────────
    def _set_status(self, text: str):
        try:
            self._status.configure(text=text)
        except Exception:
            pass

    def _open_mods(self):
        path = os.path.join(InstanceMgr.path(self.inst["name"]), "mods")
        os.makedirs(path, exist_ok=True)
        open_folder(path)

    def _prepare(self) -> dict:
        return self.app._prepare_launch_instance(self.inst)

    def _loader_note(self) -> str:
        loader = str(self.inst.get("loader") or "Vanilla")
        if loader.lower() == "vanilla":
            return tr("Сборка Vanilla: моды не поддерживаются — смените загрузчик "
                      "на Fabric/Forge в настройках сборки")
        return tr("Версия {0} · загрузчик {1}", self.inst.get("version", "?"), loader)


    # ── поиск ────────────────────────────────────────────────
    def _search(self):
        if self._busy:
            return
        query = self._query.get().strip()
        self._set_status(tr("Поиск на Modrinth...") + " " + self._loader_note())
        self._busy = True

        def worker():
            found = CoreBridge.modrinth_search(query, self.inst.get("version", ""),
                                               self.inst.get("loader", "Vanilla"),
                                               limit=25)
            self.after(0, self._render_results, found)

        threading.Thread(target=worker, daemon=True).start()

    def _render_results(self, found: list):
        self._results = found
        self._busy = False
        for widget in self._list.winfo_children():
            widget.destroy()
        if not found:
            self._set_status(tr("Ничего не найдено — проверьте интернет и версию сборки"))
            return
        self._set_status(tr("Найдено: {0}. {1}", len(found), self._loader_note()))

        for item in found:
            card = ctk.CTkFrame(self._list, fg_color=T.CARD, corner_radius=8)
            card.pack(fill="x", pady=3)
            text = ctk.CTkFrame(card, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, padx=10, pady=6)
            ctk.CTkLabel(text, text=item.get("title", ""), font=font(12, "bold"),
                         text_color=T.TEXT, anchor="w").pack(fill="x")
            meta = tr("{0} · загрузок: {1}", item.get("author") or "—",
                      item.get("downloads", 0))
            ctk.CTkLabel(text, text=meta, font=font(9), text_color=T.MUTED,
                         anchor="w").pack(fill="x")
            ctk.CTkLabel(text, text=(item.get("description") or "")[:120],
                         font=font(10), text_color=T.MUTED, anchor="w",
                         justify="left", wraplength=520).pack(fill="x")
            ctk.CTkButton(card, text=tr("Установить"), width=104, height=30,
                          fg_color=T.ACCENT, hover_color=T.ACCENT_H, font=font(11),
                          command=lambda it=item: self._install(it)
                          ).pack(side="right", padx=10)

# ═══════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ═══════════════════════════════════════════════════════════════
    # ── установка / удаление / обновление ─────────────────────
    def _install(self, item: dict):
        if self._busy:
            return
        title = item.get("title") or item.get("slug") or ""
        self._busy = True
        self._set_status(tr("Скачивание «{0}»...", title))
        inst = self._prepare()

        def worker():
            ok = CoreBridge.modrinth_install(inst, item.get("project_id", ""), title,
                                             self.app._progress_from_thread)
            self.after(0, self._after_install, ok, title)

        threading.Thread(target=worker, daemon=True).start()

    def _after_install(self, ok: bool, title: str):
        self._busy = False
        self._set_status(tr("Мод «{0}» установлен", title) if ok
                         else (CoreBridge.get_last_error()
                               or tr("Не удалось установить мод")))
        self._render_installed()

    def _remove(self, project_id: str, title: str):
        if self._busy:
            return
        if not messagebox.askyesno("SCL", tr("Удалить мод «{0}»?", title)):
            return
        ok = CoreBridge.modrinth_remove(self._prepare(), project_id)
        self._set_status(tr("Мод «{0}» удалён", title) if ok
                         else tr("Не удалось удалить мод"))
        self._render_installed()

    def _update_all(self):
        if self._busy:
            return
        self._busy = True
        self._set_status(tr("Проверяю новые версии модов..."))

        def worker():
            result = CoreBridge.modrinth_update_all(self._prepare(),
                                                    self.app._progress_from_thread)
            self.after(0, self._after_update_all, result)

        threading.Thread(target=worker, daemon=True).start()

    def _after_update_all(self, result: dict):
        self._busy = False
        updated = result.get("updated") or []
        errors  = result.get("errors") or []
        text = tr("Обновлено модов: {0}, актуальных: {1}", len(updated),
                  result.get("kept", 0))
        if errors:
            text += tr(" · ошибок: {0}", len(errors))
            log.log("Моды: ошибки обновления — " + "; ".join(errors), "WARN")
        self._set_status(text)
        self._render_installed()

    def _render_installed(self):
        for widget in self._installed.winfo_children():
            widget.destroy()
        meta = CoreBridge.mods_meta(self._prepare())
        self._inst_lbl.configure(
            text=tr("Установлено через менеджер модов: {0}", len(meta)))
        if not meta:
            ctk.CTkLabel(self._installed,
                         text=tr("Пока пусто — найдите мод выше и нажмите «Установить»"),
                         font=font(10), text_color=T.MUTED, anchor="w"
                         ).pack(fill="x", padx=10, pady=6)
            return
        for project_id, info in meta.items():
            row = ctk.CTkFrame(self._installed, fg_color=T.CARD, corner_radius=8)
            row.pack(fill="x", pady=2)
            title = str((info or {}).get("title") or project_id)
            ctk.CTkLabel(row, text=f"{title}  ·  {(info or {}).get('version_number', '')}",
                         font=font(11), text_color=T.TEXT, anchor="w"
                         ).pack(side="left", padx=10, pady=5)
            ctk.CTkButton(row, text=tr("Удалить"), width=84, height=26,
                          fg_color=T.RED_D, hover_color=T.RED_H, font=font(10),
                          command=lambda pid=project_id, t=title: self._remove(pid, t)
                          ).pack(side="right", padx=8, pady=4)

class BackupsDialog(_BaseDialog):
    """Бэкапы миров: создать копию, восстановить, открыть папку."""

    def __init__(self, parent, app, inst: dict):
        super().__init__(parent, tr("Бэкапы миров"), w=680, h=520)
        self.app   = app
        self.inst  = inst
        self._busy = False
        self._build()
        self._render()

    def _prepare(self) -> dict:
        return self.app._prepare_launch_instance(self.inst)

    def _build(self):
        self._header(tr("Бэкапы миров · {0}", self.inst.get("name", "")), "folders.png")

        self._status = ctk.CTkLabel(self, text="", text_color=T.MUTED,
                                    font=font(10), anchor="w")
        self._status.pack(fill="x", padx=18)

        self._list = ctk.CTkScrollableFrame(self, fg_color=T.PANEL)
        self._list.pack(fill="both", expand=True, padx=18, pady=6)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(row, text=tr("Сделать бэкап сейчас"), height=32,
                      fg_color=T.ACCENT, hover_color=T.ACCENT_H, font=font(11),
                      command=self._make).pack(side="left")
        ctk.CTkButton(row, text=tr("Открыть папку"), height=32,
                      fg_color=T.CARD, hover_color=T.CARD_HOVER, text_color=T.TEXT,
                      font=font(11), command=self._open_folder).pack(side="left", padx=6)
        ctk.CTkButton(row, text=tr("Закрыть"), height=32,
                      fg_color=T.CARD, hover_color=T.CARD_HOVER, text_color=T.TEXT,
                      font=font(11), command=self.destroy).pack(side="right")

    def _render(self):
        for widget in self._list.winfo_children():
            widget.destroy()
        backups = CoreBridge.list_backups(self._prepare())
        self._status.configure(text=(
            tr("Бэкапов: {0}. Хранятся последние 10 в папке сборки.", len(backups))
            if backups else
            tr("Бэкапов пока нет — они создаются автоматически перед установкой, "
               "а также кнопкой ниже")))
        if not backups:
            return
        import time as _time
        for backup in backups:
            card = ctk.CTkFrame(self._list, fg_color=T.CARD, corner_radius=8)
            card.pack(fill="x", pady=2)
            when = _time.strftime("%d.%m.%Y %H:%M",
                                  _time.localtime(backup.get("mtime", 0)))
            ctk.CTkLabel(card,
                         text=f"{backup.get('name', '')}\n{when} · "
                              f"{backup.get('size_mb', 0):.1f} МБ",
                         font=font(10), text_color=T.TEXT, anchor="w",
                         justify="left").pack(side="left", padx=10, pady=5)
            ctk.CTkButton(card, text=tr("Восстановить"), width=112, height=28,
                          fg_color=T.ACCENT, hover_color=T.ACCENT_H, font=font(10),
                          command=lambda b=backup: self._restore(b)).pack(side="right",
                                                                         padx=8, pady=4)

    def _make(self):
        if self._busy:
            return
        self._busy = True
        self._status.configure(text=tr("Делаю бэкап миров..."))

        def worker():
            path = CoreBridge.backup_saves(self._prepare(), "ручной",
                                           self.app._progress_from_thread)
            self.after(0, self._after, bool(path), path)

        threading.Thread(target=worker, daemon=True).start()

    def _restore(self, backup: dict):
        if self._busy:
            return
        name = str(backup.get("name") or "")
        if not messagebox.askyesno("SCL",
                tr("Восстановить миры из «{0}»?\n\nТекущие миры будут сначала "
                   "скопированы в новый бэкап.", name)):
            return
        self._busy = True
        self._status.configure(text=tr("Восстанавливаю миры..."))

        def worker():
            ok = CoreBridge.restore_backup(self._prepare(),
                                           str(backup.get("path") or ""),
                                           self.app._progress_from_thread)
            self.after(0, self._after, ok, tr("Миры восстановлены"))

        threading.Thread(target=worker, daemon=True).start()

    def _after(self, ok: bool, info: str):
        self._busy = False
        if ok:
            self._status.configure(text=info or tr("Готово"))
        else:
            self._status.configure(text=CoreBridge.get_last_error()
                                   or tr("Не получилось — смотрите «Консоль»"))
        self._render()

    def _open_folder(self):
        path = os.path.join(InstanceMgr.path(self.inst["name"]), "backups")
        os.makedirs(path, exist_ok=True)
        open_folder(path)

class App(ctk.CTk):

    VERSION = APP_VERSION

    def __init__(self):
        super().__init__()
        self.cfg              = Settings.load()
        # миграция темы: если сохранённой темы больше нет — переключаемся на тему по умолчанию
        if self.cfg.get("theme") not in THEMES:
            self.cfg["theme"] = DEFAULT_THEME
            Settings.save(self.cfg)
        T.apply(self.cfg.get("theme", DEFAULT_THEME))

        # язык: «Авто» — копируем язык системы (русский → русский, любой другой → английский)
        if self.cfg.get("language_auto", True) or self.cfg.get("language") not in i18n.LANGUAGES:
            self.cfg["language"] = i18n.detect_system_language()
            Settings.save(self.cfg)
        i18n.set_language(self.cfg.get("language") or i18n.DEFAULT_LANGUAGE)

        w = self.cfg.get("window_width",  1200)
        h = self.cfg.get("window_height", 700)
        self.title("Simple Craft Launcher")
        # Защита от float-координат, если они так сохранились
        self.geometry(f"{int(w)}x{int(h)}")
        self.minsize(960, 580)
        self.configure(fg_color=T.BG)

        self._set_window_icon()

        self.current_instance: dict | None = None
        self.current_account: dict = AccountMgr.load()[0]
        self.game_proc        = None
        self.game_reader      = None
        self.game_running     = False
        self._rpc             = None                     # Discord Rich Presence
        self._force_launch_used = False                  # уже просили «запустить всё равно»?
        self._installing        = False                  # идёт установка/обновление сборки
        self._last_progress     = (0.0, "Подготовка...")  # чтобы вернуть прогресс после смены темы
        self.game_tail: list[str] = []          # последние строки вывода игры (для диагностики)
        self.game_started_at  = 0.0
        self.console_win      = None
        self.cards: list[InstanceCard] = []
        self._versions_refreshing = False

        self._preload_icons()
        self._build_ui()
        self._reload_instances()
        self._refresh_versions_async()
        self._update_env_async()

        log.log(f"Simple Craft Launcher v{self.VERSION} запущен")
        log.log(f"Тема: {self.cfg.get('theme')}")
        log.log(f"Папка сборок: {INSTANCES_DIR} "
                f"(свободно {disk_free_gb(INSTANCES_DIR):.1f} ГБ)")

        # первый запуск: спрашиваем, куда ставить сборки (после отрисовки окна)
        self.after(400, self._first_run_folder)

    # ────────────────────────────────────────────────────────
    # ────────────────────────────────────────────────────────
    def _set_window_icon(self):
        """
        Иконка окна и панели задач. Windows не показывает .ico, внутри которого
        одна картинка 256×256, поэтому из assets/images/app_icon.ico (или logo.png)
        собираем мультиразмерный .ico (16…256) и кэшируем в data/cache.
        """
        # Windows берёт иконку кнопки на панели задач у процесса: без
        # AppUserModelID там окажется значок python.exe (или белый квадрат)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"SimpleCraft.Launcher.{APP_VERSION}")
        except Exception:
            pass

        src_ico = asset(os.path.join("assets", "images", "app_icon.ico"))
        src_png = asset(os.path.join("assets", "images", "logo.png"))
        cached  = os.path.join(DATA_DIR, "cache", f"window_icon_{APP_VERSION}.ico")

        ico = ""
        if platform.system() == "Windows":
            ico = prepare_window_icon(src_ico, src_png, cached)
        if not ico:
            ico = src_ico if os.path.exists(src_ico) else \
                (src_png if os.path.exists(src_png) else "")
        if not ico:
            return

        try:
            self.iconbitmap(ico)
        except Exception as e:
            log.log(f"Не удалось установить иконку окна: {e}", "WARN")

    def _preload_icons(self):
        """Иконки кнопок. Если файла нет — кнопка просто станет текстовой."""
        self._ico_logo     = load_image_icon("logo.png",  (34,34)) \
            or load_image_icon("box_icon.png", (34,34)) \
            or load_icon("box_icon.png", (34,34))
        self._ico_add      = load_icon_opt("add.png",      (18,18))
        self._ico_settings = load_icon_opt("settings.png", (18,18))
        self._ico_folders  = load_icon_opt("folders.png",  (18,18))
        self._ico_console  = load_icon_opt("console.png",  (18,18))
        self._ico_play     = load_icon_opt("play.png",     (18,18))
        self._ico_stop     = load_icon_opt("stop.png",     (18,18))
        self._ico_mods     = load_icon_opt("mods.png",     (18,18))
        self._ico_edit     = load_icon_opt("edit.png",     (18,18))
        self._ico_delete   = load_icon_opt("delete.png",   (18,18))
        self._ico_user     = load_icon_opt("user.png",     (18,18))
        self._ico_refresh  = load_icon_opt("refresh.png",  (16,16))
        self._ico_box      = load_icon_opt("box_icon.png", (18,18))

        missing = missing_icons()
        if missing:
            log.log("Нет файлов иконок в assets/images: " + ", ".join(missing)
                    + " — эти кнопки показаны без иконок", "WARN")

    # ────────────────────────────────────────────────────────
    # КНОПКИ ЗАПУСКА (единое состояние сайдбара и нижней панели)
    # ────────────────────────────────────────────────────────
    PLAY_STATES = {
        "play":    ("Играть",       "play", "ACCENT", True),
        "stop":    ("Остановить",   "stop", "RED",    True),
        "running": ("Игра идёт",    "stop", "GREEN",  True),
        "busy":    ("Запуск...",    None,   "ACCENT", False),
        "install": ("Установка...", None,   "ACCENT", False),
    }

    def _set_play_state(self, state: str):
        text, icon_name, color_name, enabled = self.PLAY_STATES.get(
            state, self.PLAY_STATES["play"])
        text  = tr(text)
        color = getattr(T, color_name, T.ACCENT)
        hover = {"ACCENT": T.ACCENT_H, "RED": T.RED_H, "GREEN": T.GREEN}.get(color_name, color)
        icon  = getattr(self, f"_ico_{icon_name}", None) if icon_name else None
        if icon is None and icon_name == "stop":
            icon = self._ico_play

        for btn in (getattr(self, "_btn_play", None),
                    getattr(self, "_sb_play", None)):
            if btn is None:
                continue
            try:
                btn.configure(
                    text=text.upper() if btn is self._btn_play else text,
                    fg_color=color, hover_color=hover,
                    image=icon, compound="left" if icon else "center",
                    state="normal" if enabled else "disabled")
            except Exception:
                pass

    # ────────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_topbar()
        self._build_body()
        self._bind_shortcuts()
        self._set_play_state("running" if self.game_running else "play")

    def _bind_shortcuts(self):
        """Горячие клавиши: F5/Ctrl+R — обновить версии, Ctrl+N — новая сборка,
        Ctrl+L — консоль, F1 — настройки."""
        for seq, fn in (("<F5>", self._refresh_versions_async),
                        ("<Control-r>", self._refresh_versions_async),
                        ("<Control-n>", self._open_create_dialog),
                        ("<Control-l>", self._open_console),
                        ("<F1>", self._open_global_settings)):
            try:
                self.bind(seq, lambda _e, f=fn: f())
            except Exception:
                pass

    # ── ТОПБАР ─────────────────────────────────────────────
    def _build_topbar(self):
        self.topbar = ctk.CTkFrame(self, height=62,
                                   fg_color=T.PANEL, corner_radius=0)
        self.topbar.pack(fill="x")
        self.topbar.pack_propagate(False)

        # лого + название
        ctk.CTkLabel(self.topbar, image=self._ico_logo, text=""
                     ).pack(side="left", padx=(16,10))
        brand = ctk.CTkFrame(self.topbar, fg_color="transparent")
        brand.pack(side="left", padx=(0,18))
        ctk.CTkLabel(brand, text="Simple Craft Launcher",
                     font=font(14,"bold"), text_color=T.TEXT
                     ).pack(anchor="w")
        ctk.CTkLabel(brand, text=f"лаунчер v{self.VERSION}",
                     font=font(10), text_color=T.MUTED
                     ).pack(anchor="w")

        def tb_btn(text, icon=None, cmd=None, color=None, hover=None):
            return ctk.CTkButton(self.topbar,
                text=text, image=icon,
                compound="left" if icon else "center",
                fg_color=color or "transparent",
                hover_color=hover or T.CARD_HOVER,
                height=36, corner_radius=8, font=font(12),
                text_color=T.TEXT if not color else None,
                command=cmd)

        tb_btn(tr("Добавить"), self._ico_add,
               cmd=self._open_create_dialog
               ).pack(side="left", padx=4, pady=13)

        tb_btn(tr("Настройки"), self._ico_settings,
               cmd=self._open_global_settings
               ).pack(side="left", padx=4)

        tb_btn(tr("Папки"), self._ico_folders,
               cmd=lambda: open_folder(INSTANCES_DIR)
               ).pack(side="left", padx=4)

        tb_btn(tr("Консоль"), self._ico_console,
               cmd=self._open_console
               ).pack(side="left", padx=4)

        tb_btn(tr("О лаунчере"), self._ico_box,
               cmd=self._open_about
               ).pack(side="left", padx=4)

        # быстрый выбор темы (справа)
        self._theme_menu = ctk.CTkOptionMenu(self.topbar,
            values=list(THEMES.keys()),
            width=134, height=32, corner_radius=8,
            font=font(11), dropdown_font=font(11),
            fg_color=T.CARD, button_color=T.CARD_HOVER,
            button_hover_color=T.CARD_BORDER, text_color=T.TEXT,
            dropdown_fg_color=T.PANEL, dropdown_hover_color=T.CARD_HOVER,
            dropdown_text_color=T.TEXT,
            command=self._apply_theme)
        self._theme_menu.set(T.NAME)
        self._theme_menu.pack(side="right", padx=(8,16))

        # версия Minecraft (справа от темы)
        self._mc_version_badge = ctk.CTkLabel(self.topbar,
            text=f"MC {default_minecraft_version()}",
            text_color=T.TEXT, font=font(11,"bold"),
            fg_color=T.CARD, corner_radius=8,
            width=96, height=28)
        self._mc_version_badge.pack(side="right", padx=(0,8))

        # тонкая линия под топбаром (как в Prism — плоский интерфейс)
        ctk.CTkFrame(self.topbar, height=1, fg_color=T.BORDER).place(
            relx=0, rely=1.0, anchor="sw", relwidth=1.0)

    # ── BODY (sidebar + center) ─────────────────────────────
    def _build_body(self):
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True)

        self._build_sidebar(self.body)
        self._build_center(self.body)

    # ── ПРАВЫЙ САЙДБАР ─────────────────────────────────────
    def _build_sidebar(self, parent):
        self.sidebar = ctk.CTkFrame(parent, width=278, fg_color=T.PANEL)
        self.sidebar.pack(side="right", fill="y")
        self.sidebar.pack_propagate(False)

        # превью иконки
        self._sb_icon = ctk.CTkLabel(self.sidebar,
            image=load_icon("box_icon.png",(72,72)), text="")
        self._sb_icon.pack(pady=(28,8))

        self._sb_name = ctk.CTkLabel(self.sidebar,
            text=tr("Выберите сборку"),
            font=font(16,"bold"), wraplength=250)
        self._sb_name.pack()

        self._sb_sub = ctk.CTkLabel(self.sidebar,
            text="", text_color=T.MUTED, font=font(11))
        self._sb_sub.pack(pady=(2,4))

        self._sb_time = ctk.CTkLabel(self.sidebar,
            text="", text_color=T.MUTED, font=font(10))
        self._sb_time.pack(pady=(0,4))

        # счётчики содержимого сборки (моды / ресурспаки / шейдеры)
        self._sb_content = ctk.CTkLabel(self.sidebar,
            text="", text_color=T.MUTED, font=font(10))
        self._sb_content.pack(pady=(0,14))

        # ── кнопки ─────────────────────────────────────────
        def sb_btn(text, color=None, hover=None, cmd=None, height=36, icon=None):
            return ctk.CTkButton(self.sidebar,
                text=text, height=height, corner_radius=8,
                image=icon, compound="left" if icon else "center",
                fg_color=color or "transparent",
                hover_color=hover or T.CARD_HOVER,
                text_color=T.TEXT if not color else None,
                font=font(12), command=cmd)

        # Кнопка «Играть» только одна — большая в нижней панели (см. _build_bottom)
        sb_btn(tr("Настройки сборки"), icon=self._ico_settings,
               cmd=lambda: self._open_instance_settings()
               ).pack(fill="x", padx=18, pady=(0,2))

        sb_btn(tr("Открыть папку"), icon=self._ico_folders,
               cmd=lambda: open_folder(
                   InstanceMgr.path(self.current_instance["name"])
                   if self.current_instance else INSTANCES_DIR)
               ).pack(fill="x", padx=18, pady=2)

        sb_btn(tr("Моды"), icon=self._ico_mods,
               cmd=self._open_mods_manager
               ).pack(fill="x", padx=18, pady=2)

        sb_btn(tr("Бэкапы миров"), icon=self._ico_box,
               cmd=self._open_backups
               ).pack(fill="x", padx=18, pady=2)

        sb_btn(tr("Поделиться сборкой"), icon=self._ico_add,
               cmd=lambda: self._export_instance()
               ).pack(fill="x", padx=18, pady=2)

        sb_btn(tr("Переименовать"), icon=self._ico_edit,
               cmd=self._rename_instance
               ).pack(fill="x", padx=18, pady=2)

        # разделитель
        ctk.CTkFrame(self.sidebar, height=1,
                     fg_color=T.BORDER
                     ).pack(fill="x", padx=18, pady=10)

        sb_btn(tr("Удалить"), T.RED_D, T.RED_H, self._delete_instance,
               icon=self._ico_delete
               ).pack(fill="x", padx=18, pady=2)

    # ── ЦЕНТР ───────────────────────────────────────────────
    def _build_center(self, parent):
        self.center = ctk.CTkFrame(parent, fg_color="transparent")
        self.center.pack(side="left", fill="both", expand=True)

        header = ctk.CTkFrame(self.center, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(16,4))

        ctk.CTkLabel(header,
            text=tr("Сборки"),
            font=font(22,"bold"), text_color=T.TEXT
        ).pack(side="left")

        self._library_stats = ctk.CTkLabel(header,
            text="", text_color=T.MUTED, font=font(11))
        self._library_stats.pack(side="left", padx=(10,0), pady=(6,0))

        self._btn_refresh = ctk.CTkButton(header,
            text=tr("Обновить версии"),
            width=168, height=30, corner_radius=8,
            image=self._ico_refresh,
            compound="left" if self._ico_refresh else "center",
            fg_color=T.CARD, hover_color=T.CARD_HOVER,
            font=font(11), text_color=T.TEXT,
            command=self._refresh_versions_async)
        self._btn_refresh.pack(side="right")

        ctk.CTkButton(header,
            text=tr("Импорт сборки"),
            width=140, height=30, corner_radius=8,
            fg_color=T.CARD, hover_color=T.CARD_HOVER,
            font=font(11), text_color=T.TEXT,
            command=self._import_instance
        ).pack(side="right", padx=(0,8))

        # поиск + сортировка
        top = ctk.CTkFrame(self.center, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(4,4))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        self._search_entry = ctk.CTkEntry(top,
            textvariable=self._search_var,
            placeholder_text=tr("Поиск сборок..."),
            font=font(13), height=36)
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0,8))

        self._sort_var = tk.StringVar(value="Имя")
        ctk.CTkSegmentedButton(top,
            values=["Имя","Версия","Дата"],
            variable=self._sort_var,
            font=font(11),
            selected_color=T.ACCENT, selected_hover_color=T.ACCENT_H,
            unselected_color=T.CARD, unselected_hover_color=T.CARD_HOVER,
            command=self._on_sort
        ).pack(side="left")

        # сетка карточек
        self.grid_frame = ctk.CTkScrollableFrame(
            self.center, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True, padx=10, pady=(4,4))

        # прогресс-оверлей (скрыт)
        self._progress = ProgressOverlay(self.center)

        # нижняя панель
        self._build_bottom()

    def _build_bottom(self):
        bottom = ctk.CTkFrame(self.center, height=72, fg_color=T.PANEL)
        bottom.pack(fill="x")
        bottom.pack_propagate(False)

        # аккаунт
        ico_user = self._ico_user or load_icon_opt("user.png", (18,18))
        self._btn_account = ctk.CTkButton(bottom,
            text=f"  {self.current_account['name']}" if ico_user
                 else self.current_account['name'],
            image=ico_user, compound="left" if ico_user else "center",
            height=40, corner_radius=8, width=180,
            fg_color=T.CARD, hover_color=T.CARD_HOVER,
            font=font(12),
            command=self._open_accounts)
        self._btn_account.pack(side="left", padx=16, pady=16)

        # тип аккаунта
        self._lbl_acc_type = ctk.CTkLabel(bottom,
            text=f"({self.current_account.get('type','offline')})",
            text_color=T.MUTED, font=font(10))
        self._lbl_acc_type.pack(side="left")

        info = ctk.CTkFrame(bottom, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=18)

        self._lbl_bottom_status = ctk.CTkLabel(info,
            text=tr("Выберите сборку для запуска"),
            text_color=T.TEXT, font=font(11), anchor="w")
        self._lbl_bottom_status.pack(anchor="w")

        self._lbl_env = ctk.CTkLabel(info,
            text="", text_color=T.MUTED, font=font(9), anchor="w")
        self._lbl_env.pack(anchor="w")

        # большая кнопка ИГРАТЬ
        self._btn_play = ctk.CTkButton(bottom,
            text=tr("ИГРАТЬ"),
            image=self._ico_play,
            compound="left" if self._ico_play else "center",
            width=220, height=46, corner_radius=10,
            fg_color=T.ACCENT, hover_color=T.ACCENT_H,
            font=font(15,"bold"),
            command=self._toggle_game)
        self._btn_play.pack(side="right", padx=16, pady=12)

    # ────────────────────────────────────────────────────────
    # ИНСТАНСЫ
    # ────────────────────────────────────────────────────────
    def _reload_instances(self, select_name: str | None = None):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.cards.clear()

        all_instances = InstanceMgr.load_all()

        if not all_instances:
            try: InstanceMgr.create("Vanilla", default_minecraft_version())
            except Exception: pass
            all_instances = InstanceMgr.load_all()

        query = self._search_var.get().lower() if hasattr(self,"_search_var") else ""
        sort  = self._sort_var.get() if hasattr(self,"_sort_var") else "Имя"
        instances = all_instances[:]

        # фильтр
        if query:
            instances = [i for i in instances
                         if query in i.get("name","").lower()
                         or query in i.get("version","").lower()]
        # сортировка
        if sort == "Версия":
            instances.sort(key=lambda i: i.get("version",""))
        elif sort == "Дата":
            instances.sort(key=lambda i: i.get("created",""), reverse=True)
        else:
            instances.sort(key=lambda i: i.get("name","").lower())

        if hasattr(self, "_library_stats"):
            total = len(all_instances)
            shown = len(instances)
            suffix = f"{shown} из {total}" if query else str(total)
            self._library_stats.configure(
                text=f"{suffix} • актуальная MC {default_minecraft_version()}")

        if not instances:
            self._show_empty_state("Ничего не найдено" if query else "Сборок пока нет")
            return

        COLS = max(1, (self.grid_frame.winfo_width() or 900) // 225)

        for idx, inst in enumerate(instances):
            card = InstanceCard(
                self.grid_frame, inst,
                on_select=self._card_select,
                on_play=self._play_instance)
            card.grid(row=idx//COLS, column=idx%COLS, padx=10, pady=10)
            self.cards.append(card)

        # восстановить выбор
        target = select_name or (self.current_instance["name"] if self.current_instance else None)
        if target:
            for c in self.cards:
                if c.data.get("name") == target:
                    self._select_instance(c.data)
                    return
        if instances:
            self._select_instance(instances[0])

    def _show_empty_state(self, title: str):
        box = ctk.CTkFrame(self.grid_frame,
            fg_color=T.CARD, corner_radius=10,
            border_width=1, border_color=T.BORDER)
        box.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(box,
            text=title,
            font=font(17,"bold"), text_color=T.TEXT
        ).pack(padx=34, pady=(28,6))
        ctk.CTkLabel(box,
            text=tr("Создайте новую сборку или измените поиск"),
            font=font(11), text_color=T.MUTED
        ).pack(padx=34, pady=(0,14))
        ctk.CTkButton(box,
            text=tr("Новая сборка"),
            image=self._ico_add,
            compound="left" if self._ico_add else "center",
            fg_color=T.ACCENT, hover_color=T.ACCENT_H,
            font=font(12,"bold"),
            command=self._open_create_dialog
        ).pack(padx=34, pady=(0,28))

    def _card_select(self, data: dict,
                     open_settings=False, delete=False):
        if delete:
            self.current_instance = data
            self._delete_instance()
            return
        self._select_instance(data)
        if open_settings:
            self._open_instance_settings()

    def _select_instance(self, data: dict):
        self.current_instance = data
        for c in self.cards:
            c.set_selected(c.data.get("name") == data.get("name"))

        self._sb_name.configure(text=data["name"])
        loader  = data.get("loader","Vanilla")
        version = data.get("version","")
        self._sb_sub.configure(text=f"{loader}  •  {version}")
        if hasattr(self, "_lbl_bottom_status"):
            self._lbl_bottom_status.configure(
                text=f"Выбрана: {data['name']} • {loader} {version} • RAM {effective_ram_mb(data)} МБ")

        # время игры
        pt = data.get("play_time", 0)
        if pt:
            h, m = divmod(pt//60, 60)
            self._sb_time.configure(text=f"Наиграно: {h} ч {m} мин")
        else:
            self._sb_time.configure(text=tr("Ещё не запускалась"))

        # иконка в сайдбаре
        ico = load_instance_icon(data["name"], (68,68))
        self._sb_icon.configure(image=ico)

        # содержимое сборки + проверка установки в фоне
        self._update_content_info(data)
        self._check_installed_async(data)

        cfg = Settings.load()
        cfg["selected_instance"] = data["name"]
        Settings.save(cfg)
        log.log(f"Выбрана сборка: {data['name']} [{loader} {version}]")

    def _on_search(self, *_): self._reload_instances()
    def _on_sort(self,  *_): self._reload_instances()

    def _refresh_versions_async(self):
        if self._versions_refreshing:
            return
        self._versions_refreshing = True
        self._refresh_dots = 0
        self._animate_refresh()                  # «Обновление версий...» с бегущими точками
        if hasattr(self, "_mc_version_badge"):
            self._mc_version_badge.configure(text="MC ...")

        def worker():
            ok, versions = refresh_minecraft_versions()
            self.after(0, self._on_versions_refreshed, ok, versions)

        threading.Thread(target=worker, daemon=True).start()

    # ── анимация кнопки «Обновить версии» ────────────────────
    def _animate_refresh(self):
        if not getattr(self, "_versions_refreshing", False):
            self._set_refresh_text(tr("Обновить версии"), True)
            self._refresh_job = None
            return
        self._refresh_dots = (getattr(self, "_refresh_dots", 0) + 1) % 4
        self._set_refresh_text(tr("Обновление версий") + "." * self._refresh_dots, False)
        self._refresh_job = self.after(350, self._animate_refresh)

    def _set_refresh_text(self, text: str, enabled: bool):
        btn = getattr(self, "_btn_refresh", None)
        if btn is None:
            return
        try:
            btn.configure(text=text, state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _on_versions_refreshed(self, ok: bool, versions: list):
        self._versions_refreshing = False
        job, self._refresh_job = getattr(self, "_refresh_job", None), None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._set_refresh_text(tr("Обновить версии"), True)
        latest = versions[0] if versions else default_minecraft_version()
        if hasattr(self, "_mc_version_badge"):
            self._mc_version_badge.configure(text=f"MC {latest}")
        if hasattr(self, "_library_stats"):
            self._reload_instances()
        if ok:
            log.log(f"Список версий Minecraft обновлён: актуальная {latest}")
        else:
            log.log("Не удалось обновить версии Minecraft, используется встроенный список", "WARN")

    # ────────────────────────────────────────────────────────
    # КНОПКИ ДЕЙСТВИЙ
    # ────────────────────────────────────────────────────────
    def _open_create_dialog(self):
        CreateInstanceDialog(self, on_created=self._on_instance_created)

    def _on_instance_created(self, data: dict):
        self._reload_instances(select_name=data["name"])

    def _open_instance_settings(self):
        if not self.current_instance:
            return
        InstanceSettingsDialog(self, self.current_instance,
                               on_saved=self._on_instance_saved)

    def _on_instance_saved(self, data: dict):
        self.current_instance = data
        self._reload_instances(select_name=data["name"])

    def _rename_instance(self):
        if not self.current_instance:
            return
        d = ctk.CTkInputDialog(text=tr("Новое название:"), title=tr("Переименовать"))
        new = d.get_input()
        if not new or new == self.current_instance["name"]:
            return
        try:
            InstanceMgr.rename(self.current_instance["name"], new)
            self._reload_instances(select_name=new)
        except Exception as e:
            messagebox.showerror(tr("Ошибка"), str(e))

    def _delete_instance(self):
        if not self.current_instance:
            return
        name = self.current_instance["name"]
        if not messagebox.askyesno(tr("Удаление"),
                f"Удалить сборку «{name}» со всеми файлами?\n"
                "Это действие необратимо."):
            return
        InstanceMgr.delete(name)
        self.current_instance = None
        self._sb_name.configure(text=tr("Выберите сборку"))
        self._sb_sub.configure(text="")
        self._sb_time.configure(text="")
        self._sb_icon.configure(image=load_icon("box_icon.png",(72,72)))
        if hasattr(self, "_lbl_bottom_status"):
            self._lbl_bottom_status.configure(text=tr("Выберите сборку для запуска"))
        self._reload_instances()

    # ────────────────────────────────────────────────────────
    # УСТАНОВКА
    # ────────────────────────────────────────────────────────
    def _install_instance(self):
        if not self.current_instance:
            messagebox.showwarning("SCL",tr("Выберите сборку"))
            return
        if self.game_running:
            messagebox.showwarning("SCL",tr("Нельзя устанавливать во время игры"))
            return

        inst = self._prepare_launch_instance(self.current_instance)
        self._installing = True
        self._last_progress = (0.0, tr("Подготовка..."))
        self._set_play_state("install")
        self._show_progress(True)
        self._progress.busy(tr("Подготовка..."))
        log.log(f"Начало установки: {inst['name']}")

        def worker():
            ok = CoreBridge.install(inst, self._progress_from_thread)
            self.after(0, self._on_install_done, ok)

        threading.Thread(target=worker, daemon=True).start()

    def _progress_from_thread(self, value: float, status: str):
        self._last_progress = (value, status)
        self.after(0, self._apply_progress, value, status)

    def _apply_progress(self, value: float, status: str):
        """Показывает прогресс: неизвестен процент — бегущая полоса, иначе точный."""
        try:
            self._progress.busy_if_unknown(value, status)
        except Exception:
            pass

    def _show_progress(self, show: bool):
        if show:
            self.grid_frame.pack_forget()
            self._progress.pack(fill="both", expand=True, padx=30, pady=30)
        else:
            self._progress.pack_forget()
            self.grid_frame.pack(fill="both", expand=True, padx=10, pady=4)

    def _on_install_done(self, ok: bool):
        self._installing = False
        self._show_progress(False)
        self._set_play_state("play")
        self._reload_instances()
        if ok:
            log.log("Установка завершена успешно")
            messagebox.showinfo("SCL",tr( "Установка завершена!\nТеперь можно запускать игру."))
        else:
            err = CoreBridge.get_last_error() or "неизвестная ошибка"
            log.log(f"Установка не выполнена: {err}", "ERROR")
            messagebox.showerror("SCL",
                "Не удалось установить сборку.\n\n"
                f"{err}\n\n"
                "Подробности — в окне «Консоль» (кнопка в верхней панели).")

    # ────────────────────────────────────────────────────────
    # ЗАПУСК ИГРЫ
    # ────────────────────────────────────────────────────────
    def _toggle_game(self):
        if self.game_running:
            self._stop_game()
        else:
            self._play_game()

    def _play_instance(self, data: dict):
        self._select_instance(data)
        self._play_game()

    def _prepare_launch_instance(self, data: dict) -> dict:
        inst = data.copy()
        inst["ram"] = effective_ram_mb(inst)
        if not inst.get("java_path"):
            inst["java_path"] = self.cfg.get("java_path", "")
        if not inst.get("jvm_args"):
            inst["jvm_args"] = self.cfg.get("jvm_args", "")
        # автоскачивание Java нужной версии (выключается в настройках)
        inst["auto_java"] = bool(self.cfg.get("auto_java", True))
        # язык игры = язык лаунчера (по умолчанию — язык системы)
        inst["ui_language"]        = i18n.get_language()
        inst["sync_game_language"] = bool(self.cfg.get("sync_game_language", True))
        return inst

    def _play_game(self):
        if not self.current_instance:
            messagebox.showwarning("SCL",tr("Выберите сборку"))
            return
        if self.game_running:
            return

        inst = self._prepare_launch_instance(self.current_instance)
        if not self._memory_check(inst):
            return
        if not CoreBridge.is_installed(inst):
            self._install_then_play(inst)
            return

        self._launch_installed(inst)

    def _install_then_play(self, inst: dict):
        self._installing = True
        self._last_progress = (0.0, tr("Игра не установлена — начинаю установку..."))
        self._show_progress(True)
        self._progress.busy(tr("Игра не установлена — начинаю установку..."))
        self._set_play_state("install")
        log.log(f"Автоустановка перед запуском: {inst['name']} [{inst.get('loader','')} {inst.get('version','')}]")

        def worker():
            ok = CoreBridge.install(inst, self._progress_from_thread)
            self.after(0, self._on_auto_install_done, ok, inst)

        threading.Thread(target=worker, daemon=True).start()

    def _on_auto_install_done(self, ok: bool, inst: dict):
        self._installing = False
        self._show_progress(False)
        self._set_play_state("play")

        if not ok:
            err = CoreBridge.get_last_error() or "неизвестная ошибка"
            log.log(f"Автоустановка не удалась: {err}", "ERROR")
            messagebox.showerror("SCL",
                "Не удалось установить игру автоматически.\n\n"
                f"{err}\n\n"
                "Подробности — в окне «Консоль».")
            return

        log.log("Автоустановка завершена, запускаю игру")
        self._launch_installed(inst)

    def _memory_check(self, inst: dict) -> bool:
        """
        Не запускаем игру, если системе не хватает памяти: вместо загадочного
        «игра остановлена» сразу объясняем причину и что делать.
        """
        wanted = _safe_int(inst.get("ram"), 4096)
        safe   = CoreBridge.safe_ram_mb(wanted)
        if safe >= 1024:
            if safe != wanted:
                log.log(f"RAM сборки уменьшена с {wanted} до {safe} МБ "
                        f"(мало свободной памяти/подкачки)", "WARN")
                inst["ram"] = safe
            return True

        hint = CoreBridge.memory_hint()
        log.log(f"Мало свободной памяти/подкачки — нужно решение владельца. {hint}", "WARN")
        drive, drive_free = self._best_free_drive()
        text = ("Сейчас системе не хватает памяти, чтобы запустить Minecraft,\n"
                "поэтому игра закрылась бы через пару секунд.\n\n"
                f"Запрошено памяти: {wanted} МБ\n"
                f"Реально можно выделить: {safe} МБ\n")
        if hint:
            text += f"Система: {hint}\n"
        text += ("\nЧто делать (по порядку):\n"
                 "1. Увеличить файл подкачки Windows — это главная причина.\n"
                 "   Важно: файл подкачки должен лежать на диске, где есть место\n"
                 f"   (свободнее всего — {drive}, там {drive_free:.1f} ГБ).\n"
                 "   Параметры → Система → О системе → Дополнительные параметры системы →\n"
                 "   Быстродействие: Параметры → Дополнительно → Виртуальная память → Изменить.\n"
                 f"   Снять галочку «Автоматически», диск {drive}, «Задать» 8192–16384 МБ,\n"
                 "   «Файл подкачки на диске C:» можно отключить, затем перезагрузка.\n"
                 "2. Закрыть тяжёлые программы (браузер, VS Code, другие лаунчеры).\n"
                 "3. Уменьшить память сборки в её настройках.\n\n"
                 "Открыть окно настроек виртуальной памяти сейчас?")
        # ── принудительный запуск (настройка или уже подтверждённый в этой сессии) ──
        if self.cfg.get("force_launch") or self._force_launch_used:
            inst["ram"] = safe
            self._force_launch_used = True
            log.log(tr("Принудительный запуск при нехватке памяти (RAM {0} МБ)", safe), "WARN")
            return True

        if messagebox.askyesno(tr("Мало памяти для запуска"), text):
            self._open_pagefile_settings()
            log.log("Запуск отменён: мало памяти/подкачки — владелец пошёл менять настройки",
                    "ERROR")
            return False

        # ответ «Нет» — предлагаем всё равно запустить (на свой риск)
        if messagebox.askyesno(tr("Запустить всё равно"),
                tr("Запустить игру всё равно?\n\nПамяти мало ({0} МБ вместо {1} МБ) — "
                   "игра может зависнуть или вылететь.\nЛучше увеличить файл подкачки "
                   "и перезапустить лаунчер.", safe, wanted)):
            inst["ram"] = safe
            self._force_launch_used = True
            log.log(tr("Принудительный запуск при нехватке памяти (RAM {0} МБ)", safe), "WARN")
            return True
        log.log("Запуск отменён: мало памяти/подкачки", "ERROR")
        return False

    def _best_free_drive(self) -> tuple[str, float]:
        """Самый свободный диск — файл подкачки и игру лучше держать на нём."""
        best      = os.path.splitdrive(ROOT)[0] or "?"
        best_free = disk_free_gb(ROOT)
        for letter in DRIVE_ORDER:
            drive = f"{letter}:\\"
            if not os.path.exists(drive):
                continue
            free = disk_free_gb(drive)
            if free > best_free:
                best, best_free = f"{letter}:", free
        return best, best_free

    def _open_pagefile_settings(self):
        """Открывает системное окно «Быстродействие» (там кнопка виртуальной памяти)."""
        drive, free = self._best_free_drive()
        try:
            subprocess.Popen(["SystemPropertiesPerformance.exe"])
            log.log("Открыто окно «Быстродействие»: вкладка «Дополнительно» → "
                    f"Виртуальная память → Изменить (рекомендуемый диск: {drive}, "
                    f"свободно {free:.1f} ГБ)")
        except Exception as e:
            log.log(f"Не удалось открыть настройки быстродействия: {e}", "WARN")
            messagebox.showinfo("SCL",
                "Откройте вручную: Win+R → SystemPropertiesPerformance.exe\n"
                "вкладка «Дополнительно» → «Виртуальная память» → Изменить\n"
                f"Диск для файла подкачки лучше выбрать {drive} "
                f"(свободно {free:.1f} ГБ)")

    def _launch_installed(self, inst: dict):
        acc = self.current_account
        log.log(f"Запуск: {inst['name']} от {acc['name']}")

        # запускаем в потоке: подбор/скачивание Java и старт Java-процесса
        self._set_play_state("busy")

        def worker():
            proc = CoreBridge.launch(inst, acc)
            self.after(0, self._on_launch_result, inst, proc)

        threading.Thread(target=worker, daemon=True).start()

    def _on_launch_result(self, inst: dict, proc):
        self._btn_play.configure(state="normal")

        if proc is None:
            err = CoreBridge.get_last_error() or "не удалось запустить Java-процесс"
            log.log(f"Запуск не выполнен: {err}", "ERROR")
            self._set_play_state("play")
            messagebox.showerror("SCL",
                "Не удалось запустить игру.\n\n"
                f"{err}\n\n"
                f"Сборка:  {inst['name']}\n"
                f"Версия:  {inst.get('loader','')} {inst.get('version','')}\n\n"
                "Подробности — в окне «Консоль».")
            return

        self.game_proc    = proc
        self.game_running = True
        self.game_started_at = time.monotonic()
        self.game_tail.clear()
        self._set_play_state("running")
        self._discord_start(inst)

        import datetime
        inst["last_played"] = datetime.datetime.now().isoformat(timespec="seconds")
        InstanceMgr.save_cfg(inst)

        self._pump_output(proc, inst)
        threading.Thread(target=self._watch_proc, args=(proc,), daemon=True).start()

        if self.cfg.get("close_on_launch"):
            self.iconify()

    def _pump_output(self, proc, inst: dict):
        """Читает вывод игры и складывает его в окно «Консоль» + файл сборки."""
        game_log = os.path.join(INSTANCES_DIR, inst["name"], "logs", "launcher-game.log")
        try:
            os.makedirs(os.path.dirname(game_log), exist_ok=True)
        except Exception:
            game_log = None

        def reader():
            try:
                for raw in iter(proc.stdout.readline, ""):
                    line = (raw or "").rstrip()
                    if not line:
                        continue
                    log.log(f"[GAME] {line}")
                    if len(self.game_tail) >= 20:      # держим хвост для диагностики падений
                        del self.game_tail[0]
                    self.game_tail.append(line)
                    if game_log:
                        try:
                            with open(game_log, "a", encoding="utf-8") as f:
                                f.write(line + "\n")
                        except Exception:
                            pass
            except Exception as e:
                log.log(f"Чтение вывода игры прервано: {e}", "WARN")
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

        self.game_reader = threading.Thread(target=reader, daemon=True)
        self.game_reader.start()

    def _watch_proc(self, proc):
        code = proc.wait()
        ran  = time.monotonic() - (self.game_started_at or time.monotonic())
        self.after(0, self._game_finished, code, ran)

    def _game_finished(self, code: int, ran_sec: float):
        """Игра завершилась: если упала сразу — объясняем причину, а не просто «остановлена»."""
        tail = "\n".join(self.game_tail)
        if code != 0 and ran_sec < 25:
            kind, explain = CoreBridge.classify_crash(tail)
            log.log(f"Игра упала: код {code}, прожила {ran_sec:.0f} с. {explain}", "ERROR")
            self._stop_game()
            self._show_crash_dialog(kind, explain, tail, code)
            return
        if code != 0:
            log.log(f"Игра завершилась с кодом {code}", "WARN")
        self._stop_game()

    def _show_crash_dialog(self, kind: str, explain: str, tail: str, code: int):
        """Понятное окно о причине падения + подсказки, что делать."""
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass

        short = "\n".join((tail or "").splitlines()[-6:]) or "(вывод пуст)"
        text  = f"{explain}\n\nСборка: {self.current_instance['name'] if self.current_instance else '?'}" \
                f"\nКод выхода: {code}\n\nПоследние строки игры:\n{short}"

        if kind == "memory":
            hint = CoreBridge.memory_hint()
            safe = CoreBridge.safe_ram_mb(effective_ram_mb(self.current_instance))
            if hint:
                text += f"\n\nСистема: {hint}"
            text += ("\n\nЧто делать:\n"
                     "1. Уменьшить память сборки (сейчас можно поставить "
                     f"{max(1024, safe)} МБ).\n"
                     "2. Увеличить файл подкачки Windows: Параметры → Система → О системе →\n"
                     "   Дополнительные параметры системы → Быстродействие → Виртуальная память\n"
                     "   (рекомендуется 1.5–2× от объёма ОЗУ).\n"
                     "3. Закрыть лишние программы (браузер, VS Code, другие лаунчеры).")
            if messagebox.askyesno(tr("Игре не хватило памяти"),
                                   text + "\n\nУменьшить память сборки и попробовать снова?"):
                self._reduce_ram_and_retry()
            return

        messagebox.showerror(tr("Игра не запустилась"), text)

    def _reduce_ram_and_retry(self):
        """Уменьшает RAM сборки до безопасной и пробует запустить заново."""
        if not self.current_instance:
            return
        current = effective_ram_mb(self.current_instance)
        new_ram = max(1024, min(current - 512, 2048)) if current > 1536 else 1024

        updated = dict(self.current_instance)
        updated["ram"] = new_ram
        try:
            InstanceMgr.save_cfg(updated)
        except Exception as e:
            log.log(f"Не удалось сохранить RAM сборки: {e}", "WARN")

        self.cfg["ram"] = new_ram
        Settings.save(self.cfg)
        log.log(f"Память сборки уменьшена до {new_ram} МБ — пробую запустить снова")

        self._reload_instances(select_name=updated["name"])
        self.after(500, self._play_game)

    # ────────────────────────────────────────────────────────
    # DISCORD RICH PRESENCE
    # ────────────────────────────────────────────────────────
    def _discord_start(self, inst: dict):
        """Показывает в Discord, во что играем (если включено в настройках)."""
        if not self.cfg.get("discord_rpc"):
            return
        if discord_rpc_mod is None:
            log.log("Discord RPC: модуль core/discord_rpc.py не найден", "WARN")
            return

        self._discord_stop()
        join_cb = self._on_discord_join if self.cfg.get("discord_join") else None
        try:
            rpc = discord_rpc_mod.DiscordRPC(
                str(self.cfg.get("discord_client_id") or ""),
                join_callback=join_cb, logger=log.log)
            if not rpc.start():
                return
            self._rpc = rpc
        except Exception as e:
            log.log(f"Discord RPC не запустился: {e}", "WARN")
            self._rpc = None
            return

        fields = {
            "details":     tr("{0} {1}", inst.get("loader", "Minecraft"),
                              inst.get("version", "")),
            "state":       tr("Сборка: {0}", inst.get("name", "")),
            "start":       int(time.time()),
            "large_image": "logo",
            "large_text":  APP_NAME,
        }
        nickname = str((self.current_account or {}).get("name") or "")
        if nickname:
            fields["small_text"] = nickname
        if self.cfg.get("discord_join"):
            # благодаря party/join_secret друзья видят кнопку «Присоединиться»
            fields["party_id"]     = f"scl-{os.getpid()}"
            fields["party_size"]   = [1, 8]
            fields["join_secret"]  = f"join-{os.getpid()}"
        self._rpc.set_activity(**fields)
        log.log(f"Discord RPC: статус включён ({inst.get('loader')} {inst.get('version')})")

    def _discord_stop(self):
        """Выключает статус Discord (и закрывает соединение)."""
        rpc, self._rpc = self._rpc, None
        if rpc is None:
            return
        try:
            rpc.stop()
        except Exception:
            pass

    def _on_discord_join(self, secret: str):
        """
        Друг нажал «Присоединиться» в Discord. Если у сборки уже указан сервер —
        предлагаем подключиться, иначе спрашиваем адрес и запоминаем его.
        """
        log.log(f"Discord: приглашение присоединиться ({str(secret)[:8]})")
        inst = self.current_instance or {}
        server = str(inst.get("server") or "").strip()
        if server:
            self.after(0, lambda: self._confirm_join(server))
        else:
            self.after(0, self._ask_join_server)

    def _ask_join_server(self):
        """Спрашиваем адрес сервера для подключения по приглашению Discord."""
        if not self.current_instance:
            return
        from tkinter import simpledialog
        server = simpledialog.askstring(
            "Discord", tr("Адрес сервера для присоединения (например play.example.com):"),
            parent=self)
        server = (server or "").strip()
        if not server:
            return
        inst = self.current_instance.copy()
        inst["server"] = server
        InstanceMgr.save_cfg(inst)
        log.log(f"Адрес сервера для приглашений сохранён: {server}")
        self._confirm_join(server)

    def _confirm_join(self, server: str):
        if not messagebox.askyesno("SCL",
                tr("Друг приглашает присоединиться.\n\nПодключиться к серверу {0}?",
                   server)):
            return
        log.log(f"Подключение к серверу из приглашения Discord: {server}")
        self._play_game()

    def _stop_game(self):
        if not self.game_running:
            return
        log.log("Игра остановлена")
        self.game_running = False
        self.game_proc    = None
        self._discord_stop()
        self._set_play_state("play")
        if self.cfg.get("close_on_launch"):
            self.deiconify()

    # ────────────────────────────────────────────────────────
    # ДИАЛОГИ
    # ────────────────────────────────────────────────────────
    def _open_accounts(self):
        AccountsDialog(self, on_select=self._on_account_selected)

    def _on_account_selected(self, acc: dict):
        self.current_account = acc
        ico = getattr(self, "_ico_user", None)
        self._btn_account.configure(text=f"  {acc['name']}" if ico else acc["name"])
        self._lbl_acc_type.configure(
            text=f"({acc.get('type','offline')})")
        log.log(f"Выбран аккаунт: {acc['name']}")

    def _open_global_settings(self):
        GlobalSettingsDialog(self, on_saved=self._on_settings_saved)

    def _on_settings_saved(self, cfg: dict):
        self.cfg = cfg

        # язык интерфейса применяется сразу: «Авто» = язык системы
        lang = str(cfg.get("language") or "")
        if cfg.get("language_auto", True) or lang not in i18n.LANGUAGES:
            lang = i18n.detect_system_language()
            cfg["language"] = lang
        i18n.set_language(lang or i18n.DEFAULT_LANGUAGE)

        # папка сборок могла переехать на другой диск — применяем сразу
        new_dir = str(cfg.get("instances_dir") or "").strip() or INSTANCES_DIR
        self._apply_instances_dir(new_dir)

        theme_changed = cfg.get("theme") != T.NAME
        T.apply(cfg.get("theme", DEFAULT_THEME))
        self._rebuild_ui()        # тема и цвета применяются сразу, перезапуск не нужен
        log.log(f"Настройки сохранены. Тема: {cfg.get('theme')}")
        if not theme_changed:
            self._set_status(tr("Настройки сохранены"))

    def _apply_instances_dir(self, new_dir: str, move: bool = True):
        """Переключает папку сборок; при move=True предлагает перенести существующие."""
        global INSTANCES_DIR
        new_dir = os.path.abspath(os.path.expanduser(str(new_dir)))
        old_dir = INSTANCES_DIR
        if new_dir == old_dir:
            return
        INSTANCES_DIR = new_dir
        try:
            os.makedirs(INSTANCES_DIR, exist_ok=True)
            log.log(f"Папка сборок: {INSTANCES_DIR}")
        except Exception as e:
            log.log(f"Не удалось создать папку сборок: {e}", "ERROR")
            INSTANCES_DIR = old_dir
            return
        if move:
            self._offer_move_instances(old_dir, INSTANCES_DIR)

    def _first_run_folder(self):
        """
        Первый запуск: спрашиваем владельца, где держать сборки игры.
        По умолчанию предлагаем папку рядом с лаунчером (там, где он лежит).
        """
        if self.cfg.get("folder_chosen"):
            return

        default_dir = pick_instances_dir()
        answer = messagebox.askyesnocancel(
            tr("Куда ставить сборки?"),
            tr("Игра, моды, миры и Java будут храниться в этой папке.\n\n"
               "«Да» — рядом с лаунчером:\n{0}\n\n"
               "«Нет» — выбрать другую папку\n"
               "«Отмена» — решить позже в «Настройках лаунчера»", default_dir))
        if answer is None:
            return

        new_dir = default_dir
        if answer is False:
            chosen = filedialog.askdirectory(
                title=tr("Папка для сборок Minecraft"),
                initialdir=INSTANCES_DIR)
            if not chosen:
                return
            new_dir = os.path.abspath(os.path.normpath(chosen))

        if os.path.abspath(new_dir) != os.path.abspath(INSTANCES_DIR):
            self._apply_instances_dir(new_dir, move=True)
        else:
            try:
                os.makedirs(INSTANCES_DIR, exist_ok=True)
            except Exception:
                pass

        self.cfg["folder_chosen"] = True
        self.cfg["instances_dir"] = INSTANCES_DIR
        Settings.save(self.cfg)
        self._rebuild_ui()

    def _open_about(self):
        AboutDialog(self)

    def _offer_move_instances(self, old_dir: str, new_dir: str):
        """
        Владелец сменил папку сборок — предлагаем перенести туда уже созданные
        сборки, чтобы игра и моды лежали в одном выбранном месте.
        """
        try:
            same = os.path.abspath(old_dir) == os.path.abspath(new_dir)
        except Exception:
            same = False
        if same or not os.path.isdir(old_dir):
            return

        try:
            names = [d for d in os.listdir(old_dir)
                     if os.path.isdir(os.path.join(old_dir, d))
                     and os.path.exists(os.path.join(old_dir, d, "instance.json"))]
        except Exception as e:
            log.log(f"Не удалось прочитать старую папку сборок: {e}", "WARN")
            return
        if not names:
            return

        if self.game_running:
            messagebox.showwarning("SCL",
                "Игра запущена, поэтому сборки не переносятся.\n\n"
                f"Новые сборки будут создаваться здесь:\n{new_dir}\n\n"
                f"Старые остались в:\n{old_dir}")
            return

        if not messagebox.askyesno("SCL",
                f"Перенести существующие сборки ({len(names)}) в новую папку?\n\n"
                f"Откуда: {old_dir}\nКуда:   {new_dir}\n\n"
                "(переносятся папки целиком вместе с модами и мирами)"):
            return

        moved, errors = 0, []
        for name in names:
            src = os.path.join(old_dir, name)
            dst = os.path.join(new_dir, name)
            try:
                if os.path.exists(dst):
                    errors.append(f"{name} — уже есть в новой папке")
                    continue
                shutil.move(src, dst)
                moved += 1
            except Exception as e:
                errors.append(f"{name} — {e}")

        log.log(f"Перенос сборок завершён: перенесено {moved}"
                + (f", с ошибками {len(errors)}" if errors else ""))
        if errors:
            messagebox.showwarning("SCL",
                f"Перенесено сборок: {moved}\n\nНе удалось перенести:\n"
                + "\n".join(errors))
        else:
            messagebox.showinfo("SCL",
                f"Перенесено сборок: {moved}.\nТеперь всё лежит в:\n{new_dir}")

    # ────────────────────────────────────────────────────────
    # ЭКСПОРТ / ИМПОРТ СБОРКИ (один ZIP-файл для друга)
    # ────────────────────────────────────────────────────────
    def _export_instance(self, inst: dict | None = None):
        inst = inst or self.current_instance
        if not inst:
            messagebox.showwarning("SCL",tr( "Выберите сборку"))
            return
        if self.game_running:
            messagebox.showwarning("SCL",tr( "Нельзя упаковывать сборку во время игры"))
            return

        path = filedialog.asksaveasfilename(
            title=tr("Сохранить сборку в файл"),
            defaultextension=".zip",
            initialfile=f"{inst['name']}.zip",
            filetypes=[(tr("Архив сборки (этот лаунчер)"), "*.zip"),
                       (tr("Модпак Modrinth/Prism (.mrpack)"), "*.mrpack")])
        if not path:
            return
        is_mrpack = path.lower().endswith(".mrpack")

        self._show_progress(True)
        self._progress.update(0.0, tr("Упаковка сборки..."))
        log.log(f"Экспорт сборки: {inst['name']} → {path}")

        def worker():
            if is_mrpack:
                ok = CoreBridge.export_mrpack(inst, path, self._progress_from_thread)
            else:
                ok = CoreBridge.export_instance(inst, path, self._progress_from_thread)
            self.after(0, self._on_export_done, ok, path, inst)

        threading.Thread(target=worker, daemon=True).start()

    def _on_export_done(self, ok: bool, path: str, inst: dict):
        self._show_progress(False)
        if not ok:
            err = CoreBridge.get_last_error() or "неизвестная ошибка"
            log.log(f"Экспорт сборки не удался: {err}", "ERROR")
            messagebox.showerror("SCL", f"Не удалось собрать файл сборки.\n\n{err}")
            return
        try:
            size = os.path.getsize(path) / (1024 * 1024)
        except OSError:
            size = 0.0
        log.log(f"Сборка упакована: {path} ({size:.1f} МБ)")
        messagebox.showinfo("SCL",
            f"Сборка «{inst['name']}» упакована в файл:\n{path}\n\n"
            f"Размер: {size:.1f} МБ\n\n"
            "Передайте файл другу — у себя он распакует его кнопкой «Импорт сборки». "
            "Сама игра, библиотеки и Java скачаются у него автоматически "
            "(поэтому файл маленький).")

    def _import_instance(self):
        if self.game_running:
            messagebox.showwarning("SCL",tr( "Нельзя импортировать сборку во время игры"))
            return

        path = filedialog.askopenfilename(
            title=tr("Выберите файл сборки"),
            filetypes=[(tr("Архивы сборок"), "*.zip *.mrpack")])
        if not path:
            return

        self._show_progress(True)
        self._progress.update(0.0,tr( "Распаковка сборки..."))
        log.log(f"Импорт сборки из {path}")

        def worker():
            name = CoreBridge.import_instance(path, "", self._progress_from_thread)
            self.after(0, self._on_import_done, name)

        threading.Thread(target=worker, daemon=True).start()

    def _on_import_done(self, name: str):
        self._show_progress(False)
        if not name:
            err = CoreBridge.get_last_error() or "файл повреждён или это не архив сборки"
            log.log(f"Импорт сборки не удался: {err}", "ERROR")
            messagebox.showerror("SCL", f"Не удалось импортировать сборку.\n\n{err}")
            return
        self._reload_instances(select_name=name)
        log.log(f"Сборка импортирована: {name}")
        messagebox.showinfo("SCL",
            f"Сборка «{name}» добавлена.\n\n"
            "Проверьте версию Minecraft в «Настройках сборки» и нажмите «Установить» — "
            "игра, библиотеки и Java докачаются автоматически.")

    def _open_console(self):
        if self.console_win and self.console_win.winfo_exists():
            self.console_win.focus()
            return
        self.console_win = ConsoleWindow(self)

    # ────────────────────────────────────────────────────────
    # ТЕМА / ИНТЕРФЕЙС
    # ────────────────────────────────────────────────────────
    def _apply_theme(self, name: str, save: bool = True):
        """Мгновенно применяет тему ко всему окну (без перезапуска)."""
        if not name or name not in THEMES:
            return
        T.apply(name)
        if save:
            self.cfg["theme"] = name
            Settings.save(self.cfg)
        self._rebuild_ui()
        log.log(f"Тема применена: {name}")

    def _rebuild_ui(self):
        """Пересобирает окно заново с текущими цветами темы."""
        selected = (self.current_instance or {}).get("name")
        for frame in (getattr(self, "topbar", None), getattr(self, "body", None)):
            try:
                if frame is not None:
                    frame.destroy()
            except Exception:
                pass

        self.cards.clear()
        self.configure(fg_color=T.BG)

        self._preload_icons()        # иконки перекрашиваются под новую тему
        self._build_ui()
        self._reload_instances(select_name=selected)
        self._update_env_async()              # строка Python/Java заполняется заново
        if self._installing:
            # смена темы во время установки: остаёмся на экране прогресса
            self._show_progress(True)
            try:
                self._apply_progress(*self._last_progress)
            except Exception:
                pass
            self._set_play_state("install")
        else:
            self._set_play_state("running" if self.game_running else "play")

    def _set_status(self, text: str):
        if hasattr(self, "_lbl_bottom_status"):
            self._lbl_bottom_status.configure(text=text)

    def _update_env_async(self):
        """Показывает в нижней панели версии Python и Java (в фоне, чтобы не тормозить)."""
        def worker():
            java = ""
            try:
                core = CoreBridge._get_core()
                if hasattr(core, "get_java_path"):
                    java = core.get_java_path(self._prepare_launch_instance(
                        self.current_instance or {"name": "Vanilla"}))
            except Exception:
                java = ""

            if java and os.path.isfile(java):
                folder = os.path.dirname(java)
                if os.path.basename(folder).lower() in ("bin", ""):
                    folder = os.path.dirname(folder)
                label = os.path.basename(folder) or folder
                if len(label) > 30:
                    label = label[:29] + "…"
            else:
                label = tr("не найдена")

            mem_text = ""
            try:
                core = CoreBridge._get_core()
                info = core.system_memory()
                if info.get("total_mb"):
                    mem_text = tr("  •  ОЗУ свободно {0} ГБ, подкачка/commit {1} ГБ",
                                  info['avail_mb'] // 1024,
                                  info['commit_avail_mb'] // 1024)
                    if info["commit_total_mb"] - info["total_mb"] < 2048:
                        mem_text += tr("  (файл подкачки мал!)")
            except Exception:
                mem_text = ""

            text = tr("Python {0}  •  Java {1}{2}",
                      platform.python_version(), label, mem_text)
            self.after(0, self._set_env_text, text)

        threading.Thread(target=worker, daemon=True).start()

    def _set_env_text(self, text: str):
        if hasattr(self, "_lbl_env"):
            try:
                self._lbl_env.configure(text=text)
            except Exception:
                pass

    def _open_mods_manager(self):
        """Окно менеджера модов (поиск и установка с Modrinth)."""
        if not self.current_instance:
            messagebox.showwarning("SCL", tr("Выберите сборку"))
            return
        ModsDialog(self, self, self.current_instance)

    def _open_backups(self):
        """Окно бэкапов миров выбранной сборки."""
        if not self.current_instance:
            messagebox.showwarning("SCL", tr("Выберите сборку"))
            return
        BackupsDialog(self, self, self.current_instance)

    def _open_mods_folder(self):
        if not self.current_instance:
            open_folder(INSTANCES_DIR)
            return
        mods = os.path.join(InstanceMgr.path(self.current_instance["name"]), "mods")
        try:
            os.makedirs(mods, exist_ok=True)
        except Exception:
            pass
        open_folder(mods)

    def _update_content_info(self, data: dict):
        """Сколько модов / ресурспаков / шейдеров / миров лежит в сборке."""
        path = InstanceMgr.path(data.get("name", ""))
        parts = []
        for folder, label in (("mods", tr("моды")), ("resourcepacks", tr("ресурспаки")),
                              ("shaderpacks", tr("шейдеры")), ("saves", tr("миры"))):
            try:
                count = len([f for f in os.listdir(os.path.join(path, folder))
                             if not f.startswith(".")])
            except Exception:
                count = 0
            if count:
                parts.append(f"{label}: {count}")
        text = " • ".join(parts) if parts else tr("папки сборки пустые")
        if hasattr(self, "_sb_content"):
            self._sb_content.configure(text=text)

    def _check_installed_async(self, data: dict):
        """Проверяет установку версии в фоне и обновляет карточку."""
        if self._installing:
            return                      # во время установки статус ещё не достоверный
        name = data.get("name")

        def worker():
            try:
                installed = CoreBridge.is_installed(data)
            except Exception:
                installed = False
            self.after(0, self._on_installed_checked, name, installed)

        threading.Thread(target=worker, daemon=True).start()

    def _on_installed_checked(self, name: str, installed: bool):
        if self._installing:
            return                      # не показываем «установлено», пока идёт установка
        for card in self.cards:
            if card.data.get("name") == name:
                card.set_installed(installed)
                break
        if (not installed and self.current_instance
                and self.current_instance.get("name") == name):
            self._set_status(tr("Сборка не установлена — нажмите «Играть», чтобы скачать"))

    # ────────────────────────────────────────────────────────
    # ЗАКРЫТИЕ
    # ────────────────────────────────────────────────────────
    def on_close(self):
        if self.game_running:
            if not messagebox.askyesno(tr("Выход"),tr(
                    "Игра запущена. Всё равно закрыть лаунчер?")):
                return
            if self.game_proc:
                try: self.game_proc.terminate()
                except Exception: pass

        cfg = Settings.load()
        cfg["window_width"]  = self.winfo_width()
        cfg["window_height"] = self.winfo_height()
        Settings.save(cfg)
        self._discord_stop()
        self.destroy()


# ─────────────────────────────────────────────────────────────
# ENSURE DATA
# ─────────────────────────────────────────────────────────────
def ensure_default_data():
    cfg = Settings.load()
    Settings.save(cfg)
    AccountMgr.save(AccountMgr.load())
    if not InstanceMgr.load_all():
        try:
            InstanceMgr.create("Vanilla", default_minecraft_version(), "Vanilla")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        ensure_default_data()
        app = App()
        app.protocol("WM_DELETE_WINDOW", app.on_close)
        app.mainloop()
    except Exception as exc:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror(tr("Критическая ошибка"), str(exc))
        raise
