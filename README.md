# TG Admin Tools

Desktop GUI (PySide6) for Telegram channel/group administration, built on Telethon.
UI is switchable between **English** and **Русский** (menu → Language).

## Tools (one tab each)

| Tab | What it does |
|---|---|
| 💾 **Backup deleted** | Exports messages deleted in the last ~48 h from a group's admin log (requires admin). Saves `dump.json` + media files named by message ID. |
| 📤 **Restore to topic** | Re-sends a backup into any chat, optionally into a specific forum topic. Daily date separators, size limit for media, resume, "start after text" search. |
| 🔁 **Repost channel** | Reposts every post (albums included) from one channel to another, oldest first. Modes: **Copy** (no "Forwarded from" tag) or **Forward** (keeps the tag). Optional 📊 stats message (views / forwards / reactions / link) before each post, optional **delete original** after repost. Resumable. |
| 🔀 **Repost group** | Like Repost channel, but only relays messages inside a group that were themselves forwarded from one chosen author/channel — handy when a group mixes reposts from many sources. **Count matches** first to sanity-check the filter before running for real. |
| 🧹 **Cleaner** | Deletes ALL messages in a channel/group where you have delete rights, except posts on a **keep list** (add by ID/link, or scan-and-review a pasted list — kept albums are kept whole). Requires typing `DELETE` to confirm. |
| 🧮 **Users diff** | Fetches the member lists of two groups and compares them: only in A, only in B, in both, or in either. Copy a username or open a member in Telegram from the results table; export the comparison as HTML. |
| 🖼 **Post replacer** | Edits existing posts in a channel: swap in a new image and/or rewrite the caption, per post. Load a range/list of post IDs (with optional skip list), then bulk-fill or set image/text per row — leaving a row blank keeps the original. |

## Config

- Stored as JSON in the OS-appropriate location
  (macOS `~/Library/Application Support/TgAdminTools/`,
  Windows `%APPDATA%\TgAdminTools\`,
  Linux `~/.config/TgAdminTools/`).
- **Named profiles** — keep several accounts / channel sets and switch instantly.
- **Import / Export `.env`** — compatible with the original scripts' `.env` format
  (`API_ID`, `API_HASH`, `PHONE_NUMBER`, `CHANNEL_ID`, `CHAT_ID`, `TOPIC_ID`,
  `SOURCE_CHANNEL`, `TARGET_CHANNEL`).
- Telethon sessions and per-tool progress files are stored per profile, so
  every tool resumes where it stopped.
- Step-by-step instructions for getting `API_ID` / `API_HASH` from
  my.telegram.org are shown right in the Config tab.

Login (SMS code and 2FA password) happens in GUI dialogs on first run;
after that the saved session is reused.

## Run from source

```bash
./run_dev.sh          # macOS / Linux
run_dev.bat           # Windows
```

or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build binaries

Each script produces **both** variants: a single-file executable and a
folder/.app bundle (faster startup).

```bash
scripts/build_mac.sh      # → dist/onefile/TgAdminTools + dist/app/TgAdminTools.app
scripts/build_linux.sh    # → dist/onefile/TgAdminTools + dist/onedir/TgAdminTools/
scripts\build_win.bat     # → dist\onefile\TgAdminTools.exe + dist\onedir\TgAdminTools\
```

Notes:
- Binaries must be built **on** the target OS (PyInstaller doesn't cross-compile).
- macOS: unsigned app → right-click → Open the first time, or
  `xattr -dr com.apple.quarantine TgAdminTools.app`.
- Linux: if Qt complains about `xcb`, install `libxcb-cursor0`.

## Safety notes

- **Cleaner** and **Delete original** are irreversible. Test on a spare channel.
- Deleting/reposting other people's content may violate Telegram ToS or local
  law — use only on channels you administer.
- The admin log only keeps deleted messages for about 48 hours; back up promptly.

---

## Кратко по-русски

GUI для админских скриптов Telegram: бэкап удалённых сообщений из журнала
администратора, восстановление бэкапа в чат/топик, репост канала в канал
(копией без пометки «Переслано из» или обычной пересылкой, со статистикой
и/или удалением оригинала), полная очистка канала.

- Язык интерфейса переключается в меню **Language**.
- Настройки — вкладка «Настройки»: профили, импорт/экспорт `.env`,
  инструкция по получению `API_ID` / `API_HASH` прямо в окне.
- Запуск из исходников: `./run_dev.sh` (или `run_dev.bat`).
- Сборка бинарников: `scripts/build_mac.sh`, `scripts/build_linux.sh`,
  `scripts\build_win.bat` — каждая делает и один файл, и папку/.app.
