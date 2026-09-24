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
"""

import os
import sys
import time
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

MEMORY_ARG_PREFIXES = ("-Xmx", "-Xms")

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
def get_mc_dir(instance_cfg: dict) -> str:
    """Возвращает рабочую директорию инстанса."""
    isolation = instance_cfg.get("isolation", "isolated")
    if isolation == "shared":
        if minecraft_launcher_lib:
            return minecraft_launcher_lib.utils.get_minecraft_directory()
        home = os.path.expanduser("~")
        if platform.system() == "Windows":
            return os.path.join(os.environ.get("APPDATA", home), ".minecraft")
        return os.path.join(home, ".minecraft")

    name = instance_cfg.get("name")
    if not name:
        if minecraft_launcher_lib:
            return minecraft_launcher_lib.utils.get_minecraft_directory()
        return os.path.join(ROOT, "instances", "_default")
    return os.path.join(ROOT, "instances", name)


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
    xms = min(max(512, ram // 4), ram)
    return [java_exe, f"-Xmx{ram}M", f"-Xms{xms}M", *rest]


def _check_mll():
    if minecraft_launcher_lib is None:
        raise RuntimeError(
            "minecraft-launcher-lib не установлен.\n"
            "Запустите: pip install minecraft-launcher-lib"
        )


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
def is_installed(instance_cfg: dict) -> bool:
    if minecraft_launcher_lib is None:
        _log("Проверка установки: minecraft-launcher-lib не установлен", "WARN")
        return False

    mc_dir  = get_mc_dir(instance_cfg)
    version = instance_cfg.get("version", "")
    loader  = instance_cfg.get("loader", "Vanilla")

    resolved = _resolve_launch_version(mc_dir, version, loader)
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

    tracker  = ProgressTracker(progress_cb)
    callback = _make_callback(tracker)

    attempts   = max(1, _safe_int(instance_cfg.get("download_retries"), 3))
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

    if progress_cb:
        progress_cb(0.0, f"Ошибка: {last_error}")
    return _fail(f"Ошибка установки «{name}» [{loader} {version}]: {last_error}")


def _do_launch(instance_cfg: dict, account: dict) -> subprocess.Popen:
    mc_dir  = get_mc_dir(instance_cfg)
    version = instance_cfg.get("version", "")
    loader  = instance_cfg.get("loader", "Vanilla")

    target_version = _resolve_launch_version(mc_dir, version, loader)
    if not target_version:
        raise RuntimeError(
            f"Версия не установлена: {loader} {version}\n"
            f"Сначала нажмите «Установить» для этой сборки."
        )

    ram = max(512, _safe_int(instance_cfg.get("ram"), 4096))

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
        "launcherVersion": "3.0",
        "gameDirectory":   mc_dir,                             # корректный путь сборки
    }

    win_w = _safe_int(instance_cfg.get("game_width"), 0)
    win_h = _safe_int(instance_cfg.get("game_height"), 0)
    if win_w > 0 and win_h > 0:
        options["customResolution"] = True
        options["resolutionWidth"]  = str(win_w)
        options["resolutionHeight"] = str(win_h)

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
