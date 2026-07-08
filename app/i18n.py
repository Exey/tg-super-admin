"""Very small dictionary-based i18n (EN / RU, switchable at runtime)."""
from __future__ import annotations

EN = {
    "app_title": "TG Admin Tools",
    # tabs
    "tab_config": "⚙️ Config",
    "tab_backup": "💾 Backup deleted",
    "tab_restore": "📤 Restore to topic",
    "tab_repost": "🔁 Repost channel",
    "tab_repost_group": "🔀 Repost group",
    "tab_cleaner": "🧹 Cleaner",
    "tab_users_extractor": "🧮 Users diff",
    "tab_post_replacer": "🖼 Post replacer",
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
    "qr_login_button": "🔳 Login via QR code",
    "qr_login_title": "QR code login",
    "qr_login_hint": "Open Telegram on your phone → Settings → Devices → "
                     "Link Desktop Device, then scan this code.",
    "qr_login_generating": "Generating QR code…",
    "qr_login_waiting": "Waiting for you to scan…",
    "qr_login_expired": "Code expired, generating a new one…",
    "qr_login_success": "Logged in successfully.",
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
    # repost group tab
    "repost_group_help": "Reposts only the messages inside a group that were "
                         "themselves forwarded from one chosen author/channel — "
                         "handy when a group mixes reposts from many sources and "
                         "you only want to relay one of them. Use “Count matches” "
                         "first to confirm you picked the right author/source "
                         "before running the real repost.",
    "repost_group_source": "Source group",
    "repost_group_author": "Only repost forwards from (username, ID, or t.me link "
                           "of the original author/channel)",
    "repost_group_target": "Target Channel/Group",
    "repost_group_need_source_author": "Fill in both the source group and the "
                                       "author/source filter first.",
    "count_matches": "🔢 Count matches",
    # cleaner tab
    "cleaner_help": "Deletes ALL messages in a channel/group where you have "
                    "“Delete messages” admin right — except the posts you add "
                    "to the keep list below. If a kept post is part of an "
                    "album (2–10 media), the whole album is kept.",
    "cleaner_channel": "Channel / group ID or @username",
    "keep_ids": "Keep these posts (skip deletion)",
    "keep_placeholder": "Message ID or t.me link (e.g. 133737 or https://t.me/c/2805046984/133737)",
    "keep_add": "➕ Add",
    "keep_add_list": "📋 Add from list…",
    "keep_open": "🔗 Open",
    "keep_remove": "🗑 Remove",
    "keep_remove_all": "🗑 Remove All",
    "keep_remove_all_confirm": "Remove all posts from the keep list?",
    "keep_hint": "Double-click a row (or press Open) to view the post in "
                 "Telegram and verify it's the right one.",
    "keep_invalid": "Could not parse a message ID from that input.",
    "keep_duplicate": "This message ID is already in the list.",
    "keep_list_title": "Add posts from a list",
    "keep_list_prompt": "Paste message IDs or t.me links, one per line "
                        "(or separated by spaces/commas):",
    "keep_list_found": "Found {n} post(s)/album(s). Review below.",
    "keep_list_empty": "None of the pasted links/IDs could be found.",
    "keep_list_added": "Added {n} message ID(s) to the keep list.",
    "keep_list_dialog_title": "Review before adding to keep list",
    "keep_list_dialog_hint": "Uncheck anything that isn't the post you meant. "
                            "Double-click a row to open it in Telegram and "
                            "confirm the author/source is right. Checked "
                            "posts (whole album if any) are added on OK.",
    "keep_select_all": "Select all",
    "keep_select_none": "Select none",
    "keep_col_link": "Link",
    "keep_col_text": "Post text",
    "keep_col_range": "Album range",
    "batch_size": "Batch size",
    "cleaner_warning": "⚠️ THIS DELETES EVERY MESSAGE IN THE CHANNEL. IRREVERSIBLE.",
    "confirm_title": "Confirm deletion",
    "confirm_delete_prompt": "Type DELETE to confirm wiping all messages:",
    "confirm_word": "DELETE",
    "confirm_wrong": "Confirmation text did not match — aborted.",
    # users extractor tab
    "users_extractor_help": "Fetches the member lists of two groups and lets "
                            "you compare them: who's only in A, only in B, "
                            "in both, or in either. Double-click a user (or "
                            "right-click) to copy their username or open "
                            "them in Telegram.",
    "users_extractor_group_a": "Group A",
    "users_extractor_group_b": "Group B",
    "users_extractor_need_groups": "Fill in both Group A and Group B first.",
    "users_extractor_algo": "Show",
    "algo_a_only": "In A, not in B",
    "algo_b_only": "In B, not in A",
    "algo_intersection": "In both (intersection)",
    "algo_symmetric_diff": "In either, not both (symmetric diff)",
    "users_extractor_col_a": "Group A members",
    "users_extractor_col_b": "Group B members",
    "users_extractor_col_delta": "Result",
    "users_extractor_col_name": "Name",
    "users_extractor_col_username": "Username / ID",
    "users_extractor_copy_username": "📋 Copy username",
    "users_extractor_done": "Group A: {a} member(s). Group B: {b} member(s).",
    "users_extractor_save_html": "💾 Save as HTML…",
    "users_extractor_saved": "Saved to {path}",
    "users_extractor_nothing_to_save": "Nothing to save yet — run the comparison first.",
    # post image replacer tab
    "post_replacer_help": "Edits specific posts in a channel: swap in a new "
                          "image and/or rewrite the caption, one mapping per "
                          "post. Load the post list, optionally skip some "
                          "IDs, then set an image/text per row (or bulk-fill "
                          "and adjust individual rows after). Leaving a "
                          "row's image or text empty keeps the original.",
    "post_replacer_channel": "Channel / group ID or @username",
    "post_replacer_posts": "Posts to edit (IDs, ranges like 100-110, or t.me links)",
    "post_replacer_posts_placeholder": "e.g. 133730-133750, 133780",
    "post_replacer_skip": "Skip these posts (IDs/ranges, left untouched)",
    "post_replacer_skip_placeholder": "e.g. 133735, 133790-133792",
    "post_replacer_load": "📋 Load posts",
    "post_replacer_bulk": "Bulk fill (applies to every row below)",
    "post_replacer_apply_all": "Apply to all rows",
    "post_replacer_table": "Per-post replacement",
    "post_replacer_col_id": "ID",
    "post_replacer_col_link": "Link",
    "post_replacer_col_image": "New image",
    "post_replacer_col_text": "New text",
    "post_replacer_keep_original": "(keep original)",
    "post_replacer_no_posts": "Could not parse any post IDs from that input.",
    "post_replacer_no_rows": "Load posts first, then set at least one new "
                            "image or new text on a row.",
    "post_replacer_bad_image": "Image file not found: {path}",
}

