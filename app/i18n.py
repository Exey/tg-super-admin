"""Very small dictionary-based i18n (EN / RU, switchable at runtime)."""
from __future__ import annotations

EN = {
    "app_title": "TG Admin Tools",
    # tabs
    "tab_config": "⚙️ Config",
    "tab_backup": "💾 Backup deleted",
    "tab_restore": "📤 Restore to topic",
    "tab_repost": "🔁 Repost channel",
    "tab_cleaner": "🧹 Cleaner",
    # generic
    "run": "▶ Run",
    "stop": "⏹ Stop",
    "browse": "Browse…",
    "save": "💾 Save profile",
    "saved": "Profile saved.",
    "log": "Log",
    "done_ok": "✅ Finished: {msg}",
    "done_fail": "❌ Failed: {msg}",
    "cancelled": "⏹ Cancelled by user.",
    "missing_conn": "Fill in API_ID, API_HASH and PHONE_NUMBER on the Config tab first.",
    "worker_running": "A task is still running. Stop it first.",
    "reset_progress": "Reset saved progress",
    "progress_reset": "Progress file removed.",
    "delay": "Delay between messages (s)",
    # menus
    "menu_file": "File",
    "menu_language": "Language",
    "menu_help": "Help",
    "import_env": "Import .env into current profile…",
    "export_env": "Export current profile as .env…",
    "open_config_folder": "Open config folder",
    "quit": "Quit",
    "lang_en": "English",
    "lang_ru": "Русский",
    "env_imported": "Imported {n} value(s) from .env.",
    # config tab
    "profile": "Profile",
    "new_profile": "New…",
    "delete_profile": "Delete",
    "profile_name": "Profile name:",
    "delete_profile_confirm": "Delete profile “{name}”?",
    "instructions_title": "📖 How to get API_ID and API_HASH",
    "instructions_text": (
        "1. Open <a href='https://my.telegram.org'>my.telegram.org</a> and log in "
        "with your phone number (Telegram sends the code to your Telegram app).<br>"
        "2. Click <b>API development tools</b>.<br>"
        "3. Fill in <i>App title</i> and <i>Short name</i> (any text), "
        "platform <i>Desktop</i>, then create the application.<br>"
        "4. Copy <b>App api_id</b> → API_ID and <b>App api_hash</b> → API_HASH.<br>"
        "5. PHONE_NUMBER must be in international format, e.g. <code>+79001234567</code>.<br><br>"
        "<b>Where do channel / chat IDs come from?</b><br>"
        "• Forward any post from the channel to <code>@userinfobot</code> or open the chat in "
        "<a href='https://web.telegram.org'>web.telegram.org</a> — the number in the URL, "
        "prefixed with <code>-100</code>, is the ID (e.g. <code>-1002805046984</code>).<br>"
        "• TOPIC_ID is the number in a forum topic's link "
        "(<code>t.me/c/…/<b>133737</b></code>).<br>"
        "• Public channels can also be given as <code>@username</code>."
    ),
    "field_API_ID": "API_ID",
    "field_API_HASH": "API_HASH",
    "field_PHONE_NUMBER": "PHONE_NUMBER",
    "field_CHANNEL_ID": "CHANNEL_ID (group, for Backup / Cleaner)",
    "field_CHAT_ID": "CHAT_ID (Restore target)",
    "field_TOPIC_ID": "TOPIC_ID (Restore topic, empty = none)",
    "field_SOURCE_CHANNEL": "SOURCE_CHANNEL (Repost from)",
    "field_TARGET_CHANNEL": "TARGET_CHANNEL (Repost to)",
    "config_location": "Config file: {path}",
    # login
    "login_code_prompt": "Enter the login code Telegram just sent you:",
    "login_password_prompt": "Enter your two-factor (2FA) password:",
    "login_title": "Telegram login",
    # backup tab
    "backup_help": "Exports messages deleted in the last 48 h from the admin log "
                   "of a group/channel where you are admin. Saves dump.json + media files.",
    "backup_group": "Group / channel ID or @username",
    "backup_mode": "Export mode",
    "mode_all": "All (text + media)",
    "mode_media": "Media only",
    "mode_text": "Text only",
    "min_id": "Min message ID (0 = no limit)",
    "max_id": "Max message ID (0 = no limit)",
    "output_folder": "Output folder",
    # restore tab
    "restore_help": "Re-sends a backup (dump.json + media) into a chat, optionally "
                    "into a specific forum topic. Resumes automatically.",
    "restore_folder": "Backup folder (contains dump.json)",
    "restore_chat": "Chat ID",
    "restore_topic": "Topic ID (0 = none)",
    "daily_sep": "Insert daily date separator (---= 2025-01-31 =---)",
    "max_size": "Max media size, MB (bigger → text only)",
    "skip_big": "Skip whole message if media too big",
    "start_index": "Start from index (0 = resume from progress)",
    "search_text": "…or start after message containing text",
    # repost tab
    "repost_help": "Reposts every post (incl. albums) from one channel to another, "
                   "oldest first. Resumes automatically via progress file.",
    "repost_source": "Source channel",
    "repost_target": "Target channel",
    "repost_mode": "Repost mode",
    "mode_copy": "Copy — fresh message, no “Forwarded from” tag",
    "mode_forward": "Forward — keeps the “Forwarded from” tag",
    "send_stats": "Send a 📊 stats message before each post (views / forwards / reactions / link)",
    "delete_original": "⚠ Delete original message from source after repost",
    "delete_original_note": "Deletion is irreversible. Test on a spare channel first!",
    "start_from_id": "Start after message ID (0 = resume from progress)",
    # cleaner tab
    "cleaner_help": "Deletes ALL messages in a channel/group where you have "
                    "“Delete messages” admin right.",
    "cleaner_channel": "Channel / group ID or @username",
    "batch_size": "Batch size",
    "cleaner_warning": "⚠️ THIS DELETES EVERY MESSAGE IN THE CHANNEL. IRREVERSIBLE.",
    "confirm_title": "Confirm deletion",
    "confirm_delete_prompt": "Type DELETE to confirm wiping all messages:",
    "confirm_word": "DELETE",
    "confirm_wrong": "Confirmation text did not match — aborted.",
}

