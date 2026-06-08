"""
Simple Craft Launcher  v3.0
============================
Главный файл UI-лаунчера.
Вся игровая логика (скачивание, запуск Minecraft) делегируется в:
    core/launcher_core.py   <-- будет реализован отдельно
"""

import os, sys, json, shutil, platform, subprocess, threading, webbrowser
import tkinter as tk
from tkinter import messagebox, colorchooser

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
    
    for pip_name, mod_name in packages.items():
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(pip_name)
            
    if missing:
        print(f"[SCL] Установка отсутствующих библиотек: {missing}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing, "-q"])
        except Exception as e:
            # Если pip упал, покажем красивое окошко вместо тихого краша
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Ошибка окружения", 
                f"Не удалось автоматически установить нужные библиотеки: {missing}\n\n"
                f"Лог ошибки: {e}\n\n"
                f"Пожалуйста, откройте консоль (cmd) и введите вручную:\n"
                f"pip install {' '.join(missing)}")
            sys.exit(1)

_install_requirements()

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

# ─────────────────────────────────────────────────────────────
# ПУТИ
# ─────────────────────────────────────────────────────────────
ROOT          = os.path.dirname(os.path.abspath(__file__))
DATA_DIR      = os.path.join(ROOT, "data")
INSTANCES_DIR = os.path.join(ROOT, "instances")
CORE_DIR      = os.path.join(ROOT, "core")
ASSETS_IMG    = os.path.join(ROOT, "assets", "images")
ASSETS_FONTS  = os.path.join(ROOT, "assets", "fonts")

for d in (DATA_DIR, INSTANCES_DIR, CORE_DIR):
    os.makedirs(d, exist_ok=True)

