<div align="center">

# 🎮 Simple Craft Launcher

**Простой лаунчер Minecraft: отдельные сборки, моды в один клик, всё на твоём диске**

![Лицензия: GPL-3.0](https://img.shields.io/badge/%D0%BB%D0%B8%D1%86%D0%B5%D0%BD%D0%B7%D0%B8%D1%8F-GPL--3.0-blue)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-yellow)
![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D6)
![Версия 1.0](https://img.shields.io/badge/%D0%B2%D0%B5%D1%80%D1%81%D0%B8%D1%8F-1.0-success)

<!-- Скриншот (необязательно): положи картинку в assets/screenshot.png
     и вставь сюда строку: ![Скриншот](assets/screenshot.png) -->

</div>

---

## ⬇️ Как играть (для игроков)

**Просто запусти `SimpleCraftLauncher.exe`** — больше ставить ничего не нужно: Python,
библиотеки, игра и Java уже позаботятся сами.

1. 📥 Скачай `SimpleCraftLauncher.exe` из [последнего релиза](https://github.com/artemiy207/Simple-Craft-Launcher/releases)
   (или собери сам — см. [DEVELOPERS.md](DEVELOPERS.md)).
2. ▶️ Запусти его. Windows может попросить подтверждение — это нормально для новых программ.
3. 📂 При первом запуске лаунчер спросит, **куда ставить сборки**: «Да» (рядом с собой) или «Нет» (выбрать папку).
4. ➕ Нажми **«Добавить»**, выбери версию Minecraft и загрузчик, затем **«Установить»**.
5. 🎮 Когда установка закончится — жми **«Играть»**.

> 💡 Ставь игру на диск, где есть место (например `B:`). На `C:` место заканчивается быстро,
> и тогда Minecraft падает с ошибкой памяти — лаунчер сам подскажет, если так вышло.

---

## ✨ Что умеет

- 🧩 **Изолированные сборки** — у каждой свой `mods`, `resourcepacks`, `shaderpacks`, `saves`, `config`. Сборки больше не конфликтуют между собой.
- ⚡ **Установка в один клик** — Minecraft и загрузчик (Vanilla, Fabric, Forge, NeoForge, Quilt) качаются сами, а после обрыва сети докачиваются.
- ☕ **Java подбирается автоматически** — если нужной версии нет в системе, лаунчер скачает её внутрь сборки.
- 💾 **Игра ставится на твой диск, а не на `C:`** — папку выбираешь при первом запуске, поменять можно в настройках (лаунчер предложит перенести готовые сборки).
- 🧩 **Менеджер модов (Modrinth)** — кнопка «Моды»: поиск, установка, удаление и **«Обновить все моды»** одной кнопкой.
- 🗄 **Бэкапы миров** — автоматически перед установкой/обновлением плюс кнопка «Сделать бэкап сейчас» и восстановление в один клик (хранятся последние 10).
- 📦 **Обмен сборками** — «Поделиться сборкой» делает лёгкий файл: ZIP для этого лаунчера или **`.mrpack`** (открывается в Prism Launcher и Modrinth App). У друга игра докачается сама.
- 🎫 **Discord Rich Presence** — в профиле видно, во что играешь; можно разрешить друзьям присоединяться.
- 🎨 **15 тем** — переключаются мгновенно, без перезапуска.
- 🌐 **Русский и English** — язык берётся из системы (русская Windows → русский, любая
  другая → английский), в настройках можно выбрать «Авто» или конкретный язык.
- 🗣 **Язык игры как в системе** — лаунчер сам прописывает язык Minecraft в `options.txt`
  сборки (русская система → `ru_ru`, любая другая → `en_us`). Отключается галочкой
  в «Настройках лаунчера».
- ✨ **Анимации загрузки** — при установке сборки бежит полоса с крутящимися точками
  (пока процент неизвестен), а кнопка «Обновить версии» показывает «Обновление версий…»
  и блокируется, пока идёт загрузка списка.
- 🆘 **Принудительный запуск** — если памяти/файла подкачки не хватает, лаунчер предупредит
  и предложит запустить игру всё равно (или разрешить это галочкой в настройках).
- 🧠 **Понятные ошибки** — если памяти не хватает, лаунчер объяснит причину и что делать, а не просто закроет игру.
- 👤 **Offline-аккаунты** со стабильным UUID, окно **«Консоль»** и логи для разбирательств.

---

## ⌨️ Горячие клавиши

| Клавиши | Действие |
|---|---|
| `F5` / `Ctrl+R` | обновить список версий Minecraft |
| `Ctrl+N` | новая сборка |
| `Ctrl+L` | окно «Консоль» |
| `F1` | настройки лаунчера |
| двойной клик по карточке | запустить сборку |
| правый клик по карточке | меню: играть / настройки / открыть папку / удалить |

---

## 📁 Где что лежит

```
SimpleCraftLauncher.exe      сам лаунчер
data/                        настройки, аккаунты, логи
<папка сборок>/<сборка>/     игра: versions, libraries, assets, mods, saves, runtime
<сборка>/backups/            бэкапы миров (автоматически и по кнопке)
```

---

## ❓ Частые вопросы

**Игра падает через пару секунд, в логе «файл подкачки слишком мал».**
Windows не хватает виртуальной памяти: `Параметры → Система → О системе → Дополнительные
параметры системы → Быстродействие: Параметры → Дополнительно → Виртуальная память → Изменить`
→ поставить 8192–16384 МБ на диске, где есть место → перезагрузка.

**Игра не запускается из-за «мало памяти».**
Лаунчер напишет причину и предложит два пути: открыть настройки виртуальной памяти Windows
(правильный) или **запустить всё равно** — на свой риск, игра может зависнуть или вылететь.
Можно один раз разрешить это галочкой «Разрешить принудительный запуск при нехватке памяти».

**Хочу другой язык в игре.**
Сними галочку «Ставить язык игры таким же, как язык лаунчера (системы)» в настройках и выбери
язык внутри Minecraft (Options → Language). По умолчанию язык игры подстраивается под систему
и лаунчер (русская Windows → `ru_ru`, любая другая → `en_us`).

**Моды не работают.**
Посмотри бейдж на карточке сборки: моды поддерживают **Fabric / Forge / NeoForge / Quilt**,
в Vanilla их подключить нельзя.

**Куда попадают моды из менеджера?**
В `<сборка>/mods` — кнопка «Открыть mods» откроет эту папку.

**«ID приложения Discord» — что это?**
Необязательно, нужно только для статуса «играю в Minecraft». Как получить — в
[DEVELOPERS.md](DEVELOPERS.md#-discord-rich-presence).

---

## ❤️ Поддержать автора

Спасибо, если лаунчер пригодился! Кнопка **«О лаунчере»** в верхней панели ведёт на страницы
поддержки:

- 🟠 [Boosty](https://boosty.to/tyomik)
- 💜 [DonationAlerts](https://dalink.to/tyomik_3212)
- ⭐ Поставь звезду репозиторию — это тоже очень помогает

---

## 👨‍💻 Для разработчиков

Структура проекта, API ядра, переводы, темы, сборка EXE и правила участия — в отдельном файле
**[DEVELOPERS.md](DEVELOPERS.md)**.

---

# 🇬🇧 English (for players)

**Just run `SimpleCraftLauncher.exe`** — nothing else to install: Python, libraries, the game and
Java are handled by the launcher.

1. 📥 Download `SimpleCraftLauncher.exe` from the latest release.
2. ▶️ Run it (Windows may ask for confirmation — that's normal for new apps).
3. 📂 On the first run choose the folder for your instances (next to the launcher or your own).
4. ➕ Press **Add**, pick a Minecraft version and a loader, press **Install**.
5. 🎮 When it finishes — press **Play**.

**Features:** isolated instances (own mods, packs and saves), one-click install of Minecraft and
Vanilla/Fabric/Forge/NeoForge/Quilt, automatic Java download, everything installed on *your* drive
(not `C:`), Modrinth mod manager with “Update all mods”, automatic world backups (last 10 kept) with
one-click restore, instance sharing as ZIP or `.mrpack`, Discord Rich Presence with optional join
requests, 15 themes, Russian/English, clear memory diagnostics, offline accounts, built-in console
and logs.

**Hotkeys:** `F5` / `Ctrl+R` refresh versions · `Ctrl+N` new instance · `Ctrl+L` console ·
`F1` settings · double-click a card to play · right-click for more.

**FAQ:** the game crashes with “page file too small” → increase the Windows page file (give Windows
8–16 GB on a drive with free space and reboot). Mods need a Fabric/Forge/NeoForge/Quilt instance,
not Vanilla.

**Support the author:** links are in the launcher's “About” window. ⭐

Developers: see **[DEVELOPERS.md](DEVELOPERS.md)**.

---

<div align="center">

Сделано с ❤️ для игроков в Minecraft · лицензия **GPL-3.0** · Minecraft © Mojang Studios

</div>

