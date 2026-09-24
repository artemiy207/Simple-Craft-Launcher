"""
launcher_core.py — игровая логика Simple Craft Launcher
=========================================================
Поддерживаемые загрузчики: Vanilla, Fabric, Forge, NeoForge, Quilt
API для UI:
  install(instance_cfg, progress_cb=None) -> bool
  is_installed(instance_cfg) -> bool
  launch(instance_cfg, account) -> subprocess.Popen
  get_java_path(instance_cfg) -> str
  fetch_versions() -> list[str]          # актуальный список с серверов Mojang
  latest_release() -> str                # самая свежая release-версия
  offline_uuid(name) -> str              # стабильный UUID для offline-аккаунта
  get_last_error() -> str                # текст последней ошибки для UI
  set_logger(cb)                         # вывод логов CORE в окно «Консоль»
  instances_dir() -> str                 # папка сборок (диск B:, а не C:)
  disk_free_gb(path) -> float            # свободное место на диске
  export_instance(cfg, zip, cb) -> bool  # сборка → один ZIP-файл
  import_instance(zip, name, cb) -> str  # ZIP-файл → новая сборка
"""

import os
import sys
import time
import json
import socket
import shutil
import threading
import zipfile
import hashlib
import subprocess
import platform
import traceback

try:
    import minecraft_launcher_lib
except ImportError:
    minecraft_launcher_lib = None  # type: ignore

# ФИКС ДЛЯ EXE: Сохраняем игру рядом с лаунчером, а не во временной папке Windows
if getattr(sys, 'frozen', False):
    ROOT = os.path.dirname(sys.executable)
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR  = os.path.join(ROOT, "data")
LOG_FILE  = os.path.join(DATA_DIR, "launcher.log")
LOG_LIMIT = 2 * 1024 * 1024          # 2 МБ, потом уходим в launcher.log.1

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
MIN_FREE_GB   = 5.0                          # меньше места — ставим игру на другой диск
DRIVE_ORDER   = "BCDEFGHIJKLMNOPQRSTUVWXYZ"  # B: проверяется первым (как просил пользователь)

MEMORY_ARG_PREFIXES = ("-Xmx", "-Xms")

# Скачивание: если данные не приходят DOWNLOAD_TIMEOUT секунд, соединение считаем
# оборванным. urllib3/requests берут этот таймаут по умолчанию, когда свой не задан,
# поэтому установка больше не может «зависнуть навсегда» на середине загрузки.
DOWNLOAD_TIMEOUT = 45
try:
    socket.setdefaulttimeout(DOWNLOAD_TIMEOUT)
except Exception:
    pass

# Стабильный stdout: без этого логи с юникодом («→») падают с UnicodeEncodeError,
# когда вывод перенаправлен (лог в файл, IDE, пайп) и кодировка локали — cp1251.
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────
# ЛОГИРОВАНИЕ
# ─────────────────────────────────────────────────────────────
_LOGGER_CB  = None
_LAST_ERROR = ""


def set_logger(cb):
    """UI передаёт сюда свою функцию лога, чтобы строки CORE попадали в консоль."""
    global _LOGGER_CB
    _LOGGER_CB = cb


def get_last_error() -> str:
    """Последняя ошибка — UI показывает её пользователю."""
    return _LAST_ERROR


def _log(msg: str, level: str = "INFO"):
    global _LAST_ERROR
    line = f"[CORE/{level}] {msg}"
    if level == "ERROR":
        _LAST_ERROR = str(msg)

    try:
        if _LOGGER_CB is None:                # UI сам печатает/складывает строки
            print(line, flush=True)
    except Exception:
        pass

    try:                                  # дублируем в файл
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_LIMIT:
            bak = LOG_FILE + ".1"
            if os.path.exists(bak):
                os.remove(bak)
            os.replace(LOG_FILE, bak)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    if _LOGGER_CB:
        try:
            _LOGGER_CB(line)
        except Exception:
            pass


def _fail(msg: str) -> bool:
    """Записывает ошибку в состояние и возвращает False (для install())."""
    _log(str(msg), "ERROR")
    return False


# ─────────────────────────────────────────────────────────────
# ПРОГРЕСС-ТРЕКЕР
# ─────────────────────────────────────────────────────────────
class ProgressTracker:
    """Маппинг колбэков MLL → наш прогресс-бар."""

    def __init__(self, cb):
        self.cb = cb
        self.maximum = 100
        self.curr = 0
        self.status = "Подготовка..."
        self.touched = time.monotonic()      # когда последний раз была активность

    def set_status(self, s: str):
        self.status = str(s)
        self._push()

    def set_progress(self, p: int | float):
        try:
            self.curr = float(p)
        except (TypeError, ValueError):
            self.curr = 0
        self._push()

    def set_max(self, m: int | float):
        try:
            self.maximum = float(m) or 100
        except (TypeError, ValueError):
            self.maximum = 100

    def _push(self):
        self.touched = time.monotonic()
        if self.cb:
            val = self.curr / self.maximum if self.maximum > 0 else 0
            val = max(0.0, min(1.0, val))
            try:
                self.cb(val, self.status)
            except Exception:
                pass


def _make_callback(tracker: ProgressTracker) -> dict:
    return {
        "setStatus":   tracker.set_status,
        "setProgress": tracker.set_progress,
        "setMax":      tracker.set_max,
    }


