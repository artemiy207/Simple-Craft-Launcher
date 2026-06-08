import os
import sys
import subprocess
import uuid
import minecraft_launcher_lib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_ARG_PREFIXES = ("-Xmx", "-Xms")

class ProgressTracker:
    """Удобный трекер для маппинга статусов MLL в наш прогресс-бар"""
    def __init__(self, cb):
        self.cb = cb
        self.maximum = 100
        self.curr = 0
        self.status = "Подготовка..."
        
    def set_status(self, s):
        self.status = s
        self._push()
        
    def set_progress(self, p):
        self.curr = p
        self._push()
        
    def set_max(self, m):
        self.maximum = m
        
    def _push(self):
        if self.cb:
            val = self.curr / self.maximum if self.maximum > 0 else 0
            self.cb(val, self.status)

def get_mc_dir(instance_cfg: dict) -> str:
    """Определяет директорию игры на основе настроек"""
    isolation = instance_cfg.get("isolation", "isolated")
    if isolation == "shared":
        # Используем стандартный .minecraft пользователя (AppData/Roaming/.minecraft)
        return minecraft_launcher_lib.utils.get_minecraft_directory()
    else:
        # Изолированная портативная папка
        name = instance_cfg.get("name")
        if not name:
            return minecraft_launcher_lib.utils.get_minecraft_directory()
        return os.path.join(ROOT, "instances", name)

def _installed_ids(mc_dir: str) -> list[str]:
    try:
        return [v["id"] for v in minecraft_launcher_lib.utils.get_installed_versions(mc_dir)]
    except Exception:
        return []

def _resolve_launch_version(mc_dir: str, version: str, loader: str) -> str | None:
    ids = _installed_ids(mc_dir)
    if loader == "Vanilla":
        return version if version in ids else None

    loader_key = loader.lower()
    for installed_id in ids:
        low = installed_id.lower()
        if version in installed_id and loader_key in low:
            return installed_id
    return None

def _clean_memory_args(args: list[str]) -> list[str]:
    return [
        arg for arg in args
        if not any(arg.startswith(prefix) for prefix in MEMORY_ARG_PREFIXES)
    ]

def _force_memory_args(cmd: list[str], ram: int) -> list[str]:
    if not cmd:
        return cmd
    cleaned = [cmd[0], *_clean_memory_args(cmd[1:])]
    xms = min(max(1024, ram // 4), ram)
    cleaned[1:1] = [f"-Xmx{ram}M", f"-Xms{xms}M"]
    return cleaned

def is_installed(instance_cfg: dict) -> bool:
    mc_dir = get_mc_dir(instance_cfg)
    version = instance_cfg.get("version")
    loader = instance_cfg.get("loader", "Vanilla")
    return bool(_resolve_launch_version(mc_dir, version, loader))

def install(instance_cfg: dict, progress_cb=None) -> bool:
    """Устанавливает игру (Vanilla / Forge / Fabric)"""
    mc_dir = get_mc_dir(instance_cfg)
    version = instance_cfg.get("version")
    loader = instance_cfg.get("loader", "Vanilla")
    
    tracker = ProgressTracker(progress_cb)
    callback = {
        "setStatus": tracker.set_status,
        "setProgress": tracker.set_progress,
        "setMax": tracker.set_max
    }
    
    try:
        # Устанавливаем в зависимости от выбранного загрузчика
        if loader == "Vanilla":
            minecraft_launcher_lib.install.install_minecraft_version(version, mc_dir, callback=callback)
        elif loader == "Fabric":
            minecraft_launcher_lib.fabric.install_fabric(version, mc_dir, callback=callback)
        elif loader == "Forge":
            minecraft_launcher_lib.forge.install_forge_version(version, mc_dir, callback=callback)
        else:
            if progress_cb:
                progress_cb(0.0, f"Загрузчик {loader} пока не поддержан установщиком")
            return False
        return True
    except Exception as e:
        print(f"[CORE] Ошибка установки: {e}")
        return False

def launch(instance_cfg: dict, account: dict) -> subprocess.Popen:
    """Генерирует аргументы и запускает Java процесс с игрой"""
    mc_dir = get_mc_dir(instance_cfg)
    version = instance_cfg.get("version")
    loader = instance_cfg.get("loader", "Vanilla")
    
    target_version = _resolve_launch_version(mc_dir, version, loader)
    if not target_version:
        raise RuntimeError(f"Версия не установлена: {loader} {version}")

    ram = int(instance_cfg.get("ram", 4096))
    custom_jvm_args = _clean_memory_args(instance_cfg.get("jvm_args", "").split())
    
    # Настройки пиратского аккаунта
    options = {
        "username": account.get("name", "Player"),
        "uuid": account.get("uuid", str(uuid.uuid4())),
        "token": account.get("token", ""), # В offline моде токен пустой
        "jvmArguments": custom_jvm_args,
        "launcherName": "SimpleCraft",
        "launcherVersion": "3.0"
    }
    
    # Если указана кастомная Java
    java_path = instance_cfg.get("java_path", "").strip()
    if java_path:
        options["executablePath"] = java_path

    # Формируем итоговую команду
    cmd = minecraft_launcher_lib.command.get_minecraft_command(target_version, mc_dir, options)
    cmd = _force_memory_args(cmd, ram)
    
    print(f"[CORE] Строка запуска: {' '.join(cmd)}")
    
    # Запускаем в фоне!
    return subprocess.Popen(cmd, cwd=mc_dir)

def get_java_path(instance_cfg: dict) -> str:
    return instance_cfg.get("java_path") or minecraft_launcher_lib.utils.get_java_executable()

def fetch_versions() -> list:
    """Получить список версий от Mojang"""
    try:
        versions = minecraft_launcher_lib.utils.get_available_versions(get_mc_dir({}))
        return [v["id"] for v in versions if v["type"] == "release"]
    except:
        return []
