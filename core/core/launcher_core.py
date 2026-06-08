"""
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

def launch(instance_cfg: dict, account: dict):
    """Заглушка запуска. Возвращает None пока не реализована."""
    print(f"[CORE] launch() called: {instance_cfg.get('name')} as {account.get('name')}")
    return None

def get_java_path(instance_cfg: dict) -> str:
    return instance_cfg.get("java_path") or ""

def fetch_versions() -> list:
    return []