# ─────────────────────────────────────────────────────────────
# АККАУНТ (offline)
# ─────────────────────────────────────────────────────────────
def offline_uuid(name: str) -> str:
    """
    Стабильный offline-UUID — как на ванильном сервере:
    md5 от 'OfflinePlayer:<ник>' с проставленными version/variant битами.
    """
    nickname = (name or "Player").strip() or "Player"
    digest   = bytearray(hashlib.md5(("OfflinePlayer:" + nickname).encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    h = digest.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# ─────────────────────────────────────────────────────────────
# ПУТИ
# ─────────────────────────────────────────────────────────────
def _read_settings() -> dict:
    """Настройки лаунчера (data/settings.json)."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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


def best_install_root(preferred: str = "") -> str:
    """
    Куда ставить игру:
      1. явно указанная папка;
      2. диск лаунчера (B:) — если на нём есть место;
      3. самый свободный диск (B: в приоритете).
    Смысл: тяжёлые файлы не должны улетать на переполненный диск C:.
    """
    preferred = (preferred or "").strip()
    if preferred:
        return os.path.abspath(os.path.expanduser(preferred))

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
            _log(f"На диске лаунчера свободно {root_free:.1f} ГБ → игра будет "
                 f"ставиться на {best} (свободно {best_free:.1f} ГБ)")
            return best
    return ROOT


def instances_dir() -> str:
    """Корень папки со сборками: из настроек, иначе рядом с лаунчером (диск B:)."""
    configured = str(_read_settings().get("instances_dir") or "").strip()
    if configured:
        base = os.path.abspath(os.path.expanduser(configured))
        if _drive_alive(base):
            return base
        _log(f"Папка сборок «{base}» недоступна — беру папку лаунчера", "WARN")
    return os.path.join(best_install_root(), "instances")


def shared_mc_dir() -> str:
    """Общий (shared) .minecraft — рядом с лаунчером, а не в %APPDATA% (диск C:)."""
    return os.path.join(os.path.dirname(instances_dir()) or ROOT, "minecraft")


def get_mc_dir(instance_cfg: dict) -> str:
    """Возвращает рабочую директорию инстанса (на выбранном диске, а не на C:)."""
    custom = str(instance_cfg.get("game_dir") or "").strip()
    if custom:
        return os.path.abspath(os.path.expanduser(custom))

    isolation = instance_cfg.get("isolation", "isolated")
    if isolation == "shared":
        return shared_mc_dir()

    name = instance_cfg.get("name")
    if not name:
        return os.path.join(instances_dir(), "_default")
    return os.path.join(instances_dir(), name)


# ─────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────────────────────
def _safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _installed_ids(mc_dir: str) -> list[str]:
    if not minecraft_launcher_lib:
        return []
    try:
        return [v["id"] for v in minecraft_launcher_lib.utils.get_installed_versions(mc_dir)]
    except Exception as e:
        _log(f"Ошибка чтения установленных версий ({mc_dir}): {e}", "WARN")
        return []


def _resolve_launch_version(mc_dir: str, version: str, loader: str) -> str | None:
    """Находит точный ID установленной версии для данного загрузчика."""
    ids = _installed_ids(mc_dir)
    if not ids:
        return None

    loader = loader or "Vanilla"

    if loader.lower() == "vanilla":
        return version if version in ids else None

    # Для модифицированных версий ищем по подстрокам
    # Формат: "fabric-loader-0.xx.x-1.21.4" / "1.21.4-forge-xx" / "neoforge-xx" / "quilt-loader-xx-1.21.4"
    loader_key = loader.lower()
    candidates = []
    for installed_id in ids:
        low = installed_id.lower()
        if version in installed_id and loader_key in low:
            candidates.append(installed_id)

    if not candidates:
        return None
    # Берём последнюю (наиболее свежую) по имени
    return sorted(candidates)[-1]


def _clean_memory_args(args: list[str]) -> list[str]:
    return [a for a in args if not any(a.startswith(p) for p in MEMORY_ARG_PREFIXES)]


def _force_memory_args(cmd: list[str], ram: int) -> list[str]:
    if not cmd:
        return cmd
    java_exe = cmd[0]
    rest = _clean_memory_args(cmd[1:])
    # Xms держим небольшим (как в Prism): большой стартовый heap сразу коммитит память,
    # и на системах с маленьким файлом подкачки JVM падает при старте.
    xms = min(512, ram)
    return [java_exe, f"-Xmx{ram}M", f"-Xms{xms}M", *rest]


def _check_mll():
    if minecraft_launcher_lib is None:
        raise RuntimeError(
            "minecraft-launcher-lib не установлен.\n"
            "Запустите: pip install minecraft-launcher-lib"
        )


# ─────────────────────────────────────────────────────────────
# ПАМЯТЬ СИСТЕМЫ
# ─────────────────────────────────────────────────────────────
def system_memory() -> dict:
    """
    Память системы в МБ:
      total_mb / avail_mb        — физическая ОЗУ
      commit_total_mb / commit_avail_mb — лимит commit (ОЗУ + файл подкачки) и сколько свободно
    """
    info = {"total_mb": 0, "avail_mb": 0, "commit_total_mb": 0, "commit_avail_mb": 0}
    if platform.system() == "Windows":
        try:
            import ctypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = _MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                mb = 1024 * 1024
                info["total_mb"]        = int(status.ullTotalPhys // mb)
                info["avail_mb"]        = int(status.ullAvailPhys // mb)
                info["commit_total_mb"] = int(status.ullTotalPageFile // mb)
                info["commit_avail_mb"] = int(status.ullAvailPageFile // mb)
        except Exception as e:
            _log(f"Не удалось прочитать память системы: {e}", "WARN")
    else:
        try:
            page = os.sysconf("SC_PAGE_SIZE")
            info["total_mb"] = int(os.sysconf("SC_PHYS_PAGES") * page // (1024 * 1024))
            info["avail_mb"] = int(os.sysconf("SC_AVPHYS_PAGES") * page // (1024 * 1024))
        except Exception:
            pass
    return info


def safe_ram_mb(requested: int) -> int:
    """
    Сколько МБ реально можно отдать игре:
      * не больше половины ОЗУ,
      * не больше свободного commit (ОЗУ + файл подкачки) минус запас системе.
    Иначе JVM падает с «insufficient memory» и игра закрывается через пару секунд.
    """
    requested = max(512, _safe_int(requested, 4096))
    mem = system_memory()
    if not mem["total_mb"]:
        return requested

    limit = max(512, mem["total_mb"] // 2)
    if mem["commit_avail_mb"] > 0:
        limit = min(limit, max(512, mem["commit_avail_mb"] - 768))

    if limit < requested:
        _log(f"RAM уменьшена с {requested} до {limit} МБ "
             f"(ОЗУ {mem['total_mb']} МБ, свободно commit {mem['commit_avail_mb']} МБ)", "WARN")
        return limit
    return requested


def memory_hint() -> str:
    """Короткая подсказка про память для интерфейса."""
    mem = system_memory()
    if not mem["total_mb"]:
        return ""
    text = (f"ОЗУ {mem['total_mb'] // 1024} ГБ, свободно {mem['avail_mb'] // 1024} ГБ; "
            f"commit свободно {mem['commit_avail_mb'] // 1024} ГБ")
    if mem["commit_total_mb"] and mem["commit_total_mb"] - mem["total_mb"] < 2048:
        text += " • файл подкачки меньше рекомендуемого"
    return text


_NETWORK_HINTS = (
    "proxyerror", "sslerror", "connectionerror", "connectionreset",
    "readtimeout", "connecttimeout", "timeout", "max retries exceeded",
    "remotedisconnected", "eof occurred", "temporary failure",
    "connection aborted", "incompleteread", "chunkedencodingerror",
    "nameserver", "getaddrinfo", "network is unreachable",
)


def _is_network_error(err) -> bool:
    """Похоже ли на сетевой сбой (тогда установку имеет смысл повторить)."""
    text = f"{type(err).__name__}: {err}".lower()
    return any(hint in text for hint in _NETWORK_HINTS)


_MEMORY_CRASH_MARKERS = (
    "insufficient memory for the java runtime",
    "os::commit_memory",
    "native memory allocation",
    "файл подкачки слишком мал",
    "page file",
    "could not reserve enough space",
    "outofmemoryerror",
    "java heap space",
)


def classify_crash(output_tail: str) -> tuple[str, str]:
    """
    По выводу игры определяет причину падения: (код, объяснение для пользователя).
    Коды: memory / java / files / unknown
    """
    text = (output_tail or "").lower()
    if any(marker in text for marker in _MEMORY_CRASH_MARKERS):
        return ("memory",
                "Игре не хватило памяти: Java не смогла зарезервировать heap.\n"
                "Обычно причина — маленький файл подкачки Windows или мало свободной памяти.")
    if "unsupportedclassversionerror" in text or "class file version" in text:
        return ("java",
                "Не подходит версия Java для этой версии Minecraft.\n"
                "Выберите другую Java в настройках сборки.")
    if "could not find or load main class" in text or "classnotfoundexception" in text:
        return ("files",
                "Файлы сборки неполные или повреждены — попробуйте установить её заново.")
    if "exception" in text and "error" in text:
        return ("unknown", "Игра завершилась с ошибкой — подробности ниже.")
    return ("unknown", "Игра завершилась с ошибкой.")


# ─────────────────────────────────────────────────────────────
# ВЕРСИИ MINECRAFT
# ─────────────────────────────────────────────────────────────
def fetch_versions() -> list[str]:
    """Список release-версий Minecraft с серверов Mojang (новые сверху)."""
    if minecraft_launcher_lib is None:
        return []
    try:
        versions = minecraft_launcher_lib.utils.get_version_list()
        return [v["id"] for v in versions if v.get("type") == "release"]
    except Exception as e:
        _log(f"fetch_versions: {e}", "WARN")
        return []


def latest_release() -> str:
    """Самая свежая release-версия (например «26.3»). Пустая строка — нет сети."""
    if minecraft_launcher_lib is None:
        return ""
    try:
        return (minecraft_launcher_lib.utils.get_latest_version() or {}).get("release", "")
    except Exception as e:
        _log(f"latest_release: {e}", "WARN")
        return ""


# ─────────────────────────────────────────────────────────────
# JAVA
# ─────────────────────────────────────────────────────────────
_JAVA_CACHE: list[dict] | None = None


def _parse_java_major(version: str) -> int:
    """«1.8.0_402» → 8, «21.0.12.1» → 21, «17» → 17. 0 — не разобрали."""
    text = str(version or "").strip()
    if not text:
        return 0
    parts = text.split(".")
    try:
        if parts[0] == "1" and len(parts) > 1:
            return int(parts[1].split("_")[0])
        return int(parts[0].split("_")[0])
    except (ValueError, IndexError):
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits[:2]) if digits else 0


def _major_from_name(name: str) -> int:
    """Вытаскивает major Java из имени папки: «jdk-21.0.12.1» → 21, «jre1.8.0_402» → 8."""
    import re
    match = re.search(r"\d+(?:\.\d+)*", name or "")
    return _parse_java_major(match.group(0)) if match else 0


def _system_java_candidates() -> list[dict]:
    """
    Все найденные в системе Java (кэшируется на время работы процесса):
        [{"path": "...\\java.exe", "javaw": "...\\javaw.exe", "major": 21}, ...]
    """
    global _JAVA_CACHE
    if _JAVA_CACHE is not None:
        return _JAVA_CACHE

    found: dict[str, dict] = {}

    def _register(exe: str, javaw: str = "", major: int = 0):
        if not exe:
            return
        exe = os.path.normpath(exe)
        key = os.path.normcase(exe)
        if key in found:
            if major and not found[key]["major"]:
                found[key]["major"] = major
            return
        found[key] = {
            "path":  exe,
            "javaw": os.path.normpath(javaw) if javaw else exe,
            "major": major,
        }

    # 1) через minecraft-launcher-lib — он умеет спрашивать версию у самой Java
    if minecraft_launcher_lib is not None:
        try:
            for info in minecraft_launcher_lib.java_utils.find_system_java_versions_information():
                if isinstance(info, dict):
                    get = info.get
                else:
                    def get(k, i=info):
                        return getattr(i, k, "")
                _register(get("java_path") or get("path") or "",
                          get("javaw_path") or "",
                          _parse_java_major(get("version") or ""))
        except Exception as e:
            _log(f"Поиск Java через minecraft-launcher-lib не удался: {e}", "WARN")

    # 2) JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        bin_dir = os.path.join(java_home, "bin")
        for exe_name in ("java.exe", "java"):
            exe = os.path.join(bin_dir, exe_name)
            if os.path.isfile(exe):
                _register(exe, os.path.join(bin_dir, "javaw.exe"), _major_from_name(java_home))
                break

    # 3) стандартные папки установки
    if platform.system() == "Windows":
        roots = (
            r"C:\Program Files\Java",
            r"C:\Program Files\Eclipse Adoptium",
            r"C:\Program Files\Microsoft",
            r"C:\Program Files\Zulu",
            r"C:\Program Files\BellSoft",
            r"C:\Program Files\Amazon Corretto",
            r"C:\Program Files (x86)\Java",
        )
        for root_dir in roots:
            if not os.path.isdir(root_dir):
                continue
            try:
                subs = sorted(os.listdir(root_dir), reverse=True)
            except Exception:
                continue
            for sub in subs:
                bin_dir = os.path.join(root_dir, sub, "bin")
                javaw   = os.path.join(bin_dir, "javaw.exe")
                if os.path.isfile(javaw):
                    _register(os.path.join(bin_dir, "java.exe"), javaw, _major_from_name(sub))

    _JAVA_CACHE = sorted(found.values(), key=lambda c: c["major"], reverse=True)
    if _JAVA_CACHE:
        _log("Найдены Java: " + ", ".join(
            f"{c['major'] or '?'} ({c['path']})" for c in _JAVA_CACHE))
    else:
        _log("Java в системе не найдена", "WARN")
    return _JAVA_CACHE


def _required_java(instance_cfg: dict, target_version: str) -> tuple[str, int]:
    """(имя рантайма Mojang, требуемая major-версия Java). ("", 0) — не определили."""
    if not (minecraft_launcher_lib and target_version):
        return ("", 0)
    try:
        info = minecraft_launcher_lib.runtime.get_version_runtime_information(
            target_version, get_mc_dir(instance_cfg)
        )
    except Exception as e:
        _log(f"Не удалось определить требуемую Java для {target_version}: {e}", "WARN")
        return ("", 0)
    if not info:
        return ("", 0)
    if isinstance(info, dict):
        return (str(info.get("name") or ""), _safe_int(info.get("javaMajorVersion"), 0))
    return (str(getattr(info, "name", "")), _safe_int(getattr(info, "javaMajorVersion", 0), 0))


def _installed_runtime_java(component: str, mc_dir: str) -> str:
    """Java из рантайма Mojang, уже скачанного в эту сборку."""
    if not (component and minecraft_launcher_lib):
        return ""
    try:
        path = minecraft_launcher_lib.runtime.get_executable_path(component, mc_dir)
    except Exception:
        return ""
    return path if path and os.path.exists(path) else ""


def get_java_path(instance_cfg: dict, target_version: str | None = None) -> str:
    """Java: кастомная → рантайм сборки → системная под версию → самая свежая → из PATH."""
    custom = (instance_cfg.get("java_path") or "").strip()
    if custom and os.path.exists(custom):
        return custom

    mc_dir = get_mc_dir(instance_cfg)
    if not target_version:
        target_version = _resolve_launch_version(
            mc_dir, instance_cfg.get("version", ""), instance_cfg.get("loader", "Vanilla")
        ) or instance_cfg.get("version", "")

    component, needed = _required_java(instance_cfg, target_version)

    runtime_java = _installed_runtime_java(component, mc_dir)
    if runtime_java:
        return runtime_java

    candidates = _system_java_candidates()
    if needed:
        for cand in candidates:                      # точное совпадение major
            if cand["major"] == needed:
                return cand["javaw"] or cand["path"]
    if candidates:
        best = max(candidates, key=lambda c: c["major"])
        return best["javaw"] or best["path"]

    if minecraft_launcher_lib:
        try:
            found = minecraft_launcher_lib.utils.get_java_executable()
            if found and os.path.exists(found):
                return found
        except Exception:
            pass
    return "java"


def ensure_java_runtime(instance_cfg: dict, target_version: str, progress_cb=None) -> str:
    """
    Гарантирует подходящую Java:
      1) кастомный путь из настроек
      2) уже скачанный рантайм сборки
      3) системная Java нужной major-версии
      4) при auto_java=True — качает рантайм Mojang (java-runtime-*)
    Возвращает путь к java или "" если не удалось.
    """
    custom = (instance_cfg.get("java_path") or "").strip()
    if custom and os.path.exists(custom):
        return custom
    if not instance_cfg.get("auto_java", True):
        return ""

    mc_dir = get_mc_dir(instance_cfg)
    component, needed = _required_java(instance_cfg, target_version)

    runtime_java = _installed_runtime_java(component, mc_dir)
    if runtime_java:
        return runtime_java

    if needed:
        for cand in _system_java_candidates():
            if cand["major"] == needed:
                _log(f"Используем системную Java {needed}: {cand['path']}")
                return cand["javaw"] or cand["path"]

    if not component:
        _log(f"Не удалось определить требуемый рантайм Java для {target_version}", "WARN")
        return ""

    tracker = ProgressTracker(progress_cb)
    tracker.set_status(f"Скачивание Java {needed} ({component})...")
    _log(f"Скачивание рантайма Java «{component}» (Java {needed}) для Minecraft {target_version}...")
    try:
        minecraft_launcher_lib.runtime.install_jvm_runtime(
            component, mc_dir, callback=_make_callback(tracker)
        )
    except Exception as e:
        _log(f"Не удалось скачать рантайм Java «{component}»: {e}", "ERROR")
        return ""

    path = _installed_runtime_java(component, mc_dir)
    if path:
        _log(f"Java готова: {path}")
    return path


# ─────────────────────────────────────────────────────────────
# ЗАГРУЗЧИКИ
# ─────────────────────────────────────────────────────────────
_LOADER_IDS = {"fabric": "fabric", "forge": "forge", "neoforge": "neoforge", "quilt": "quilt"}


def _install_loader(loader: str, version: str, mc_dir: str,
                    tracker: ProgressTracker, callback: dict) -> str:
    """
    Устанавливает загрузчик и возвращает ID установленной версии.
    Сначала пробуем новый API minecraft-launcher-lib (mod_loader),
    затем — старые функции (fabric/forge/quilt) для совместимости.
    """
    loader_key = (loader or "").lower()
    loader_id  = _LOADER_IDS.get(loader_key)

    if loader_id and hasattr(minecraft_launcher_lib, "mod_loader"):
        mod = None
        try:
            mod = minecraft_launcher_lib.mod_loader.get_mod_loader(loader_id)
        except Exception as e:
            _log(f"mod_loader не смог отдать «{loader_id}»: {e}", "WARN")

        if mod is not None:
            try:
                supported = mod.is_minecraft_version_supported(version)
            except Exception:
                supported = True
            if not supported:
                raise RuntimeError(f"{loader} не поддерживает Minecraft {version}")
            tracker.set_status(f"Скачивание {loader} для {version}...")
            installed = mod.install(version, mc_dir, callback=callback)
            return installed or version

    # ── Старый API (minecraft-launcher-lib < 8)
    if loader_key == "fabric" and hasattr(minecraft_launcher_lib, "fabric"):
        tracker.set_status(f"Скачивание Fabric для {version}...")
        minecraft_launcher_lib.fabric.install_fabric(version, mc_dir, callback=callback)
        return _resolve_launch_version(mc_dir, version, loader) or version

    if loader_key == "forge" and hasattr(minecraft_launcher_lib, "forge"):
        tracker.set_status(f"Скачивание Forge для {version}...")
        forge_ver = minecraft_launcher_lib.forge.find_forge_version(version)
        if not forge_ver:
            raise RuntimeError(f"Forge для Minecraft {version} не найден")
        minecraft_launcher_lib.forge.install_forge_version(forge_ver, mc_dir, callback=callback)
        return _resolve_launch_version(mc_dir, version, loader) or forge_ver

    if loader_key == "quilt" and hasattr(minecraft_launcher_lib, "quilt"):
        tracker.set_status(f"Скачивание Quilt для {version}...")
        minecraft_launcher_lib.quilt.install_quilt(version, mc_dir, callback=callback)
        return _resolve_launch_version(mc_dir, version, loader) or version

    if loader_key == "neoforge":
        raise RuntimeError(
            "Для NeoForge нужен minecraft-launcher-lib >= 8.0.\n"
            "Обновите: pip install --upgrade minecraft-launcher-lib"
        )
    raise RuntimeError(f"Загрузчик «{loader}» не поддерживается установщиком")


# ─────────────────────────────────────────────────────────────
# ПУБЛИЧНЫЙ API
# ─────────────────────────────────────────────────────────────
def _version_complete(mc_dir: str, version_id: str) -> bool:
    """
    Установлена ли версия ПОЛНОСТЬЮ. Одного JSON мало: нужен ещё клиент (jar)
    базовой версии и индекс ассетов — иначе недокачанная сборка выглядела бы
    «установленной» (например, если прервать загрузку на середине).
    """
    json_path = os.path.join(mc_dir, "versions", version_id, f"{version_id}.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False

    base      = data.get("inheritsFrom") or version_id
    base_json = os.path.join(mc_dir, "versions", base, f"{base}.json")
    jar_path  = os.path.join(mc_dir, "versions", base, f"{base}.jar")
    if not os.path.exists(jar_path):
        _log(f"Проверка «{version_id}»: нет клиента {base}.jar — установка не завершена",
             "WARN")
        return False
    if not os.path.exists(base_json):
        return False

    try:
        with open(base_json, "r", encoding="utf-8") as f:
            base_data = json.load(f)
        index_id = (base_data.get("assetIndex") or {}).get("id")
        if index_id and not os.path.exists(
                os.path.join(mc_dir, "assets", "indexes", f"{index_id}.json")):
            _log(f"Проверка «{version_id}»: нет индекса ассетов {index_id}.json", "WARN")
            return False
    except Exception:
        pass
    return True


def is_installed(instance_cfg: dict) -> bool:
    if minecraft_launcher_lib is None:
        _log("Проверка установки: minecraft-launcher-lib не установлен", "WARN")
        return False

    mc_dir  = get_mc_dir(instance_cfg)
    version = instance_cfg.get("version", "")
    loader  = instance_cfg.get("loader", "Vanilla")

    resolved = _resolve_launch_version(mc_dir, version, loader)
    if resolved and not _version_complete(mc_dir, resolved):
        _log(f"«{instance_cfg.get('name')}» [{loader} {version}] → установка не завершена "
             f"({resolved}): не хватает файлов", "WARN")
        resolved = None
    if resolved:
        _log(f"«{instance_cfg.get('name')}» [{loader} {version}] → установлено ({resolved})")
    else:
        _log(f"«{instance_cfg.get('name')}» [{loader} {version}] → не установлено")
    return bool(resolved)


def install(instance_cfg: dict, progress_cb=None) -> bool:
    """
    Скачивает Minecraft + выбранный загрузчик (и Java при auto_java=True).
    При сетевых сбоях повторяет попытку — уже скачанные файлы заново не качаются.
    Возвращает True при успехе.
    """
    if minecraft_launcher_lib is None:
        if progress_cb:
            progress_cb(0.0, "minecraft-launcher-lib не установлен")
        return _fail("minecraft-launcher-lib не установлен.\n"
                     "Выполните: pip install minecraft-launcher-lib")

    mc_dir  = get_mc_dir(instance_cfg)
    version = instance_cfg.get("version", "")
    loader  = instance_cfg.get("loader", "Vanilla")
    name    = instance_cfg.get("name", "?")

    if not version:
        return _fail("Не указана версия Minecraft")

    os.makedirs(mc_dir, exist_ok=True)
    _log(f"Установка {loader} {version} → {mc_dir}")

    free_gb = disk_free_gb(mc_dir)
    if 0 <= free_gb < 3:
        _log(f"На диске «{os.path.splitdrive(mc_dir)[0] or ''}» свободно всего "
             f"{free_gb:.1f} ГБ — установка может не удаться. Освободите место или "
             f"выберите другой диск в «Настройках лаунчера».", "WARN")

    # страховка: миры сохраняем перед установкой/обновлением (если они уже есть)
    backup_saves(instance_cfg, "перед-установкой", progress_cb)

    tracker  = ProgressTracker(progress_cb)
    callback = _make_callback(tracker)

    # ── сторож загрузки: если данные долго не приходят, пишем это в лог ──────
    watchdog_stop = threading.Event()

    def _watch_download():
        last_report = 0.0
        while not watchdog_stop.wait(15):
            idle = time.monotonic() - getattr(tracker, "touched", time.monotonic())
            if idle >= 60 and time.monotonic() - last_report >= 60:
                last_report = time.monotonic()
                _log(f"Скачивание молчит {int(idle)} с (статус: {tracker.status}) — "
                     f"соединение подвисло; попытка прервётся по таймауту "
                     f"{DOWNLOAD_TIMEOUT} с и повторится с места обрыва", "WARN")

    threading.Thread(target=_watch_download, daemon=True).start()

    attempts   = max(1, _safe_int(instance_cfg.get("download_retries"), 4))
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            tracker.set_status(f"Подготовка установки {loader} {version}...")

            if (loader or "").lower() == "vanilla":
                tracker.set_status(f"Скачивание Vanilla {version}...")
                minecraft_launcher_lib.install.install_minecraft_version(
                    version, mc_dir, callback=callback
                )
                installed_id = version
            else:
                installed_id = _install_loader(loader, version, mc_dir, tracker, callback)

            if instance_cfg.get("auto_java", True):
                tracker.set_status("Проверка Java...")
                ensure_java_runtime(instance_cfg, installed_id, progress_cb)

            tracker.set_status("Установка завершена!")
            tracker.set_progress(tracker.maximum)
            _log(f"Установка завершена: «{name}» [{loader} {version}] → {installed_id}")
            watchdog_stop.set()
            return True

        except Exception as e:
            last_error = e
            _log(traceback.format_exc(), "DEBUG")
            if attempt < attempts and _is_network_error(e):
                wait = 5 * attempt
                tracker.set_status(f"Сбой сети ({attempt}/{attempts}) — повтор через {wait} с...")
                _log(f"Сбой сети, повторяю установку через {wait} с: {e}", "WARN")
                time.sleep(wait)
                continue
            break

    watchdog_stop.set()
    if progress_cb:
        progress_cb(0.0, f"Ошибка: {last_error}")
    hint = ""
    if last_error and _is_network_error(last_error):
        hint = ("\nПохоже на обрыв связи: проверьте интернет/прокси. "
                "Повторная установка продолжит с уже скачанных файлов.")
    return _fail(f"Ошибка установки «{name}» [{loader} {version}]: {last_error}{hint}")


# ─────────────────────────────────────────────────────────────
# ЭКСПОРТ / ИМПОРТ СБОРКИ (один ZIP — чтобы перекинуть другу)
# ─────────────────────────────────────────────────────────────
# В архив идёт только «пользовательское» содержимое (моды, ресурспаки, шейдеры,
# конфиги, миры). Версии игры, библиотеки, ассеты и Java скачаются заново при
# установке — поэтому файл получается маленьким.
EXPORT_DIRS = ("mods", "resourcepacks", "shaderpacks", "config", "defaultconfigs",
               "saves", "screenshots", "scripts", "kubejs", "datapacks")
EXPORT_FILES = ("instance.json", "options.txt", "optionsof.txt", "servers.dat",
                "icon.png", "usercache.json")
SKIP_SUFFIX = (".log", ".log.gz", ".tmp", ".part", ".bak")
EXPORT_MARKER = "simplecraft-instance.json"


def _iter_export_files(mc_dir: str):
    """Файлы сборки для архива: (путь внутри архива, полный путь)."""
    for rel in EXPORT_FILES:
        full = os.path.join(mc_dir, rel)
        if os.path.isfile(full):
            yield rel, full
    for sub in EXPORT_DIRS:
        base = os.path.join(mc_dir, sub)
        if not os.path.isdir(base):
            continue
        for root_dir, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in files:
                if fname.lower().endswith(SKIP_SUFFIX):
                    continue
                full = os.path.join(root_dir, fname)
                yield os.path.relpath(full, mc_dir), full


def export_instance(instance_cfg: dict, archive_path: str, progress_cb=None) -> bool:
    """
    Упаковывает сборку в ZIP (mods / resourcepacks / shaderpacks / config / saves).
    Файл можно передать другу и распаковать у него кнопкой «Импорт сборки».
    """
    mc_dir = get_mc_dir(instance_cfg)
    if not os.path.isdir(mc_dir):
        return _fail(f"Папка сборки не найдена: {mc_dir}")

    archive_path = os.path.abspath(os.path.expanduser(archive_path))
    os.makedirs(os.path.dirname(archive_path) or ".", exist_ok=True)

    items   = list(_iter_export_files(mc_dir))
    tracker = ProgressTracker(progress_cb)
    tracker.set_max(max(1, len(items)))
    tracker.set_status("Упаковка сборки...")

    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=9) as zf:
            zf.writestr(EXPORT_MARKER, json.dumps({
                "launcher": "SimpleCraft",
                "format":   1,
                "name":     instance_cfg.get("name", ""),
                "version":  instance_cfg.get("version", ""),
                "loader":   instance_cfg.get("loader", "Vanilla"),
            }, ensure_ascii=False, indent=2))
            for index, (rel, full) in enumerate(items, 1):
                tracker.set_status(rel)
                zf.write(full, rel)
                tracker.set_progress(index)
    except Exception as e:
        return _fail(f"Не удалось создать архив сборки: {e}")

    size_mb = os.path.getsize(archive_path) / (1024 * 1024)
    _log(f"Сборка «{instance_cfg.get('name')}» упакована: {archive_path} "
         f"({size_mb:.1f} МБ, файлов: {len(items)})")
    if progress_cb:
        progress_cb(1.0, f"Готово: {os.path.basename(archive_path)} ({size_mb:.1f} МБ)")
    return True


def _safe_extract(zf: zipfile.ZipFile, target_dir: str):
    """Распаковка без выхода за пределы target_dir (защита от путей вида ..\\..)."""
    target_dir = os.path.abspath(target_dir)
    for member in zf.infolist():
        name = member.filename.replace("\\", "/")
        if not name or name.startswith("/") or ".." in name.split("/"):
            _log(f"В архиве пропущен подозрительный путь: {member.filename}", "WARN")
            continue
        dest = os.path.abspath(os.path.join(target_dir, name))
        if dest != target_dir and not dest.startswith(target_dir + os.sep):
            continue
        if member.is_dir():
            os.makedirs(dest, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with zf.open(member) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)


_LOADER_FROM_DEPS = {
    "fabric-loader": "Fabric",
    "quilt-loader":  "Quilt",
    "forge":         "Forge",
    "neoforge":      "NeoForge",
}


def _loader_from_deps(deps: dict) -> str:
    """'fabric-loader' из зависимостей модпака → «Fabric»."""
    for key, loader in _LOADER_FROM_DEPS.items():
        if key in (deps or {}):
            return loader
    return "Vanilla"


def _extract_mrpack(zf: zipfile.ZipFile, target_dir: str, tracker=None) -> None:
    """
    Распаковка .mrpack: содержимое overrides/ → в корень сборки, файлы из
    files[] (ссылки на CDN Modrinth) — докачиваются в свои пути.
    """
    target_dir = os.path.abspath(target_dir)
    for member in zf.infolist():
        if member.is_dir():
            continue
        name = member.filename.replace("\\", "/")
        if not (name.startswith("overrides/") or name.startswith("client-overrides/")):
            continue
        rel = name.split("/", 1)[1] if "/" in name else ""
        if not rel or ".." in rel.split("/"):
            continue
        dest = os.path.abspath(os.path.join(target_dir, rel))
        if dest != target_dir and not dest.startswith(target_dir + os.sep):
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with zf.open(member) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)

    try:
        index = json.loads(zf.read(MRPACK_INDEX).decode("utf-8"))
    except Exception:
        return

    files = index.get("files") or []
    if not files:
        return
    _log(f"В модпаке {len(files)} файлов со ссылками — качаю их")
    for item in files:
        path = str(item.get("path") or "").replace("\\", "/").lstrip("/")
        urls = item.get("downloads") or []
        if not path or not urls or ".." in path.split("/"):
            continue
        dest = os.path.abspath(os.path.join(target_dir, path))
        if not dest.startswith(target_dir + os.sep):
            continue
        if tracker:
            tracker.set_status(f"Скачивание {os.path.basename(path)}...")
        _download_file(urls[0], dest, tracker)


def _unique_instance_name(base: str) -> str:
    """Свободное имя сборки: «Друг», «Друг-2», «Друг-3»..."""
    base = (base or "Сборка").strip() or "Сборка"
    root, candidate, n = instances_dir(), base, 2
    while os.path.exists(os.path.join(root, candidate)):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def import_instance(archive_path: str, name: str = "", progress_cb=None) -> str:
    """
    Распаковывает ZIP-архив сборки в папку сборок (на диск B:).
    Возвращает имя созданной сборки ("" — ошибка).
    """
    archive_path = os.path.abspath(os.path.expanduser(archive_path))
    if not os.path.isfile(archive_path):
        _log(f"Архив не найден: {archive_path}", "ERROR")
        return ""

    tracker = ProgressTracker(progress_cb)
    tracker.set_status("Распаковка архива...")
    tracker.set_progress(0.1)

    marker: dict = {}
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            names     = zf.namelist()
            is_mrpack = MRPACK_INDEX in names
            if EXPORT_MARKER in names:
                try:
                    marker = json.loads(zf.read(EXPORT_MARKER).decode("utf-8"))
                except Exception:
                    marker = {}
            elif is_mrpack:
                try:
                    index = json.loads(zf.read(MRPACK_INDEX).decode("utf-8"))
                except Exception:
                    index = {}
                deps = index.get("dependencies") or {}
                marker = {
                    "name":    index.get("name") or "",
                    "version": str(deps.get("minecraft") or ""),
                    "loader":  _loader_from_deps(deps),
                }
                tracker.set_status("Распаковка модпака (.mrpack)...")
            base_name = (name or str(marker.get("name") or "")
                         or os.path.splitext(os.path.basename(archive_path))[0])
            target_name = _unique_instance_name(base_name)
            target_dir  = os.path.join(instances_dir(), target_name)
            for sub in ("mods", "resourcepacks", "shaderpacks", "saves",
                        "screenshots", "logs"):
                os.makedirs(os.path.join(target_dir, sub), exist_ok=True)
            if is_mrpack:
                _extract_mrpack(zf, target_dir, tracker)
            else:
                _safe_extract(zf, target_dir)
    except Exception as e:
        _log(f"Не удалось распаковать архив: {e}", "ERROR")
        return ""

    cfg_file = os.path.join(target_dir, "instance.json")
    cfg: dict = {}
    try:
        with open(cfg_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            cfg = loaded
    except Exception:
        cfg = {}

    cfg["name"] = target_name
    cfg.setdefault("version", str(marker.get("version") or ""))
    cfg.setdefault("loader",  str(marker.get("loader") or "Vanilla"))
    cfg.setdefault("ram", 4096)
    cfg.setdefault("java_path", "")
    cfg.setdefault("jvm_args", "")
    cfg.setdefault("created", time.strftime("%Y-%m-%dT%H:%M:%S"))
    cfg.setdefault("last_played", None)
    cfg.setdefault("play_time", 0)
    try:
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception as e:
        _log(f"Не удалось записать instance.json импортированной сборки: {e}", "WARN")

    _log(f"Сборка импортирована: «{target_name}» → {target_dir} "
         f"[{cfg.get('loader')} {cfg.get('version')}]")
    if progress_cb:
        progress_cb(1.0, f"Импортирована сборка «{target_name}»")
    return target_name


# ─────────────────────────────────────────────────────────────
# БЭКАПЫ МИРОВ (папка backups внутри сборки)
# ─────────────────────────────────────────────────────────────
BACKUP_DIRNAME = "backups"
BACKUP_KEEP    = 10            # сколько последних бэкапов хранить


def backups_dir(mc_dir: str) -> str:
    """Папка с бэкапами внутри сборки (на том же диске, что и игра)."""
    return os.path.join(mc_dir, BACKUP_DIRNAME)


def list_backups(instance_cfg: dict) -> list[dict]:
    """Список бэкапов: [{'name','path','size_mb','mtime'}] — новые сверху."""
    folder = backups_dir(get_mc_dir(instance_cfg))
    if not os.path.isdir(folder):
        return []
    result = []
    for fname in os.listdir(folder):
        if not fname.lower().endswith(".zip"):
            continue
        path = os.path.join(folder, fname)
        try:
            size  = os.path.getsize(path) / (1024 * 1024)
            mtime = os.path.getmtime(path)
        except OSError:
            size, mtime = 0.0, 0.0
        result.append({"name": fname, "path": path, "size_mb": size, "mtime": mtime})
    return sorted(result, key=lambda b: b["mtime"], reverse=True)


def _prune_backups(mc_dir: str):
    """Оставляет только BACKUP_KEEP последних бэкапов."""
    folder = backups_dir(mc_dir)
    try:
        files = sorted(
            (os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(".zip")),
            key=os.path.getmtime, reverse=True)
    except Exception:
        return
    for old in files[BACKUP_KEEP:]:
        try:
            os.remove(old)
            _log(f"Старый бэкап удалён: {os.path.basename(old)}")
        except Exception:
            pass


def backup_saves(instance_cfg: dict, reason: str = "ручной", progress_cb=None) -> str:
    """
    Кладёт saves/ сборки в <сборка>/backups/saves-<дата>-<метка>.zip.
    Возвращает путь к архиву ("" — бэкапить было нечего или ошибка).
    """
    mc_dir = get_mc_dir(instance_cfg)
    saves  = os.path.join(mc_dir, "saves")
    if not os.path.isdir(saves):
        _log("Бэкап миров: папки saves нет — пропускаю")
        return ""

    files = []
    for root_dir, _dirs, names in os.walk(saves):
        for fname in names:
            full = os.path.join(root_dir, fname)
            files.append((os.path.relpath(full, mc_dir), full))
    if not files:
        _log("Бэкап миров: миров пока нет — пропускаю")
        return ""

    folder = backups_dir(mc_dir)
    os.makedirs(folder, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    label = "".join(ch for ch in reason if ch.isalnum() or ch in "-_")[:24] or "backup"
    path  = os.path.join(folder, f"saves-{stamp}-{label}.zip")

    tracker = ProgressTracker(progress_cb)
    tracker.set_max(max(1, len(files)))
    tracker.set_status("Бэкап миров...")
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for index, (rel, full) in enumerate(files, 1):
                zf.write(full, rel)
                tracker.set_progress(index)
    except Exception as e:
        _log(f"Не удалось создать бэкап миров: {e}", "ERROR")
        return ""

    _prune_backups(mc_dir)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    _log(f"Бэкап миров создан ({reason}): {os.path.basename(path)} ({size_mb:.1f} МБ)")
    return path


def restore_backup(instance_cfg: dict, archive_path: str, progress_cb=None) -> bool:
    """Возвращает мир из архива в saves/ (текущие миры сначала бэкапятся)."""
    if not os.path.isfile(archive_path):
        return _fail(f"Файл бэкапа не найден: {archive_path}")

    backup_saves(instance_cfg, "перед-восстановлением", progress_cb)   # страховка
    mc_dir  = get_mc_dir(instance_cfg)
    tracker = ProgressTracker(progress_cb)
    tracker.set_status("Восстановление мира...")
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            _safe_extract(zf, mc_dir)
    except Exception as e:
        return _fail(f"Не удалось восстановить мир: {e}")

    _log(f"Мир восстановлен из {os.path.basename(archive_path)}")
    if progress_cb:
        progress_cb(1.0, "Мир восстановлен")
    return True


# ─────────────────────────────────────────────────────────────
# ЭКСПОРТ .mrpack (формат Modrinth / Prism Launcher)
# ─────────────────────────────────────────────────────────────
MRPACK_INDEX = "modrinth.index.json"
MRPACK_LOADER_KEYS = {
    "fabric":   "fabric-loader",
    "quilt":    "quilt-loader",
    "forge":    "forge",
    "neoforge": "neoforge",
}


def _loader_dependency(loader: str, target_version: str = "") -> dict:
    """{'fabric-loader': '0.16.9'} — версию загрузчика берём из id установки."""
    key = MRPACK_LOADER_KEYS.get((loader or "").lower())
    if not key or not target_version:
        return {}
    import re

    name = (loader or "").lower()                 # fabric / quilt / forge / neoforge
    patterns = {
        "fabric":   r"fabric-loader-([0-9][\w.\-]*?)(?=-|$)",
        "quilt":    r"quilt-loader-([0-9][\w.\-]*?)(?=-|$)",
        "forge":    r"forge-([0-9][\w.\-]*?)(?=-|$)",
        "neoforge": r"neoforge-([0-9][\w.\-]*?)(?=-|$)",
    }
    match = re.search(patterns.get(name, ""), target_version, re.IGNORECASE)
    if not match:
        return {}
    version = match.group(1).rstrip("-")
    return {key: version} if version else {}


def export_mrpack(instance_cfg: dict, archive_path: str, progress_cb=None) -> bool:
    """
    Собирает .mrpack: modrinth.index.json + overrides/… (моды, конфиги, миры).
    Такой файл открывают Prism Launcher и Modrinth App — они сами скачают
    нужную версию игры, загрузчик и Java.
    """
    mc_dir = get_mc_dir(instance_cfg)
    if not os.path.isdir(mc_dir):
        return _fail(f"Папка сборки не найдена: {mc_dir}")

    archive_path = os.path.abspath(os.path.expanduser(archive_path))
    os.makedirs(os.path.dirname(archive_path) or ".", exist_ok=True)

    loader  = instance_cfg.get("loader", "Vanilla")
    version = instance_cfg.get("version", "")
    deps    = {"minecraft": version} if version else {}
    deps.update(_loader_dependency(loader, _resolve_launch_version(
        mc_dir, version, loader) or version))

    index = {
        "formatVersion": 1,
        "game":          "minecraft",
        "versionId":     time.strftime("%Y%m%d%H%M%S"),
        "name":          instance_cfg.get("name", "SimpleCraft instance"),
        "summary":       "Собрано в Simple Craft Launcher",
        "files":         [],
        "dependencies":  deps,
    }

    items = [(rel, full) for rel, full in _iter_export_files(mc_dir)
             if os.path.basename(rel) != "instance.json"]
    tracker = ProgressTracker(progress_cb)
    tracker.set_max(max(1, len(items)))
    tracker.set_status("Сборка .mrpack...")

    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=9) as zf:
            zf.writestr(MRPACK_INDEX, json.dumps(index, ensure_ascii=False, indent=2))
            for order, (rel, full) in enumerate(items, 1):
                tracker.set_status(rel)
                zf.write(full, "overrides/" + rel.replace("\\", "/"))
                tracker.set_progress(order)
    except Exception as e:
        return _fail(f"Не удалось собрать .mrpack: {e}")

    size_mb = os.path.getsize(archive_path) / (1024 * 1024)
    _log(f"Сборка «{instance_cfg.get('name')}» сохранена как .mrpack: {archive_path} "
         f"({size_mb:.1f} МБ), зависимости: {deps}")
    if progress_cb:
        progress_cb(1.0, f"Готово: {os.path.basename(archive_path)} ({size_mb:.1f} МБ)")
    return True


# ─────────────────────────────────────────────────────────────
# MODRINTH: поиск, установка и обновление модов
# ─────────────────────────────────────────────────────────────
MODRINTH_API     = "https://api.modrinth.com/v2"
MODS_META_FILE   = ".simplecraft-mods.json"     # что скачано через менеджер модов
MODRINTH_LOADERS = {"fabric": "fabric", "quilt": "quilt",
                    "forge": "forge", "neoforge": "neoforge"}
_HTTP_TIMEOUT    = 30


def _modrinth_headers() -> dict:
    """Modrinth требует осмысленный User-Agent."""
    return {"User-Agent": "SimpleCraftLauncher/1.0 (tyomik; +https://github.com/artemiy207/Simple-Craft-Launcher)"}


def modrinth_loaders(loader: str) -> list[str]:
    """Загрузчики для фильтра Modrinth (Vanilla → пусто, моды не применимы)."""
    key = MODRINTH_LOADERS.get((loader or "").lower())
    return [key] if key else []


def _facets(version: str, loader: str, project_type: str = "mod") -> str:
    parts = [[f"project_type:{project_type}"]]
    if version:
        parts.append([f"versions:{version}"])
    loaders = modrinth_loaders(loader)
    if loaders:
        parts.append([f"categories:{name}" for name in loaders])
    return json.dumps(parts)


def modrinth_search(query: str, version: str = "", loader: str = "Vanilla",
                    limit: int = 20, offset: int = 0,
                    project_type: str = "mod") -> list[dict]:
    """
    Поиск проектов на Modrinth. Возвращает список словарей:
    {project_id, title, description, downloads, author, icon_url}
    """
    try:
        import requests

        params = {
            "query":  query or "",
            "limit":  max(1, min(50, int(limit))),
            "offset": max(0, int(offset)),
            "index":  "relevance" if query else "downloads",
        }
        facets = _facets(version, loader, project_type)
        if facets:
            params["facets"] = facets
        response = requests.get(f"{MODRINTH_API}/search", params=params,
                                headers=_modrinth_headers(), timeout=_HTTP_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        _log(f"Поиск в Modrinth не удался: {e}", "WARN")
        return []

    result = []
    for hit in data.get("hits", []):
        result.append({
            "project_id":  hit.get("project_id") or hit.get("slug") or "",
            "slug":        hit.get("slug") or "",
            "title":       hit.get("title") or "",
            "description": hit.get("description") or "",
            "downloads":   _safe_int(hit.get("downloads"), 0),
            "author":      hit.get("author") or "",
            "icon_url":    hit.get("icon_url") or "",
        })
    return result


def modrinth_best_version(project_id: str, version: str = "", loader: str = "Vanilla",
                          version_id: str = "") -> dict:
    """
    Подходящий файл проекта: {'version_id','file_name','url','version_number',
    'game_versions','release'} или {} если ничего не подошло.
    version_id заполняется, когда нужна конкретная версия (для обновлений).
    """
    if not project_id:
        return {}
    try:
        import requests

        if version_id:
            url = f"{MODRINTH_API}/version/{version_id}"
            data = [requests.get(url, headers=_modrinth_headers(),
                                 timeout=_HTTP_TIMEOUT).json()]
        else:
            params = {}
            if version:
                params["game_versions"] = json.dumps([version])
            loaders = modrinth_loaders(loader)
            if loaders:
                params["loaders"] = json.dumps(loaders)
            response = requests.get(f"{MODRINTH_API}/project/{project_id}/version",
                                    params=params, headers=_modrinth_headers(),
                                    timeout=_HTTP_TIMEOUT)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        _log(f"Не удалось получить версии проекта {project_id}: {e}", "WARN")
        return {}

    if not isinstance(data, list) or not data:
        return {}

    def is_release(item: dict) -> int:
        return 0 if (item.get("version_type") or "") == "release" else 1

    for item in sorted(data, key=is_release):
        files = item.get("files") or []
        chosen = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not chosen:
            continue
        return {
            "version_id":     item.get("id") or "",
            "version_number": item.get("version_number") or "",
            "file_name":      chosen.get("filename") or "",
            "url":            chosen.get("url") or "",
            "game_versions":  item.get("game_versions") or [],
            "release":        (item.get("version_type") or "") == "release",
        }
    return {}


def mods_dir(instance_cfg: dict) -> str:
    """Папка mods сборки (внутри папки сборки, на выбранном диске)."""
    return os.path.join(get_mc_dir(instance_cfg), "mods")


def _mods_meta_path(mc_dir: str) -> str:
    return os.path.join(mc_dir, MODS_META_FILE)


def read_mods_meta(instance_cfg: dict) -> dict:
    """{'project_id': {'title','version_id','version_number','file'}}."""
    try:
        with open(_mods_meta_path(get_mc_dir(instance_cfg)), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_mods_meta(mc_dir: str, meta: dict) -> None:
    try:
        with open(_mods_meta_path(mc_dir), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception as e:
        _log(f"Не удалось сохранить список модов: {e}", "WARN")


def _download_file(url: str, dest: str, tracker=None) -> bool:
    """Качает файл во временный .part и только потом подменяет цель."""
    try:
        import requests

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        with requests.get(url, headers=_modrinth_headers(), stream=True,
                          timeout=_HTTP_TIMEOUT) as response:
            response.raise_for_status()
            total = _safe_int(response.headers.get("content-length"), 0)
            if tracker and total:
                tracker.set_max(total)
            done = 0
            with open(tmp, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if tracker:
                        tracker.set_progress(done)
        if os.path.exists(dest):
            os.remove(dest)
        os.replace(tmp, dest)
        return True
    except Exception as e:
        _log(f"Не удалось скачать файл мода: {e}", "ERROR")
        try:
            if os.path.exists(dest + ".part"):
                os.remove(dest + ".part")
        except Exception:
            pass
        return False


def modrinth_install(instance_cfg: dict, project_id: str, title: str = "",
                     version: str = "", loader: str = "",
                     progress_cb=None) -> bool:
    """Скачивает мод в mods/ и запоминает его для «Обновить все моды»."""
    version = version or instance_cfg.get("version", "")
    loader  = loader or instance_cfg.get("loader", "Vanilla")
    mc_dir  = get_mc_dir(instance_cfg)

    tracker = ProgressTracker(progress_cb)
    tracker.set_status(f"Поиск версии «{title or project_id}»...")
    info = modrinth_best_version(project_id, version, loader)
    if not info:
        return _fail(f"Для {loader} {version} подходящего файла «{title or project_id}» нет")

    tracker.set_status(f"Скачивание {info['file_name']}...")
    target = os.path.join(mods_dir(instance_cfg), info["file_name"])
    if not _download_file(info["url"], target, tracker):
        return _fail(f"Не удалось скачать {info['file_name']}")

    meta = read_mods_meta(instance_cfg)
    old  = str((meta.get(project_id) or {}).get("file") or "")
    meta[project_id] = {
        "title":          title or project_id,
        "version_id":     info["version_id"],
        "version_number": info["version_number"],
        "file":           info["file_name"],
    }
    _write_mods_meta(mc_dir, meta)

    if old and old != info["file_name"]:
        try:
            os.remove(os.path.join(mods_dir(instance_cfg), old))
            _log(f"Старый файл мода удалён: {old}")
        except Exception:
            pass

    _log(f"Мод установлен: {title or project_id} {info['version_number']} "
         f"→ mods/{info['file_name']}")
    if progress_cb:
        progress_cb(1.0, f"{title or project_id} {info['version_number']}")
    return True


def modrinth_remove(instance_cfg: dict, project_id: str) -> bool:
    """Удаляет файл мода и запись о нём."""
    meta = read_mods_meta(instance_cfg)
    info = meta.pop(project_id, None)
    if not info:
        return False
    file_path = os.path.join(mods_dir(instance_cfg), str(info.get("file") or ""))
    try:
        if info.get("file") and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        _log(f"Не удалось удалить файл мода: {e}", "WARN")
    _write_mods_meta(get_mc_dir(instance_cfg), meta)
    _log(f"Мод удалён: {info.get('title') or project_id}")
    return True


def modrinth_update_all(instance_cfg: dict, progress_cb=None) -> dict:
    """
    Проверяет и обновляет все моды, поставленные через менеджер модов.
    Возвращает {'updated': [описания], 'kept': сколько актуальных, 'errors': [...]}.
    """
    meta   = read_mods_meta(instance_cfg)
    result = {"updated": [], "kept": 0, "errors": []}
    if not meta:
        return result

    version = instance_cfg.get("version", "")
    loader  = instance_cfg.get("loader", "Vanilla")
    tracker = ProgressTracker(progress_cb)
    tracker.set_max(max(1, len(meta)))

    for index, (project_id, info) in enumerate(meta.items(), 1):
        title = str((info or {}).get("title") or project_id)
        tracker.set_status(f"Проверка {title}...")
        fresh = modrinth_best_version(project_id, version, loader)
        if not fresh:
            result["errors"].append(f"{title}: нет версии для {loader} {version}")
            tracker.set_progress(index)
            continue
        if fresh["version_id"] == str((info or {}).get("version_id") or ""):
            result["kept"] += 1
            tracker.set_progress(index)
            continue

        tracker.set_status(f"Обновление {title} → {fresh['version_number']}...")
        target = os.path.join(mods_dir(instance_cfg), fresh["file_name"])
        if not _download_file(fresh["url"], target, tracker):
            result["errors"].append(f"{title}: ошибка скачивания")
            tracker.set_progress(index)
            continue

        old = str((info or {}).get("file") or "")
        if old and old != fresh["file_name"]:
            try:
                os.remove(os.path.join(mods_dir(instance_cfg), old))
            except Exception:
                pass
        meta[project_id] = {
            "title":          title,
            "version_id":     fresh["version_id"],
            "version_number": fresh["version_number"],
            "file":           fresh["file_name"],
        }
        result["updated"].append(f"{title} → {fresh['version_number']}")
        tracker.set_progress(index)

    _write_mods_meta(get_mc_dir(instance_cfg), meta)
    _log(f"Обновление модов: обновлено {len(result['updated'])}, "
         f"актуальных {result['kept']}, ошибок {len(result['errors'])}")
    if progress_cb:
        progress_cb(1.0, f"Обновлено модов: {len(result['updated'])}")
    return result


# ─────────────────────────────────────────────────────────────
# ЯЗЫК ИГРЫ (options.txt) — ставим такой же, как язык системы
# ─────────────────────────────────────────────────────────────
GAME_LANG_CODES = {"ru": "ru_ru", "en": "en_us"}


def game_language_code(ui_language: str) -> str:
    """«ru» → «ru_ru», «en» → «en_us» — код языка для Minecraft."""
    return GAME_LANG_CODES.get((ui_language or "").lower(), "en_us")


def apply_game_language(instance_cfg: dict, ui_language: str) -> str:
    """
    Прописывает язык игры в options.txt сборки (как язык системы/лаунчера).
    Возвращает итоговый код языка, "" — не получилось.
    """
    mc_dir = get_mc_dir(instance_cfg)
    if not os.path.isdir(mc_dir):
        return ""

    code = game_language_code(ui_language)
    path = os.path.join(mc_dir, "options.txt")
    lines = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except Exception as e:
            _log(f"Не удалось прочитать options.txt: {e}", "WARN")
            return ""

    new_lines, found, changed = [], False, False
    for line in lines:
        if line.startswith("lang:"):
            found = True
            if line.strip() != f"lang:{code}":
                new_lines.append(f"lang:{code}")
                changed = True
                continue
        new_lines.append(line)
    if not found:
        new_lines.append(f"lang:{code}")
        changed = True

    if not changed:
        return code
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(new_lines) + "\n")
    except Exception as e:
        _log(f"Не удалось записать язык игры в options.txt: {e}", "WARN")
        return ""
    _log(f"Язык игры выставлен: {code} (options.txt сборки)")
    return code


def _do_launch(instance_cfg: dict, account: dict) -> subprocess.Popen:
    mc_dir  = get_mc_dir(instance_cfg)
    version = instance_cfg.get("version", "")
    loader  = instance_cfg.get("loader", "Vanilla")

    # язык игры — как язык системы (можно выключить в настройках лаунчера)
    if instance_cfg.get("sync_game_language", True):
        apply_game_language(instance_cfg, str(instance_cfg.get("ui_language") or ""))

    target_version = _resolve_launch_version(mc_dir, version, loader)
    if not target_version:
        raise RuntimeError(
            f"Версия не установлена: {loader} {version}\n"
            f"Сначала нажмите «Установить» для этой сборки."
        )

    ram = max(512, _safe_int(instance_cfg.get("ram"), 4096))
    safe = safe_ram_mb(ram)
    if safe != ram:
        _log(f"Игре выделено {safe} МБ вместо {ram} МБ (мало свободной памяти/подкачки)", "WARN")
    ram = safe

    raw_jvm = instance_cfg.get("jvm_args", "")
    custom_jvm = _clean_memory_args(
        raw_jvm.split() if isinstance(raw_jvm, str) else list(raw_jvm)
    )

    nickname = account.get("name") or "Player"
    options: dict = {
        "username":        nickname,
        "uuid":            account.get("uuid") or offline_uuid(nickname),
        "token":           account.get("token", ""),           # offline → пустой токен
        "jvmArguments":    custom_jvm,
        "launcherName":    "SimpleCraft",
        "launcherVersion": "1.0",
        "gameDirectory":   mc_dir,                             # корректный путь сборки
    }

    win_w = _safe_int(instance_cfg.get("game_width"), 0)
    win_h = _safe_int(instance_cfg.get("game_height"), 0)
    if win_w > 0 and win_h > 0:
        options["customResolution"] = True
        options["resolutionWidth"]  = str(win_w)
        options["resolutionHeight"] = str(win_h)

    # сервер для «Присоединиться» (приглашение Discord): Minecraft 1.20+ умеет
    # стартовать сразу на сервере через --quickPlayMultiplayer
    server = str(instance_cfg.get("server") or "").strip()
    if server:
        options["quickPlayMultiplayer"] = server
        _log(f"Игра стартует на сервере: {server}")

    # Java: кастомная → рантайм сборки → системная/скачанная под версию
    java_path = ensure_java_runtime(instance_cfg, target_version) \
        or get_java_path(instance_cfg, target_version)
    if java_path and os.path.isfile(java_path):
        options["executablePath"] = java_path
        _log(f"Java: {java_path}")

    cmd = minecraft_launcher_lib.command.get_minecraft_command(
        target_version, mc_dir, options
    )
    cmd = _force_memory_args(cmd, ram)

    _log(f"Запуск: «{instance_cfg.get('name')}» [{loader} {version}] от {nickname}")
    _log(f"Команда: {' '.join(cmd[:5])}... (всего {len(cmd)} аргументов)")

    # creationflags на Windows убирает лишнее консольное окно
    kwargs: dict = {
        "cwd":    mc_dir,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "bufsize": 1,
        "universal_newlines": True,
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    proc = subprocess.Popen(cmd, **kwargs)
    _log(f"Процесс запущен, PID={proc.pid}")
    return proc


def launch(instance_cfg: dict, account: dict) -> subprocess.Popen:
    """
    Запускает Java-процесс с Minecraft.
    Возвращает subprocess.Popen; при ошибке пишет её в get_last_error() и бросает исключение.
    """
    try:
        _check_mll()
        return _do_launch(instance_cfg, account)
    except Exception as e:
        _log(f"Ошибка запуска «{instance_cfg.get('name')}»: {e}", "ERROR")
        raise