def asset(rel: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(ROOT, rel)

# ─────────────────────────────────────────────────────────────
# ВЕРСИИ MINECRAFT (список для UI)
# ─────────────────────────────────────────────────────────────
MOJANG_VERSION_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
DEFAULT_MINECRAFT_VERSIONS = [
    "26.1.2", "26.1.1", "26.1",
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
MINECRAFT_VERSIONS = DEFAULT_MINECRAFT_VERSIONS.copy()

def default_minecraft_version() -> str:
    return MINECRAFT_VERSIONS[0] if MINECRAFT_VERSIONS else "26.1.2"

LOADERS = ["Vanilla", "Fabric", "Forge", "NeoForge", "Quilt"]

# ─────────────────────────────────────────────────────────────
# ТЕМЫ
# ─────────────────────────────────────────────────────────────
THEMES = {
    "Dark Slate": {
        "BG": "#111318", "PANEL": "#1a1d24", "CARD": "#22262f",
        "CARD_HOVER": "#2b303b", "CARD_SEL": "#1e3a5f", "CARD_BORDER": "#3b82f6",
        "TEXT": "#e2e8f0", "MUTED": "#94a3b8",
        "ACCENT": "#3b82f6", "ACCENT_H": "#2563eb",
        "RED": "#ef4444", "RED_H": "#dc2626", "RED_D": "#7f1d1d",
        "GREEN": "#22c55e", "MODE": "dark",
    },
    "AMOLED": {
        "BG": "#000000", "PANEL": "#0a0a0a", "CARD": "#111111",
        "CARD_HOVER": "#1a1a1a", "CARD_SEL": "#001a40", "CARD_BORDER": "#3b82f6",
        "TEXT": "#ffffff", "MUTED": "#888888",
        "ACCENT": "#3b82f6", "ACCENT_H": "#2563eb",
        "RED": "#ef4444", "RED_H": "#dc2626", "RED_D": "#7f1d1d",
        "GREEN": "#22c55e", "MODE": "dark",
    },
    "Midnight": {
        "BG": "#0d1117", "PANEL": "#161b22", "CARD": "#21262d",
        "CARD_HOVER": "#30363d", "CARD_SEL": "#1c2b3a", "CARD_BORDER": "#58a6ff",
        "TEXT": "#c9d1d9", "MUTED": "#8b949e",
        "ACCENT": "#58a6ff", "ACCENT_H": "#388bfd",
        "RED": "#f85149", "RED_H": "#da3633", "RED_D": "#6e1b18",
        "GREEN": "#3fb950", "MODE": "dark",
    },
    "Forest": {
        "BG": "#0f1a0f", "PANEL": "#162216", "CARD": "#1e2d1e",
        "CARD_HOVER": "#253825", "CARD_SEL": "#1a3a1a", "CARD_BORDER": "#4ade80",
        "TEXT": "#d1fae5", "MUTED": "#6ee7b7",
        "ACCENT": "#4ade80", "ACCENT_H": "#22c55e",
        "RED": "#ef4444", "RED_H": "#dc2626", "RED_D": "#7f1d1d",
        "GREEN": "#4ade80", "MODE": "dark",
    },
    "Light": {
        "BG": "#f1f5f9", "PANEL": "#e2e8f0", "CARD": "#ffffff",
        "CARD_HOVER": "#cbd5e1", "CARD_SEL": "#dbeafe", "CARD_BORDER": "#3b82f6",
        "TEXT": "#0f172a", "MUTED": "#64748b",
        "ACCENT": "#3b82f6", "ACCENT_H": "#2563eb",
        "RED": "#ef4444", "RED_H": "#dc2626", "RED_D": "#fecaca",
        "GREEN": "#16a34a", "MODE": "light",
    },
}

class T:
    """Активная тема — singleton с горячей заменой."""
    _d = THEMES["Dark Slate"].copy()

    BG=PANEL=CARD=CARD_HOVER=CARD_SEL=CARD_BORDER=""
    TEXT=MUTED=ACCENT=ACCENT_H=RED=RED_H=RED_D=GREEN=""
    MODE="dark"; FONT="Montserrat"

    @classmethod
    def apply(cls, name: str):
        d = THEMES.get(name, THEMES["Dark Slate"])
        cls._d = d.copy()
        cls.BG=d["BG"]; cls.PANEL=d["PANEL"]; cls.CARD=d["CARD"]
        cls.CARD_HOVER=d["CARD_HOVER"]; cls.CARD_SEL=d["CARD_SEL"]
        cls.CARD_BORDER=d["CARD_BORDER"]; cls.TEXT=d["TEXT"]
        cls.MUTED=d["MUTED"]; cls.ACCENT=d["ACCENT"]
        cls.ACCENT_H=d["ACCENT_H"]; cls.RED=d["RED"]
        cls.RED_H=d["RED_H"]; cls.RED_D=d["RED_D"]; cls.GREEN=d["GREEN"]
        cls.MODE=d["MODE"]
        ctk.set_appearance_mode(cls.MODE)

T.apply("Dark Slate")

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
_ICON_CACHE: dict[str, ctk.CTkImage] = {}

def _to_white(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    px  = img.getdata()
    img.putdata([
        (255, 255, 255, a) if (r < 120 and g < 120 and b < 120) else (r, g, b, a)
        for r, g, b, a in px
    ])
    return img

def _make_placeholder(size=(20,20)) -> Image.Image:
    img  = Image.new("RGBA", size, (0,0,0,0))
    draw = ImageDraw.Draw(img)
    s    = min(size)
    draw.ellipse([2,2,s-3,s-3], fill=(255,255,255,180))
    return img

def load_icon(filename: str, size=(20,20)) -> ctk.CTkImage:
    key = f"{filename}_{size}"
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    path = asset(os.path.join("assets","images",filename))
    try:
        img = _to_white(Image.open(path))
    except Exception:
        img = _make_placeholder(size)
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
# LOGGER  (print + опциональный textbox)
# ─────────────────────────────────────────────────────────────
class Logger:
    def __init__(self):
        self._box = None

    def attach(self, box):
        self._box = box

    def log(self, msg: str, level="INFO"):
        line = f"[{level}] {msg}"
        print(line)
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
# SETTINGS MANAGER
# ─────────────────────────────────────────────────────────────
class Settings:
    FILE = os.path.join(DATA_DIR, "settings.json")
    DEFAULTS = {
        "theme":             "Dark Slate",
        "ram":               4096,
        "java_path":         "",
        "jvm_args":          "-XX:+UseG1GC -XX:+ParallelRefProcEnabled",
        "close_on_launch":   False,
        "selected_instance": None,
        "language":          "ru",
        "discord_rpc":       False,
        "window_width":      1200,
        "window_height":     700,
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
    cfg = Settings.load()
    instance_ram = _safe_int((instance_cfg or {}).get("ram"), 0)
    global_ram = _safe_int(cfg.get("ram"), 4096)
    return max(2048, min(32768, max(instance_ram, global_ram)))

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
            data = [{"name": "Player", "type": "offline", "uuid": ""}]
        return data

    @classmethod
    def save(cls, data: list):
        save_json(cls.FILE, data)

    @classmethod
    def add(cls, name: str, acc_type="offline") -> list:
        import uuid
        accounts = cls.load()
        for a in accounts:
            if a["name"] == name:
                raise Exception(f"Аккаунт «{name}» уже существует")
        accounts.append({"name": name, "type": acc_type, "uuid": str(uuid.uuid4())})
        cls.save(accounts)
        return accounts

    @classmethod
    def remove(cls, name: str) -> list:
        accounts = [a for a in cls.load() if a["name"] != name]
        if not accounts:
            # Запрещаем удалять последний аккаунт подчистую (всегда должен быть 1)
            accounts = [{"name": "Player", "type": "offline", "uuid": ""}]
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
    CORE_PATH = os.path.join(CORE_DIR, "launcher_core.py")

    @classmethod
    def _ensure_stub(cls):
        """Создаёт заглушку core/launcher_core.py если файла нет."""
        if os.path.exists(cls.CORE_PATH):
            return
        stub = '''"""
launcher_core.py — игровая логика SCL
======================================
Реализуй здесь:
  - скачивание нужной версии Minecraft (vanilla/fabric/forge/neoforge/quilt)
  - скачивание Java нужной версии
  - построение classpath и аргументов запуска
  - запуск процесса java
  - аутентификация (offline / Microsoft / ely.by)
  - отслеживание статуса процесса

API, которого ждёт UI:
  install(instance_cfg: dict, progress_cb=None) -> bool
  is_installed(instance_cfg: dict) -> bool
  launch(instance_cfg: dict, account: dict) -> subprocess.Popen
  get_java_path(instance_cfg: dict) -> str
  fetch_versions() -> list[str]        # актуальный список с серверов Mojang
"""

def install(instance_cfg: dict, progress_cb=None) -> bool:
    """Заглушка установки. Вернёт False пока не реализована."""
    print(f"[CORE] install() called for {instance_cfg.get('name')}")
    if progress_cb:
        progress_cb(0.0, "Не реализовано — это заглушка")
    return False

def is_installed(instance_cfg: dict) -> bool:
    return False

def launch(instance_cfg: dict, account: dict):
    """Заглушка запуска. Возвращает None пока не реализована."""
    print(f"[CORE] launch() called: {instance_cfg.get('name')} as {account.get('name')}")
    return None

def get_java_path(instance_cfg: dict) -> str:
    return instance_cfg.get("java_path") or ""

def fetch_versions() -> list:
    try:
        import minecraft_launcher_lib
        versions = minecraft_launcher_lib.utils.get_available_versions(
            minecraft_launcher_lib.utils.get_minecraft_directory())
        return [v["id"] for v in versions if v.get("type") == "release"]
    except Exception:
        return []
'''
        with open(cls.CORE_PATH, "w", encoding="utf-8") as f:
            f.write(stub)
        log.log("Создана заглушка core/launcher_core.py")

    @classmethod
    def _get_core(cls):
        cls._ensure_stub()
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("launcher_core", cls.CORE_PATH)
        mod  = ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @classmethod
    def install(cls, instance_cfg: dict, progress_cb=None) -> bool:
        try:
            return cls._get_core().install(instance_cfg, progress_cb)
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

CoreBridge._ensure_stub()

def _merge_versions(primary: list, fallback: list) -> list:
    result = []
    for version in [*primary, *fallback]:
        if version and version not in result:
            result.append(version)
    return result

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
    global MINECRAFT_VERSIONS
    versions = fetch_mojang_release_versions()
    if not versions:
        versions = CoreBridge.fetch_versions()
    if not versions:
        return False, MINECRAFT_VERSIONS
    MINECRAFT_VERSIONS = _merge_versions(versions, DEFAULT_MINECRAFT_VERSIONS)
    return True, MINECRAFT_VERSIONS

# ─────────────────────────────────────────────────────────────
# УТИЛИТЫ UI
# ─────────────────────────────────────────────────────────────
def font(size=13, weight="normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=T.FONT, size=size, weight=weight)

def open_folder(path: str):
    if not os.path.exists(path):
        messagebox.showwarning("SCL", f"Папка не найдена:\n{path}")
        return
    try:
        s = platform.system()
        if   s == "Windows": os.startfile(path)
        elif s == "Darwin":  subprocess.Popen(["open",     path])
        else:                subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Ошибка", str(e))

# ═══════════════════════════════════════════════════════════════
#  ВИДЖЕТЫ
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────
# INSTANCE CARD
# ─────────────────────────────────────────────────────────────
class InstanceCard(ctk.CTkFrame):
    def __init__(self, parent, data: dict, on_select, on_play):
        super().__init__(parent,
            width=200, height=210,
            fg_color=T.CARD, corner_radius=12,
            border_width=2, border_color=T.CARD)
        self.data      = data
        self.on_select = on_select
        self.on_play   = on_play
        self.selected  = False
        self.grid_propagate(False)

        self._ico = load_instance_icon(data.get("name",""), size=(58,58))
        self._lbl_ico = ctk.CTkLabel(self, image=self._ico, text="")
        self._lbl_ico.pack(pady=(16,6))

        self._lbl_name = ctk.CTkLabel(self,
            text=data.get("name","?"),
            font=font(13,"bold"), wraplength=165)
        self._lbl_name.pack()

        loader  = data.get("loader","Vanilla")
        version = data.get("version","")
        self._lbl_ver = ctk.CTkLabel(self,
            text=f"{loader} {version}",
            text_color=T.MUTED, font=font(11))
        self._lbl_ver.pack(pady=(2,0))

        self._lbl_ram = ctk.CTkLabel(self,
            text=f"RAM {effective_ram_mb(data)} МБ",
            text_color=T.MUTED, font=font(10))
        self._lbl_ram.pack(pady=(2,0))

        # ── кнопка быстрого запуска ──────────────────────────
        self._btn_play = ctk.CTkButton(self,
            text="▶  Играть", width=112, height=28,
            corner_radius=8, font=font(11,"bold"),
            fg_color=T.ACCENT, hover_color=T.ACCENT_H,
            command=self._quick_play)
        self._btn_play.pack(pady=(9,0))

        for w in (self, self._lbl_ico, self._lbl_name, self._lbl_ver, self._lbl_ram):
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
            self.configure(fg_color=T.CARD, border_color=T.CARD)

    def _click(self,_e):  self.on_select(self.data)
    def _dbl(self,_e):    self.on_play(self.data)
    def _quick_play(self): self.on_play(self.data)
    def _enter(self,_e):
        if not self.selected: self.configure(fg_color=T.CARD_HOVER)
    def _leave(self,_e):
        if not self.selected: self.configure(fg_color=T.CARD)
    def _rclick(self, e):
        menu = tk.Menu(self, tearoff=0,
                       bg=T.CARD, fg=T.TEXT,
                       activebackground=T.CARD_HOVER,
                       activeforeground=T.TEXT,
                       bd=0, relief="flat")
        menu.add_command(label="▶  Играть",        command=lambda: self.on_play(self.data))
        menu.add_command(label="🔧  Настройки",     command=lambda: self.on_select(self.data, open_settings=True))
        menu.add_separator()
        menu.add_command(label="📁  Открыть папку", command=lambda: open_folder(InstanceMgr.path(self.data["name"])))
        menu.add_separator()
        menu.add_command(label="🗑  Удалить",        command=lambda: self.on_select(self.data, delete=True))
        try: menu.tk_popup(e.x_root, e.y_root)
        finally: menu.grab_release()

# ─────────────────────────────────────────────────────────────
# PROGRESS BAR OVERLAY  (показывается во время установки)
# ─────────────────────────────────────────────────────────────
class ProgressOverlay(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent,
            fg_color=T.PANEL, corner_radius=12)
        ctk.CTkLabel(self, text="Установка...",
                     font=font(14,"bold")).pack(pady=(20,8))
        self._bar = ctk.CTkProgressBar(self, width=340,
                                       fg_color=T.CARD,
                                       progress_color=T.ACCENT)
        self._bar.set(0)
        self._bar.pack(padx=30, pady=4)
        self._lbl = ctk.CTkLabel(self, text="Подготовка...",
                                 text_color=T.MUTED, font=font(11))
        self._lbl.pack(pady=(4,20))

    def update(self, value: float, status: str):
        self._bar.set(max(0.0, min(1.0, value)))
        self._lbl.configure(text=status)
        self.update_idletasks()

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

    def _header(self, text: str):
        ctk.CTkLabel(self, text=text,
                     font=font(20,"bold")).pack(pady=(22,16))

    def _btn_row(self, ok_text="Создать", ok_cmd=None, cancel_cmd=None):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(8,20))
        ctk.CTkButton(row, text="Отмена",
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
        self._header("Создание сборки")
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24)

        def row(label):
            ctk.CTkLabel(body, text=label,
                         text_color=T.MUTED, font=font(12),
                         anchor="w").pack(fill="x", pady=(8,1))

        row("Название")
        self._name = ctk.CTkEntry(body, placeholder_text="Моя сборка",
                                  font=font(13))
        self._name.pack(fill="x")

        row("Версия Minecraft")
        versions = MINECRAFT_VERSIONS or DEFAULT_MINECRAFT_VERSIONS
        self._ver = ctk.CTkComboBox(body,
            values=versions, font=font(13),
            dropdown_font=font(12),
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H,
            border_color=T.CARD_HOVER)
        self._ver.set(default_minecraft_version())
        self._ver.pack(fill="x")

        row("Загрузчик")
        self._loader = ctk.CTkSegmentedButton(body,
            values=LOADERS, font=font(12),
            selected_color=T.ACCENT, selected_hover_color=T.ACCENT_H,
            unselected_color=T.CARD, unselected_hover_color=T.CARD_HOVER)
        self._loader.set("Vanilla")
        self._loader.pack(fill="x", pady=(2,0))

        row("RAM (МБ)")
        default_ram = effective_ram_mb({})
        self._ram = ctk.CTkEntry(body, placeholder_text="4096", font=font(13))
        self._ram.insert(0, str(default_ram))
        self._ram.pack(fill="x")

        self._btn_row("Создать", self._submit)

    def _submit(self):
        name   = self._name.get().strip()
        ver    = self._ver.get()
        loader = self._loader.get()
        try:
            ram = int(self._ram.get())
        except ValueError:
            messagebox.showerror("Ошибка", "RAM должен быть числом", parent=self)
            return
        if not name:
            messagebox.showerror("Ошибка", "Введите название сборки", parent=self)
            return
        try:
            data = InstanceMgr.create(name, ver, loader, ram)
            self.on_created(data)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self)

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
        self._header(f"⚙  {self.data['name']}")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=24)

        def row(label):
            ctk.CTkLabel(scroll, text=label,
                         text_color=T.MUTED, font=font(12), anchor="w"
                         ).pack(fill="x", pady=(10,1))

        row("Название")
        self._name = ctk.CTkEntry(scroll, font=font(13))
        self._name.insert(0, self.data.get("name",""))
        self._name.pack(fill="x")

        row("Версия Minecraft")
        versions = MINECRAFT_VERSIONS or DEFAULT_MINECRAFT_VERSIONS
        self._ver = ctk.CTkComboBox(scroll,
            values=versions, font=font(13),
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H,
            border_color=T.CARD_HOVER)
        self._ver.set(self.data.get("version", default_minecraft_version()))
        self._ver.pack(fill="x")

        row("Загрузчик")
        self._loader = ctk.CTkSegmentedButton(scroll,
            values=LOADERS, font=font(12),
            selected_color=T.ACCENT, selected_hover_color=T.ACCENT_H,
            unselected_color=T.CARD, unselected_hover_color=T.CARD_HOVER)
        self._loader.set(self.data.get("loader","Vanilla"))
        self._loader.pack(fill="x", pady=(2,0))

        row("RAM (МБ)")
        self._ram = ctk.CTkEntry(scroll, font=font(13))
        self._ram.insert(0, str(self.data.get("ram", 4096)))
        self._ram.pack(fill="x")

        row("Путь к Java (оставь пустым — авто)")
        self._java = ctk.CTkEntry(scroll, font=font(12),
                                  placeholder_text="C:\\Program Files\\Java\\...")
        self._java.insert(0, self.data.get("java_path",""))
        self._java.pack(fill="x")

        row("Аргументы JVM")
        self._jvm = ctk.CTkEntry(scroll, font=font(12),
            placeholder_text="-XX:+UseG1GC -XX:+ParallelRefProcEnabled")
        self._jvm.insert(0, self.data.get("jvm_args",""))
        self._jvm.pack(fill="x")

        self._btn_row("Сохранить", self._submit)

    def _submit(self):
        new_name = self._name.get().strip()
        old_name = self.data["name"]
        try:
            ram = int(self._ram.get())
        except ValueError:
            messagebox.showerror("Ошибка","RAM должен быть числом", parent=self)
            return
        if not new_name:
            messagebox.showerror("Ошибка","Введите название", parent=self)
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
            messagebox.showerror("Ошибка", str(e), parent=self)

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
        self._header("👤  Аккаунты")

        self._list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list.pack(fill="both", expand=True, padx=20)

        self._refresh()

        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", padx=20, pady=(8,16))
        self._new_name = ctk.CTkEntry(add_row,
            placeholder_text="Никнейм (offline)", font=font(13))
        self._new_name.pack(side="left", fill="x", expand=True, padx=(0,8))
        ctk.CTkButton(add_row, text="+ Добавить", width=100,
                      fg_color=T.ACCENT, hover_color=T.ACCENT_H,
                      command=self._add).pack(side="left")

    def _refresh(self):
        for w in self._list.winfo_children():
            w.destroy()
        for acc in self.accounts:
            row = ctk.CTkFrame(self._list,
                fg_color=T.CARD, corner_radius=8)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row,
                text=f"👤  {acc['name']}",
                font=font(13)
            ).pack(side="left", padx=12, pady=10)
            ctk.CTkLabel(row,
                text=acc.get("type","offline"),
                text_color=T.MUTED, font=font(11)
            ).pack(side="left")
            ctk.CTkButton(row, text="Выбрать", width=80,
                fg_color=T.ACCENT, hover_color=T.ACCENT_H,
                command=lambda a=acc: self._select(a)
            ).pack(side="right", padx=6)
            ctk.CTkButton(row, text="✕", width=32,
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
            messagebox.showerror("Ошибка", str(e), parent=self)

    def _delete(self, name):
        if messagebox.askyesno("Удаление", f"Удалить аккаунт «{name}»?", parent=self):
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
        self._header("⚙  Настройки лаунчера")

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

        # ── Тема ───────────────────────────────────────────
        row("Тема оформления")
        self._theme = ctk.CTkComboBox(scroll,
            values=list(THEMES.keys()), font=font(13),
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H,
            border_color=T.CARD_HOVER)
        self._theme.set(self.cfg.get("theme","Dark Slate"))
        self._theme.pack(fill="x")

        # ── RAM ────────────────────────────────────────────
        row("RAM по умолчанию (МБ)", "Используется если не задано в настройках сборки")
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

        # ── Java ───────────────────────────────────────────
        row("Глобальный путь к Java", "Можно переопределить в настройках сборки")
        self._java = ctk.CTkEntry(scroll, font=font(12),
            placeholder_text="Авто (из PATH)")
        self._java.insert(0, self.cfg.get("java_path",""))
        self._java.pack(fill="x")

        # ── JVM Args ───────────────────────────────────────
        row("Аргументы JVM по умолчанию")
        self._jvm = ctk.CTkEntry(scroll, font=font(12))
        self._jvm.insert(0, self.cfg.get("jvm_args",
            "-XX:+UseG1GC -XX:+ParallelRefProcEnabled"))
        self._jvm.pack(fill="x")

        # ── Закрывать лаунчер при запуске ─────────────────
        row("")
        self._close_sw = ctk.CTkSwitch(scroll,
            text="Сворачивать лаунчер при запуске игры",
            font=font(13),
            progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H)
        if self.cfg.get("close_on_launch"):
            self._close_sw.select()
        self._close_sw.pack(anchor="w", pady=(4,0))

        # ── Discord RPC ────────────────────────────────────
        self._discord_sw = ctk.CTkSwitch(scroll,
            text="Discord Rich Presence (в разработке)",
            font=font(13),
            progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_H)
        if self.cfg.get("discord_rpc"):
            self._discord_sw.select()
        self._discord_sw.pack(anchor="w", pady=(8,0))

        self._btn_row("Сохранить", self._submit)

    def _ram_slide(self, v):
        self._ram_lbl.configure(text=f"{int(v)} МБ")

    def _submit(self):
        self.cfg.update({
            "theme":           self._theme.get(),
            "ram":             int(self._ram_slider.get()),
            "java_path":       self._java.get().strip(),
            "jvm_args":        self._jvm.get().strip(),
            "close_on_launch": self._close_sw.get() == 1,
            "discord_rpc":     self._discord_sw.get() == 1,
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

        ctk.CTkButton(self, text="Очистить",
                      fg_color=T.CARD, hover_color=T.CARD_HOVER,
                      command=self._clear).pack(pady=(0,10))

    def _clear(self):
        self._box.configure(state="normal")
        self._box.delete("1.0","end")
        self._box.configure(state="disabled")

# ═══════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ═══════════════════════════════════════════════════════════════
class App(ctk.CTk):

    VERSION = "1.0"

    def __init__(self):
        super().__init__()
        self.cfg              = Settings.load()
        T.apply(self.cfg.get("theme","Dark Slate"))

        w = self.cfg.get("window_width",  1200)
        h = self.cfg.get("window_height", 700)
        self.title("Simple Craft Launcher")
        # Защита от float-координат, если они так сохранились
        self.geometry(f"{int(w)}x{int(h)}")
        self.minsize(960, 580)
        self.configure(fg_color=T.BG)

        # иконка
        ico = asset(os.path.join("assets","images","app_icon.ico"))
        if os.path.exists(ico):
            try: self.iconbitmap(ico)
            except Exception: pass

        self.current_instance: dict | None = None
        self.current_account: dict = AccountMgr.load()[0]
        self.game_proc        = None
        self.game_running     = False
        self.console_win      = None
        self.cards: list[InstanceCard] = []
        self._versions_refreshing = False

        self._preload_icons()
        self._build_ui()
        self._reload_instances()
        self._refresh_versions_async()

        log.log(f"Simple Craft Launcher v{self.VERSION} запущен")
        log.log(f"Тема: {self.cfg.get('theme')}")

    # ────────────────────────────────────────────────────────
    def _preload_icons(self):
        self._ico_add      = load_icon("add.png",      (18,18))
        self._ico_settings = load_icon("settings.png", (18,18))
        self._ico_folders  = load_icon("folders.png",  (18,18))

    # ────────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_topbar()
        self._build_body()

    # ── ТОПБАР ─────────────────────────────────────────────
    def _build_topbar(self):
        self.topbar = ctk.CTkFrame(self, height=54,
                                   fg_color=T.PANEL, corner_radius=0)
        self.topbar.pack(fill="x")
        self.topbar.pack_propagate(False)

        # лого
        ctk.CTkLabel(self.topbar,
            text="  ⛏  SCL",
            font=font(16,"bold"), text_color=T.TEXT
        ).pack(side="left", padx=(14,20))

        def tb_btn(text, icon=None, cmd=None):
            return ctk.CTkButton(self.topbar,
                text=text, image=icon,
                compound="left" if icon else "center",
                fg_color=T.CARD, hover_color=T.CARD_HOVER,
                height=34, corner_radius=8, font=font(12),
                command=cmd)

        tb_btn("Добавить", self._ico_add,
               cmd=self._open_create_dialog
               ).pack(side="left", padx=4, pady=10)

        tb_btn("Настройки", self._ico_settings,
               cmd=self._open_global_settings
               ).pack(side="left", padx=4)

        tb_btn("Папки", self._ico_folders,
               cmd=lambda: open_folder(INSTANCES_DIR)
               ).pack(side="left", padx=4)


        # версия лаунчера (справа)
        ctk.CTkLabel(self.topbar,
            text=f"v{self.VERSION}",
            text_color=T.MUTED, font=font(11)
        ).pack(side="right", padx=16)

        self._mc_version_badge = ctk.CTkLabel(self.topbar,
            text=f"MC {default_minecraft_version()}",
            text_color=T.TEXT, font=font(11,"bold"),
            fg_color=T.CARD, corner_radius=8,
            width=96, height=28)
        self._mc_version_badge.pack(side="right", padx=(0,8))

    # ── BODY (sidebar + center) ─────────────────────────────
    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self._build_sidebar(body)
        self._build_center(body)

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
            text="Выберите сборку",
            font=font(16,"bold"), wraplength=250)
        self._sb_name.pack()

        self._sb_sub = ctk.CTkLabel(self.sidebar,
            text="", text_color=T.MUTED, font=font(11))
        self._sb_sub.pack(pady=(2,4))

        self._sb_time = ctk.CTkLabel(self.sidebar,
            text="", text_color=T.MUTED, font=font(10))
        self._sb_time.pack(pady=(0,14))

        # ── кнопки ─────────────────────────────────────────
        def sb_btn(text, color=None, hover=None, cmd=None, height=36):
            return ctk.CTkButton(self.sidebar,
                text=text, height=height, corner_radius=8,
                fg_color=color or T.CARD,
                hover_color=hover or T.CARD_HOVER,
                font=font(12), command=cmd)

        self._sb_play = sb_btn("▶  Играть",
            T.ACCENT, T.ACCENT_H, self._toggle_game, height=42)
        self._sb_play.pack(fill="x", padx=18, pady=(0,6))

        sb_btn("🔧  Настройки сборки",
               cmd=lambda: self._open_instance_settings()
               ).pack(fill="x", padx=18, pady=2)

        sb_btn("📁  Открыть папку",
               cmd=lambda: open_folder(
                   InstanceMgr.path(self.current_instance["name"])
                   if self.current_instance else INSTANCES_DIR)
               ).pack(fill="x", padx=18, pady=2)

        sb_btn("✏  Переименовать",
               cmd=self._rename_instance
               ).pack(fill="x", padx=18, pady=2)

        # разделитель
        ctk.CTkFrame(self.sidebar, height=1,
                     fg_color=T.CARD_HOVER
                     ).pack(fill="x", padx=18, pady=10)

        sb_btn("🗑  Удалить",
               T.RED_D, T.RED_H, self._delete_instance
               ).pack(fill="x", padx=18, pady=2)

    # ── ЦЕНТР ───────────────────────────────────────────────
    def _build_center(self, parent):
        self.center = ctk.CTkFrame(parent, fg_color="transparent")
        self.center.pack(side="left", fill="both", expand=True)

        header = ctk.CTkFrame(self.center, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(16,4))

        ctk.CTkLabel(header,
            text="Сборки",
            font=font(22,"bold"), text_color=T.TEXT
        ).pack(side="left")

        self._library_stats = ctk.CTkLabel(header,
            text="", text_color=T.MUTED, font=font(11))
        self._library_stats.pack(side="left", padx=(10,0), pady=(6,0))

        # поиск + сортировка
        top = ctk.CTkFrame(self.center, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(4,4))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        self._search_entry = ctk.CTkEntry(top,
            textvariable=self._search_var,
            placeholder_text="🔍  Поиск сборок...",
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
        self._btn_account = ctk.CTkButton(bottom,
            text=f"👤  {self.current_account['name']}  ▾",
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

        self._lbl_bottom_status = ctk.CTkLabel(bottom,
            text="Выберите сборку для запуска",
            text_color=T.MUTED, font=font(11), anchor="w")
        self._lbl_bottom_status.pack(side="left", fill="x", expand=True, padx=18)

        # большая кнопка ИГРАТЬ
        self._btn_play = ctk.CTkButton(bottom,
            text="  ИГРАТЬ  ",
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
            fg_color=T.CARD, corner_radius=12,
            border_width=1, border_color=T.CARD_HOVER)
        box.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(box,
            text=title,
            font=font(17,"bold"), text_color=T.TEXT
        ).pack(padx=34, pady=(28,6))
        ctk.CTkLabel(box,
            text="Создайте новую сборку или измените поиск",
            font=font(11), text_color=T.MUTED
        ).pack(padx=34, pady=(0,14))
        ctk.CTkButton(box,
            text="＋  Новая сборка",
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
            self._sb_time.configure(text=f"🕒 Наиграно: {h}ч {m}м")
        else:
            self._sb_time.configure(text="Ещё не запускалась")

        # иконка в сайдбаре
        ico = load_instance_icon(data["name"], (68,68))
        self._sb_icon.configure(image=ico)

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
        if hasattr(self, "_mc_version_badge"):
            self._mc_version_badge.configure(text="MC ...")

        def worker():
            ok, versions = refresh_minecraft_versions()
            self.after(0, self._on_versions_refreshed, ok, versions)

        threading.Thread(target=worker, daemon=True).start()

    def _on_versions_refreshed(self, ok: bool, versions: list):
        self._versions_refreshing = False
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
        d = ctk.CTkInputDialog(text="Новое название:", title="Переименовать")
        new = d.get_input()
        if not new or new == self.current_instance["name"]:
            return
        try:
            InstanceMgr.rename(self.current_instance["name"], new)
            self._reload_instances(select_name=new)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _delete_instance(self):
        if not self.current_instance:
            return
        name = self.current_instance["name"]
        if not messagebox.askyesno("Удаление",
                f"Удалить сборку «{name}» со всеми файлами?\n"
                "Это действие необратимо."):
            return
        InstanceMgr.delete(name)
        self.current_instance = None
        self._sb_name.configure(text="Выберите сборку")
        self._sb_sub.configure(text="")
        self._sb_time.configure(text="")
        self._sb_icon.configure(image=load_icon("box_icon.png",(72,72)))
        if hasattr(self, "_lbl_bottom_status"):
            self._lbl_bottom_status.configure(text="Выберите сборку для запуска")
        self._reload_instances()

    # ────────────────────────────────────────────────────────
    # УСТАНОВКА
    # ────────────────────────────────────────────────────────
    def _install_instance(self):
        if not self.current_instance:
            messagebox.showwarning("SCL","Выберите сборку")
            return
        if self.game_running:
            messagebox.showwarning("SCL","Нельзя устанавливать во время игры")
            return

        inst = self._prepare_launch_instance(self.current_instance)
        self._show_progress(True)
        log.log(f"Начало установки: {inst['name']}")

        def worker():
            ok = CoreBridge.install(inst, self._progress_from_thread)
            self.after(0, self._on_install_done, ok)

        threading.Thread(target=worker, daemon=True).start()

    def _progress_from_thread(self, value: float, status: str):
        self.after(0, self._progress.update, value, status)

    def _show_progress(self, show: bool):
        if show:
            self.grid_frame.pack_forget()
            self._progress.pack(fill="both", expand=True, padx=30, pady=30)
        else:
            self._progress.pack_forget()
            self.grid_frame.pack(fill="both", expand=True, padx=10, pady=4)

    def _on_install_done(self, ok: bool):
        self._show_progress(False)
        if ok:
            log.log("Установка завершена успешно")
            messagebox.showinfo("SCL","Установка завершена!")
        else:
            log.log("Установка не выполнена (core не реализован)", "WARN")
            messagebox.showinfo("SCL",
                "Логика установки ещё не реализована.\n"
                "Открой core/launcher_core.py и реализуй функцию install()")

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
        return inst

    def _play_game(self):
        if not self.current_instance:
            messagebox.showwarning("SCL","Выберите сборку")
            return
        if self.game_running:
            return

        inst = self._prepare_launch_instance(self.current_instance)
        if not CoreBridge.is_installed(inst):
            self._install_then_play(inst)
            return

        self._launch_installed(inst)

    def _install_then_play(self, inst: dict):
        self._show_progress(True)
        self._progress.update(0.0, "Игра не установлена — начинаю установку...")
        self._btn_play.configure(text="  УСТАНОВКА...  ", state="disabled")
        self._sb_play.configure(text="Установка...", state="disabled")
        log.log(f"Автоустановка перед запуском: {inst['name']} [{inst.get('loader','')} {inst.get('version','')}]")

        def worker():
            ok = CoreBridge.install(inst, self._progress_from_thread)
            self.after(0, self._on_auto_install_done, ok, inst)

        threading.Thread(target=worker, daemon=True).start()

    def _on_auto_install_done(self, ok: bool, inst: dict):
        self._show_progress(False)
        self._btn_play.configure(text="  ИГРАТЬ  ", state="normal", fg_color=T.ACCENT)
        self._sb_play.configure(text="▶  Играть", state="normal", fg_color=T.ACCENT)

        if not ok:
            log.log("Автоустановка не удалась", "ERROR")
            messagebox.showerror("SCL",
                "Не удалось установить игру автоматически.\n"
                "Подробности смотри в консоли лаунчера.")
            return

        log.log("Автоустановка завершена, запускаю игру")
        self._launch_installed(inst)

    def _launch_installed(self, inst: dict):
        acc  = self.current_account
        log.log(f"Запуск: {inst['name']} от {acc['name']}")

        proc = CoreBridge.launch(inst, acc)

        if proc is None:
            messagebox.showinfo("SCL",
                "Запуск игры пока не реализован.\n\n"
                f"Сборка:  {inst['name']}\n"
                f"Версия:  {inst.get('loader','')} {inst.get('version','')}\n"
                f"Аккаунт: {acc['name']}\n"
                f"RAM:     {inst.get('ram',4096)} МБ\n\n"
                "Реализуй функцию launch() в core/launcher_core.py")
            return

        self.game_proc    = proc
        self.game_running = True
        self._btn_play.configure(text="  ИГРА ИДЁТ  ", fg_color=T.GREEN)
        self._sb_play.configure(text="■  Остановить", fg_color=T.RED)

        import datetime
        inst["last_played"] = datetime.datetime.now().isoformat(timespec="seconds")
        InstanceMgr.save_cfg(inst)

        threading.Thread(target=self._watch_proc, args=(proc,), daemon=True).start()

        if self.cfg.get("close_on_launch"):
            self.iconify()

    def _watch_proc(self, proc):
        proc.wait()
        self.after(0, self._stop_game)

    def _stop_game(self):
        if not self.game_running:
            return
        log.log("Игра остановлена")
        self.game_running = False
        self.game_proc    = None
        self._btn_play.configure(text="  ИГРАТЬ  ", fg_color=T.ACCENT)
        self._sb_play.configure(text="▶  Играть", fg_color=T.ACCENT)
        if self.cfg.get("close_on_launch"):
            self.deiconify()

    # ────────────────────────────────────────────────────────
    # ДИАЛОГИ
    # ────────────────────────────────────────────────────────
    def _open_accounts(self):
        AccountsDialog(self, on_select=self._on_account_selected)

    def _on_account_selected(self, acc: dict):
        self.current_account = acc
        self._btn_account.configure(text=f"👤  {acc['name']}  ▾")
        self._lbl_acc_type.configure(
            text=f"({acc.get('type','offline')})")
        log.log(f"Выбран аккаунт: {acc['name']}")

    def _open_global_settings(self):
        GlobalSettingsDialog(self, on_saved=self._on_settings_saved)

    def _on_settings_saved(self, cfg: dict):
        self.cfg = cfg
        T.apply(cfg.get("theme","Dark Slate"))
        log.log(f"Настройки сохранены. Тема: {cfg.get('theme')}")
        messagebox.showinfo("SCL",
            "Некоторые изменения вступят в силу при следующем запуске.\n"
            "(Тема, шрифт, цветовая схема)")

    def _open_console(self):
        if self.console_win and self.console_win.winfo_exists():
            self.console_win.focus()
            return
        self.console_win = ConsoleWindow(self)

    # ────────────────────────────────────────────────────────
    # ЗАКРЫТИЕ
    # ────────────────────────────────────────────────────────
    def on_close(self):
        if self.game_running:
            if not messagebox.askyesno("Выход",
                    "Игра запущена. Всё равно закрыть лаунчер?"):
                return
            if self.game_proc:
                try: self.game_proc.terminate()
                except Exception: pass

        cfg = Settings.load()
        cfg["window_width"]  = self.winfo_width()
        cfg["window_height"] = self.winfo_height()
        Settings.save(cfg)
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
        messagebox.showerror("Критическая ошибка", str(exc))
        raise