RU = {
    "app_title": "TG Admin Tools",
    "tab_config": "⚙️ Настройки",
    "tab_backup": "💾 Бэкап удалённых",
    "tab_restore": "📤 Восстановить в топик",
    "tab_repost": "🔁 Репост канала",
    "tab_cleaner": "🧹 Очистка",
    "run": "▶ Запустить",
    "stop": "⏹ Остановить",
    "browse": "Обзор…",
    "save": "💾 Сохранить профиль",
    "saved": "Профиль сохранён.",
    "log": "Журнал",
    "done_ok": "✅ Готово: {msg}",
    "done_fail": "❌ Ошибка: {msg}",
    "cancelled": "⏹ Остановлено пользователем.",
    "missing_conn": "Сначала заполните API_ID, API_HASH и PHONE_NUMBER на вкладке «Настройки».",
    "worker_running": "Задача ещё выполняется. Сначала остановите её.",
    "reset_progress": "Сбросить сохранённый прогресс",
    "progress_reset": "Файл прогресса удалён.",
    "delay": "Пауза между сообщениями (сек)",
    "menu_file": "Файл",
    "menu_language": "Язык",
    "menu_help": "Справка",
    "import_env": "Импортировать .env в текущий профиль…",
    "export_env": "Экспортировать профиль как .env…",
    "open_config_folder": "Открыть папку настроек",
    "quit": "Выход",
    "lang_en": "English",
    "lang_ru": "Русский",
    "env_imported": "Импортировано значений из .env: {n}.",
    "profile": "Профиль",
    "new_profile": "Новый…",
    "delete_profile": "Удалить",
    "profile_name": "Имя профиля:",
    "delete_profile_confirm": "Удалить профиль «{name}»?",
    "instructions_title": "📖 Как получить API_ID и API_HASH",
    "instructions_text": (
        "1. Откройте <a href='https://my.telegram.org'>my.telegram.org</a> и войдите "
        "по номеру телефона (код придёт в приложение Telegram).<br>"
        "2. Нажмите <b>API development tools</b>.<br>"
        "3. Заполните <i>App title</i> и <i>Short name</i> (любой текст), "
        "платформа <i>Desktop</i>, создайте приложение.<br>"
        "4. Скопируйте <b>App api_id</b> → API_ID и <b>App api_hash</b> → API_HASH.<br>"
        "5. PHONE_NUMBER — в международном формате, например <code>+79001234567</code>.<br><br>"
        "<b>Откуда брать ID каналов и чатов?</b><br>"
        "• Перешлите любой пост боту <code>@userinfobot</code> или откройте чат в "
        "<a href='https://web.telegram.org'>web.telegram.org</a> — число из URL с префиксом "
        "<code>-100</code> и есть ID (например <code>-1002805046984</code>).<br>"
        "• TOPIC_ID — число из ссылки на топик форума "
        "(<code>t.me/c/…/<b>133737</b></code>).<br>"
        "• Публичные каналы можно указывать как <code>@username</code>."
    ),
    "field_API_ID": "API_ID",
    "field_API_HASH": "API_HASH",
    "field_PHONE_NUMBER": "PHONE_NUMBER",
    "field_CHANNEL_ID": "CHANNEL_ID (группа — для Бэкапа / Очистки)",
    "field_CHAT_ID": "CHAT_ID (куда восстанавливать)",
    "field_TOPIC_ID": "TOPIC_ID (топик, пусто = без топика)",
    "field_SOURCE_CHANNEL": "SOURCE_CHANNEL (репост откуда)",
    "field_TARGET_CHANNEL": "TARGET_CHANNEL (репост куда)",
    "config_location": "Файл настроек: {path}",
    "login_code_prompt": "Введите код входа, который прислал Telegram:",
    "login_password_prompt": "Введите пароль двухфакторной аутентификации (2FA):",
    "login_title": "Вход в Telegram",
    "backup_help": "Экспортирует сообщения, удалённые за последние 48 ч, из журнала "
                   "администратора группы/канала. Сохраняет dump.json + медиафайлы.",
    "backup_group": "ID группы/канала или @username",
    "backup_mode": "Режим экспорта",
    "mode_all": "Всё (текст + медиа)",
    "mode_media": "Только медиа",
    "mode_text": "Только текст",
    "min_id": "Мин. ID сообщения (0 = без ограничения)",
    "max_id": "Макс. ID сообщения (0 = без ограничения)",
    "output_folder": "Папка для сохранения",
    "restore_help": "Отправляет бэкап (dump.json + медиа) в чат, при необходимости "
                    "в конкретный топик форума. Возобновляется автоматически.",
    "restore_folder": "Папка бэкапа (с dump.json)",
    "restore_chat": "ID чата",
    "restore_topic": "ID топика (0 = без топика)",
    "daily_sep": "Вставлять разделитель дня (---= 2025-01-31 =---)",
    "max_size": "Макс. размер медиа, МБ (больше → только текст)",
    "skip_big": "Пропускать сообщение целиком, если медиа слишком большое",
    "start_index": "Начать с индекса (0 = продолжить по прогрессу)",
    "search_text": "…или начать после сообщения с текстом",
    "repost_help": "Репостит все посты (включая альбомы) из одного канала в другой, "
                   "от старых к новым. Возобновляется по файлу прогресса.",
    "repost_source": "Канал-источник",
    "repost_target": "Канал-приёмник",
    "repost_mode": "Режим репоста",
    "mode_copy": "Копия — новое сообщение, без пометки «Переслано из»",
    "mode_forward": "Пересылка — с пометкой «Переслано из»",
    "send_stats": "Отправлять 📊 статистику перед каждым постом (просмотры / репосты / реакции / ссылка)",
    "delete_original": "⚠ Удалять оригинал из источника после репоста",
    "delete_original_note": "Удаление необратимо. Сначала проверьте на тестовом канале!",
    "start_from_id": "Начать после сообщения с ID (0 = продолжить по прогрессу)",
    "cleaner_help": "Удаляет ВСЕ сообщения в канале/группе, где у вас есть право "
                    "«Удаление сообщений».",
    "cleaner_channel": "ID канала/группы или @username",
    "batch_size": "Размер пачки",
    "cleaner_warning": "⚠️ УДАЛЯЕТ ВСЕ СООБЩЕНИЯ В КАНАЛЕ. НЕОБРАТИМО.",
    "confirm_title": "Подтверждение удаления",
    "confirm_delete_prompt": "Введите DELETE, чтобы подтвердить удаление всех сообщений:",
    "confirm_word": "DELETE",
    "confirm_wrong": "Текст подтверждения не совпал — отменено.",
}

LANGS = {"en": EN, "ru": RU}


class I18n:
    def __init__(self, lang: str = "en") -> None:
        self.lang = lang if lang in LANGS else "en"

    def tr(self, key: str, **kw) -> str:
        text = LANGS[self.lang].get(key) or EN.get(key) or key
        return text.format(**kw) if kw else text
