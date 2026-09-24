# Simple Craft Launcher

Лаунчер Minecraft на Python (customtkinter) с изолированными сборками.
Поддерживаемые загрузчики: **Vanilla, Fabric, Forge, NeoForge, Quilt**.

## Возможности

- **15 тем оформления** (Dark Slate, AMOLED, Midnight, Forest, Light, Nord, Dracula,
  Sunset, Ocean, Coffee, Cyberpunk, Monokai, Blood Moon, Sakura, Mint) — переключаются
  мгновенно из топбара или из настроек, с живым предпросмотром, без перезапуска
- сборки в отдельных папках `instances/<имя>` — свои `mods/`, `resourcepacks/`, `shaderpacks/`, `saves/`
- карточка сборки показывает цветной бейдж загрузчика, статус «установлена/нет» и RAM,
  сайдбар — сколько модов/ресурспаков/шейдеров/миров в сборке
- автоустановка Minecraft и загрузчика (через `minecraft-launcher-lib` 8.x)
- подбор и автоскачивание нужной версии Java (`java-runtime-*` от Mojang), если её нет в системе
- версия по умолчанию — самая свежая release-версия Mojang; список версий кэшируется и работает офлайн
- offline-аккаунты со стабильным UUID (`md5("OfflinePlayer:<ник>")`)
- окно «Консоль» (кнопка в топбаре или `Ctrl+L`) + лог в `data/launcher.log`,
  вывод игры — в `instances/<сборка>/logs/launcher-game.log`
- авто-повтор установки при сетевых сбоях (докачка продолжается с места обрыва)

## Горячие клавиши

| Клавиши | Действие |
|---|---|
| `F5` / `Ctrl+R` | обновить список версий Minecraft с серверов Mojang |
| `Ctrl+N` | новая сборка |
| `Ctrl+L` | окно «Консоль» |
| `F1` | настройки |
| двойной клик по карточке | запустить сборку |
| правый клик по карточке | меню: играть / настройки / открыть папку / удалить |

## Запуск из исходников

1. Установить Python 3.11+ с python.org (галочка «Add Python to PATH»).
2. Двойной клик по `build.bat` — при первом запуске библиотеки доустановятся сами.
   Либо вручную: `pip install customtkinter pillow requests minecraft-launcher-lib`

## Сборка EXE

`build_exe.bat` → результат в `dist\SimpleCraftLauncher.exe`
(ассеты, шрифт и `core/launcher_core.py` упаковываются внутрь exe).

## Структура

```
Simple-Craft-Launcher.py   # UI (customtkinter)
core/launcher_core.py      # игровая логика: установка, запуск, Java, загрузчики
data/                      # settings.json, accounts.json, versions_cache.json, launcher.log
instances/<сборка>/        # сама сборка: mods/, saves/, logs/, versions/, libraries/ ...
assets/                    # иконки и шрифт
```

## Пока не сделано

- вход через Microsoft (OAuth device-code) — сейчас только offline-аккаунты
- Discord Rich Presence

## Лицензия

Не указана. Перед публикацией репозитория стоит добавить файл LICENSE.