RU = {
    "app_title": "TG Admin Tools",
    "tab_config": "⚙️ Настройки",
    "tab_backup": "💾 Бэкап удалённых",
    "tab_restore": "📤 Восстановить в топик",
    "tab_repost": "🔁 Репост канала",
    "tab_repost_group": "🔀 Репост группы",
    "tab_cleaner": "🧹 Очистка",
    "tab_users_extractor": "🧮 Разница юзеров",
    "tab_post_replacer": "🖼 Замена в постах",
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
    "qr_login_button": "🔳 Вход по QR-коду",
    "qr_login_title": "Вход по QR-коду",
    "qr_login_hint": "Откройте Telegram на телефоне → Настройки → Устройства → "
                     "Подключить устройство и отсканируйте этот код.",
    "qr_login_generating": "Генерация QR-кода…",
    "qr_login_waiting": "Ожидание сканирования…",
    "qr_login_expired": "Код истёк, генерируется новый…",
    "qr_login_success": "Вход выполнен успешно.",
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
    "repost_group_help": "Репостит только те сообщения в группе, которые сами "
                         "являются пересылкой от одного выбранного автора/канала — "
                         "удобно, когда в группе смешаны репосты из разных "
                         "источников, а нужен только один из них. Сначала "
                         "нажмите «Посчитать совпадения», чтобы убедиться, что "
                         "автор/источник выбран верно, прежде чем запускать репост.",
    "repost_group_source": "Группа-источник",
    "repost_group_author": "Репостить только пересылки от (username, ID или "
                           "ссылка t.me на автора/канал-оригинал)",
    "repost_group_target": "Канал/группа-приёмник",
    "repost_group_need_source_author": "Сначала укажите группу-источник и "
                                       "фильтр автора/источника.",
    "count_matches": "🔢 Посчитать совпадения",
    "cleaner_help": "Удаляет ВСЕ сообщения в канале/группе, где у вас есть право "
                    "«Удаление сообщений» — кроме постов из списка исключений "
                    "ниже. Если сохранённый пост — часть альбома (2–10 медиа), "
                    "альбом сохраняется целиком.",
    "cleaner_channel": "ID канала/группы или @username",
    "keep_ids": "Сохранить эти посты (не удалять)",
    "keep_placeholder": "ID сообщения или ссылка t.me (напр. 133737 или https://t.me/c/2805046984/133737)",
    "keep_add": "➕ Добавить",
    "keep_add_list": "📋 Добавить из списка…",
    "keep_open": "🔗 Открыть",
    "keep_remove": "🗑 Убрать",
    "keep_remove_all": "🗑 Убрать все",
    "keep_remove_all_confirm": "Убрать все посты из списка сохранения?",
    "keep_hint": "Двойной клик по строке (или «Открыть») — откроет пост в "
                 "Telegram, чтобы проверить, что он тот самый.",
    "keep_invalid": "Не удалось распознать ID сообщения из введённого текста.",
    "keep_duplicate": "Такой ID уже есть в списке.",
    "keep_list_title": "Добавить посты из списка",
    "keep_list_prompt": "Вставьте ID сообщений или ссылки t.me, по одной на "
                        "строку (или через пробел/запятую):",
    "keep_list_found": "Найдено постов/альбомов: {n}. Проверьте список ниже.",
    "keep_list_empty": "Ни одна из вставленных ссылок/ID не найдена.",
    "keep_list_added": "В список сохранения добавлено ID: {n}.",
    "keep_list_dialog_title": "Проверка перед добавлением в список сохранения",
    "keep_list_dialog_hint": "Снимите галочку с того, что не нужно сохранять. "
                            "Двойной клик по строке откроет пост в Telegram, "
                            "чтобы проверить автора/источник. Отмеченные посты "
                            "(и весь альбом, если он есть) добавятся по кнопке OK.",
    "keep_select_all": "Выбрать всё",
    "keep_select_none": "Снять выбор",
    "keep_col_link": "Ссылка",
    "keep_col_text": "Текст поста",
    "keep_col_range": "Диапазон альбома",
    "batch_size": "Размер пачки",
    "cleaner_warning": "⚠️ УДАЛЯЕТ ВСЕ СООБЩЕНИЯ В КАНАЛЕ. НЕОБРАТИМО.",
    "confirm_title": "Подтверждение удаления",
    "confirm_delete_prompt": "Введите DELETE, чтобы подтвердить удаление всех сообщений:",
    "confirm_word": "DELETE",
    "confirm_wrong": "Текст подтверждения не совпал — отменено.",
    "users_extractor_help": "Загружает списки участников двух групп и "
                            "позволяет сравнить их: кто есть только в A, "
                            "только в B, в обеих или хотя бы в одной. "
                            "Двойной клик (или правая кнопка мыши) по "
                            "пользователю — скопировать username или открыть "
                            "его в Telegram.",
    "users_extractor_group_a": "Группа A",
    "users_extractor_group_b": "Группа B",
    "users_extractor_need_groups": "Сначала укажите обе группы — A и B.",
    "users_extractor_algo": "Показать",
    "algo_a_only": "Есть в A, нет в B",
    "algo_b_only": "Есть в B, нет в A",
    "algo_intersection": "Есть в обеих (пересечение)",
    "algo_symmetric_diff": "Есть хотя бы в одной, но не в обеих (симметр. разность)",
    "users_extractor_col_a": "Участники группы A",
    "users_extractor_col_b": "Участники группы B",
    "users_extractor_col_delta": "Результат",
    "users_extractor_col_name": "Имя",
    "users_extractor_col_username": "Username / ID",
    "users_extractor_copy_username": "📋 Скопировать username",
    "users_extractor_done": "Группа A: участников {a}. Группа B: участников {b}.",
    "users_extractor_save_html": "💾 Сохранить в HTML…",
    "users_extractor_saved": "Сохранено в {path}",
    "users_extractor_nothing_to_save": "Пока нечего сохранять — сначала запустите сравнение.",
    "post_replacer_help": "Редактирует конкретные посты в канале: меняет "
                          "картинку и/или текст подписи — своя замена для "
                          "каждого поста. Сначала загрузите список постов, "
                          "при необходимости укажите ID для пропуска, затем "
                          "задайте картинку/текст в каждой строке (или "
                          "заполните все разом и поправьте отдельные строки "
                          "вручную). Пустое поле в строке — оригинал не "
                          "меняется.",
    "post_replacer_channel": "ID канала/группы или @username",
    "post_replacer_posts": "Посты для редактирования (ID, диапазоны вида "
                           "100-110 или ссылки t.me)",
    "post_replacer_posts_placeholder": "например 133730-133750, 133780",
    "post_replacer_skip": "Пропустить эти посты (ID/диапазоны, не трогать)",
    "post_replacer_skip_placeholder": "например 133735, 133790-133792",
    "post_replacer_load": "📋 Загрузить посты",
    "post_replacer_bulk": "Заполнить разом (для всех строк ниже)",
    "post_replacer_apply_all": "Применить ко всем строкам",
    "post_replacer_table": "Замена по каждому посту",
    "post_replacer_col_id": "ID",
    "post_replacer_col_link": "Ссылка",
    "post_replacer_col_image": "Новая картинка",
    "post_replacer_col_text": "Новый текст",
    "post_replacer_keep_original": "(оставить как есть)",
    "post_replacer_no_posts": "Не удалось распознать ни одного ID поста из "
                              "введённого текста.",
    "post_replacer_no_rows": "Сначала загрузите посты, затем задайте картинку "
                             "или текст хотя бы в одной строке.",
    "post_replacer_bad_image": "Файл картинки не найден: {path}",
}

LANGS = {"en": EN, "ru": RU}


class I18n:
    def __init__(self, lang: str = "en") -> None:
        self.lang = lang if lang in LANGS else "en"

    def tr(self, key: str, **kw) -> str:
        text = LANGS[self.lang].get(key) or EN.get(key) or key
        return text.format(**kw) if kw else text
