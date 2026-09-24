"""
discord_rpc.py — Discord Rich Presence для Simple Craft Launcher
=================================================================
pypresence — НЕобязательная зависимость: если её нет (или не указан ID
приложения Discord), класс просто сообщает об этом и ничего не делает.

    rpc = DiscordRPC(client_id, join_callback=cb, logger=log.log)
    rpc.start()
    rpc.set_activity(details="Minecraft 1.21.4", state="Fabric", start=time.time())
    rpc.stop()
"""

import threading

try:
    from pypresence import Presence
except Exception:                      # pypresence не установлен — не беда
    Presence = None

# ID приложения из Discord Developer Portal. Можно оставить пустым:
# тогда пользователь впишет свой ID в «Настройках лаунчера».
DEFAULT_CLIENT_ID = "1552623451720781854"


class DiscordRPC:
    """Статус «играет в Minecraft» в профиле Discord + приём приглашений."""

    def __init__(self, client_id: str, join_callback=None, logger=None):
        self.client_id     = str(client_id or DEFAULT_CLIENT_ID).strip()
        self.join_callback = join_callback
        self._log          = logger or (lambda msg, level="INFO": None)
        self._presence     = None
        self._state        = {}
        self._stop         = threading.Event()
        self._lock         = threading.Lock()
        self._thread       = None
        self._listener     = None

    @property
    def available(self) -> bool:
        """Есть ли шанс, что статус заработает."""
        return Presence is not None and bool(self.client_id)

    # ── управление ────────────────────────────────────────────
    def start(self) -> bool:
        if Presence is None:
            self._log("Discord RPC: библиотека pypresence не установлена — статус выключен",
                      "WARN")
            return False
        if not self.client_id:
            self._log("Discord RPC: не указан ID приложения Discord — статус выключен",
                      "WARN")
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def set_activity(self, **fields):
        """Что показывать в статусе (пустые поля игнорируются)."""
        with self._lock:
            self._state = {k: v for k, v in fields.items() if v not in (None, "", -1)}

    def clear(self):
        with self._lock:
            self._state = {}

    def stop(self):
        """Отключает статус (и закрывает соединение с Discord)."""
        self._stop.set()
        self._close_quiet()
        self._thread = None

    # ── внутреннее ────────────────────────────────────────────
    def _run(self):
        while not self._stop.is_set():
            try:
                self._connect()
                while not self._stop.is_set():
                    self._push()
                    self._stop.wait(15)          # Discord любит редкие обновления
            except Exception as e:
                self._log(f"Discord RPC: {e}", "WARN")
                self._presence = None
                self._stop.wait(20)
        self._close_quiet()

    def _connect(self):
        presence = Presence(self.client_id)
        presence.connect()
        self._presence = presence
        self._log("Discord RPC подключён")
        if callable(self.join_callback) and self._listener is None:
            self._listener = threading.Thread(target=self._listen, daemon=True)
            self._listener.start()

    def _push(self):
        with self._lock:
            state = dict(self._state)
        presence = self._presence
        if presence is None:
            return
        if state:
            presence.update(**state)
        else:
            try:
                presence.clear_activity()
            except Exception:
                pass

    def _listen(self):
        """События Discord: ACTIVITY_JOIN — друг нажал «Присоединиться»."""
        while not self._stop.is_set():
            presence = self._presence
            reader   = getattr(presence, "read", None) if presence else None
            if not callable(reader):
                self._stop.wait(30)
                continue
            try:
                payload = reader()
            except Exception:
                self._stop.wait(5)
                continue
            if isinstance(payload, dict) and payload.get("cmd") == "ACTIVITY_JOIN":
                secret = ""
                args   = payload.get("args")
                if isinstance(args, dict):
                    secret = str(args.get("secret") or "")
                self._log("Discord: кто-то хочет присоединиться к игре")
                try:
                    self.join_callback(secret)
                except Exception as e:
                    self._log(f"Discord join error: {e}", "WARN")

    def _close_quiet(self):
        presence, self._presence = self._presence, None
        if presence is None:
            return
        try:
            presence.clear_activity()
        except Exception:
            pass
        try:
            presence.close()
        except Exception:
            pass
