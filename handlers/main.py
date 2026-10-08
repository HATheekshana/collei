import asyncio
import logging
from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command
from utils.helper import send_log, resolve_character_media
from handlers.admin import (
    handle_add_artifact_command,
    handle_admin_panel_command,
    handle_ban_command,
    handle_unban_command,
)
from handlers.broadcast_admin import handle_broadcast_command
from handlers.boss_admin import handle_bossimg_command
from handlers.card_guide_admin import handle_addcard_command, handle_addguide_command, handle_delcard_command, handle_delguide_command
from handlers.special_media_admin import (
    handle_addabyss_command,
    handle_addtheatre_command,
    handle_addstygian_command,
    handle_delabyss_command,
    handle_deltheatre_command,
    handle_delstygian_command,
    handle_addnextabyss_command,
    handle_addnexttheatre_command,
    handle_addnextstygian_command,
    handle_delnextabyss_command,
    handle_delnexttheatre_command,
    handle_delnextstygian_command,
)
from handlers.cycle_admin import (
    handle_nabyss_command,
    handle_ntheatre_command,
    handle_nstygian_command,
    handle_pabyss_command,
    handle_ptheatre_command,
    handle_pstygian_command,
)
from handlers.complain import handle_complain_command, handle_answer_command
from utils.bosses import find_boss, load_bosses
from utils.artifacts import find_artifact_info
from utils.helper import find_artifact_files
from utils.cards import load_cards
from utils.guides import load_guides
from handlers.media import send_cached_media_group, send_media_slideshow
from utils.search import find_search_matches, build_search_rich_message, send_search_result, RICH_MESSAGE_AVAILABLE
from utils.calculate import router as calculate_router, send_calculate_prompt
from utils.weapons import find_weapon, load_weapons, send_weapon_result
from utils.banner import get_banner_countdown_text, fetch_banner_data_from_hoyolab, get_banner_icons, get_banner_text, update_banner_data
from utils.endgame import get_endgame_text, ensure_schedule
from utils.special_media import get_media, LABELS
from data.aliases import ALIASES
from data.search_items import SEARCH_ITEMS
from data.config import BOT_USERNAME, ADMIN_IDS, GENSHIN_SYNC_UID, GENSHIN_SYNC_REGION
from utils.broadcast_targets import record_user, record_group
from utils.banned_users import is_banned

router = Router()
router.include_router(calculate_router)

MENU_BUTTON_COMMANDS = {
    "artifacts": "artifacts",
    "character guides": "guides",
    "character cards": "cards",
    "bosses": "bosses",
    "weapons": "weapons",
    "search": "search",
    "help": "help",
    "about": "about",
    "add me to group": "addgroup",
}
MENU_CATEGORY_LABELS = {
    "artifacts": "Choose an artifact set:",
    "guides": "Choose a character guide:",
    "cards": "Choose a character card:",
    "bosses": "Choose a boss:",
    "weapons": "Choose a weapon:",
}
MENU_PAGE_SIZE = 10


def build_main_menu_keyboard(bot_username: str | None) -> types.InlineKeyboardMarkup:
    return build_inline_main_menu_keyboard(bot_username)


def build_inline_main_menu_keyboard(bot_username: str | None) -> types.InlineKeyboardMarkup:
    rows = [
        [
            types.InlineKeyboardButton(text="Artifacts", callback_data="menu|artifacts"),
            types.InlineKeyboardButton(text="Character guides", callback_data="menu|guides"),
        ],
        [
            types.InlineKeyboardButton(text="Character cards", callback_data="menu|cards"),
            types.InlineKeyboardButton(text="Bosses", callback_data="menu|bosses"),
        ],
        [
            types.InlineKeyboardButton(text="Weapons", callback_data="menu|weapons"),
            types.InlineKeyboardButton(
                text="Search",
                callback_data="menu|help_search",
            ),
        ],
        [types.InlineKeyboardButton(text="Help", callback_data="menu|help")],
        [types.InlineKeyboardButton(text="About", callback_data="menu|about")],
    ]
    if bot_username:
        rows.append([
            types.InlineKeyboardButton(
                text="Add me to group",
                url=f"https://t.me/{bot_username.lstrip('@')}?startgroup=true",
            )
        ])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)



HELP_TOPICS = {
    "characters": ("Characters & builds", "Use /cards or /guides to browse, or send /collei or /ganyu.\n\nBelow a character card, tap More info to read Skills and Cons. Tap a heading to expand it, and Back to return to the card."),
    "equipment": ("Weapons & artifacts", "Use inline search or /search followed by a weapon or artifact name. Character commands always open character cards.\n\nWeapon details include base stats and R1–R5 refinement buttons. Artifact details include set effects when available."),
    "search": ("Search & bosses", "Use /search name to find characters, weapons, artifacts, or bosses. Use /bosses to browse bosses.\n\n/allcommands lists available search commands. You can also type the bot's @username followed by a name in any chat to search inline."),
    "events": ("Banners & endgame", "Use /current for current banners or /next for upcoming banners and countdowns. You can add a character name after either command.\n\nUse the Abyss, Theatre, and Stygian buttons below those messages to view the available current or next event cards."),
    "support": ("Feedback & groups", "Use /complain your message to contact support. Reply to another message with /complain to include it.\n\nUse /addgroup to invite the bot. Group administrators can use /removegroup to remove it. Open About for the support group, channel, and owner."),
}


def help_view(user_id, topic=None):
    title, body = HELP_TOPICS.get(topic, ("Collei Bot Help", "Choose a topic below for commands and instructions."))
    rows=[]
    topics=list(HELP_TOPICS.items())
    for index in range(0,len(topics),2):
        rows.append([types.InlineKeyboardButton(text=value[0],callback_data="menu|help_"+key,**({"style":"primary"} if topic==key else {})) for key,value in topics[index:index+2]])
    if user_id in ADMIN_IDS:
        rows.append([types.InlineKeyboardButton(text="Admin help",callback_data="admin_help")])
    rows.append([types.InlineKeyboardButton(text="About",callback_data="menu|about"),types.InlineKeyboardButton(text="Main menu",callback_data="menu|back")])
    return title+"\n\n"+body, types.InlineKeyboardMarkup(inline_keyboard=rows)


def about_view():
    return ("Collei Bot\n\nGenshin Impact character guides, cards, skills, constellations, weapons, artifacts, bosses, banners and endgame information.\n\nOwner: @Renxzero", types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Support group",url="https://t.me/+PIojr4QOf3o2MzE1"),types.InlineKeyboardButton(text="Channel",url="https://t.me/renxzero_channel")],
        [types.InlineKeyboardButton(text="Owner · @Renxzero",url="https://t.me/Renxzero")],
        [types.InlineKeyboardButton(text="Help",callback_data="menu|help"),types.InlineKeyboardButton(text="Main menu",callback_data="menu|back")]
    ]))


async def edit_menu(message, text, markup):
    try:
        if message.photo:
            await message.edit_caption(caption=text,reply_markup=markup,parse_mode=None)
        else:
            await message.edit_text(text,reply_markup=markup,parse_mode=None)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


def _menu_items(category: str) -> list[tuple[str, str]]:
    if category == "artifacts":
        items = [
            (key, display)
            for key, display in SEARCH_ITEMS.items()
            if find_artifact_info(key) or find_artifact_files(key)
        ]
    elif category == "bosses":
        boss_names = {boss.get("name", "") for boss in load_bosses()}
        items = [
            (key, display) for key, display in SEARCH_ITEMS.items() if display in boss_names
        ]
    elif category == "weapons":
        items = [(key, entry.get("name", key)) for key, entry in load_weapons().items()]
    else:
        source = load_guides() if category == "guides" else load_cards()
        keys = {entry.get("character_key") for entry in source if entry.get("character_key")}
        items = [(key, SEARCH_ITEMS.get(key, key.title())) for key in sorted(keys)]

    return sorted(items, key=lambda item: item[1].lower())


COMMAND_SECTIONS = {
    "home": "Overview", "general": "Bot commands", "all": "All search commands",
    "guides": "Character guides", "cards": "Character cards",
    "weapons": "Weapons", "artifacts": "Artifacts", "bosses": "Bosses",
}


def allcommands_view(owner, section="home", page=0):
    section = section if section in COMMAND_SECTIONS else "home"
    items = []
    if section == "general":
        items = [
            ("start", "Main menu"), ("help", "Usage and support"),
            ("allcommands", "Browse all commands"), ("search", "Search by name"), ("calculate", "Pick a character by letter"),
            ("cards", "Character cards"), ("guides", "Character guides"),
            ("weapons", "Weapon details"), ("artifacts", "Artifact sets"),
            ("bosses", "Boss information"), ("current", "Current banners and endgame"),
            ("next", "Upcoming banners and endgame"), ("about", "Owner and community"),
            ("complain", "Send feedback"), ("addgroup", "Invite Collei"),
            ("removegroup", "Remove Collei (group admins)"),
        ]
    elif section == "all":
        from utils.search import search_catalog
        items = sorted((k[2:], v) for k,v in search_catalog().items() if k.startswith(("c:", "b:")))
    elif section != "home":
        items = _menu_items(section)
    pages = max(1, (len(items) + 11) // 12)
    page = max(0, min(page, pages - 1))
    if section == "home":
        text = ("🌿 Collei · Command directory\n\n"
                "Choose a category below. Use Previous and Next to browse.\n"
                "Tap a /command in the list to use it, or type /search followed by a name.")
    else:
        lines = [f"/search {label}" if section in {"weapons", "artifacts"} else f"/{key} — {str(label)[:120]}" for key, label in items[page*12:(page+1)*12]]
        text = (f"🌿 {COMMAND_SECTIONS[section]}\n"
                f"Page {page+1}/{pages} · {len(items)} commands\n\n" +
                ("\n".join(lines) or "No commands available in this category yet."))
    def button(label, target, number=0, selected=False):
        return types.InlineKeyboardButton(
            text=label, callback_data=f"cmdnav|{owner}|{target}|{number}",
            **({"style": "primary"} if selected else {}))
    rows = []
    if pages > 1:
        row = []
        if page > 0: row.append(button("‹ Previous", section, page-1))
        if page+1 < pages: row.append(button("Next ›", section, page+1))
        rows.append(row)
    sections = [(k,v) for k,v in COMMAND_SECTIONS.items() if k != "home"]
    for i in range(0,len(sections),2):
        rows.append([button(label,key,selected=key==section) for key,label in sections[i:i+2]])
    if section != "home":
        rows.append([button("‹ Overview", "home")])
    return text, types.InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda c: c.data and c.data.startswith("cmdnav|"))
async def handle_command_navigation(callback: types.CallbackQuery):
    try:
        _, owner, section, page = callback.data.split("|")
        owner, page = int(owner), int(page)
        if section not in COMMAND_SECTIONS:
            raise ValueError
    except (ValueError, TypeError):
        await callback.answer("Invalid menu button.")
        return
    if callback.from_user.id != owner:
        await callback.answer("Open /allcommands to use your own menu.", show_alert=True)
        return
    if not callback.message:
        await callback.answer("Open /allcommands again.")
        return
    await callback.answer()
    text, markup = allcommands_view(owner, section, page)
    await edit_menu(callback.message, text, markup)


def build_category_keyboard(category: str, user_id: int, page: int = 0) -> types.InlineKeyboardMarkup:
    items = _menu_items(category)
    page_count = max(1, (len(items) + MENU_PAGE_SIZE - 1) // MENU_PAGE_SIZE)
    page = max(0, min(page, page_count - 1))
    page_items = items[page * MENU_PAGE_SIZE:(page + 1) * MENU_PAGE_SIZE]

    keyboard = [
        [
            types.InlineKeyboardButton(
                text=display[:32], callback_data=f"search|{user_id}|{ {'weapons': 'w', 'artifacts': 'a', 'bosses': 'b'}.get(category, 'c')}:{key}"
            )
            for key, display in page_items[index:index + 2]
        ]
        for index in range(0, len(page_items), 2)
    ]
    navigation = []
    if page > 0:
        navigation.append(types.InlineKeyboardButton(
            text="Previous page", callback_data=f"menu_page|{category}|{page - 1}|{user_id}"
        ))
    if page < page_count - 1:
        navigation.append(types.InlineKeyboardButton(
            text="Next page", callback_data=f"menu_page|{category}|{page + 1}|{user_id}"
        ))
    if navigation:
        keyboard.append(navigation)
    keyboard.append([types.InlineKeyboardButton(text="Main menu", callback_data="menu|back")])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


async def _send_character_results(message: types.Message, character: str):
    """Resolve media (imgBB URL preferred, Telegram file_id fallback) and send as rich slideshow."""
    logging.info(f"_send_character_results called with character: {character}")
    media_items = await resolve_character_media(message.bot, character)

    logging.info(f"Got {len(media_items)} media items: {media_items[:2] if media_items else 'None'}")
    if not media_items:
        await message.reply(f"No files found for {character.title()}.")
        return

    await send_media_slideshow(message, media_items, caption=character.title(), character_key=character)


async def _reply_or_answer(message: types.Message, text: str):
    """message.reply() fails with 'message to be replied not found' if the
    original command message has already vanished (deleted, expired, etc.)
    by the time we respond. Fall back to a plain send in that case."""
    try:
        await message.reply(text, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message to be replied not found" in str(e):
            await message.answer(text, parse_mode="HTML")
        else:
            raise


async def _reply_or_answer_with_markup(
    message: types.Message, text: str, reply_markup: types.InlineKeyboardMarkup | None
):
    """Same as _reply_or_answer, but also attaches an inline keyboard."""
    try:
        await message.reply(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message to be replied not found" in str(e):
            await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            raise


async def _call_with_flood_retry(action, max_retries: int = 1):
    """Run an aiogram send call, retrying (once, by default) if Telegram's
    flood control (TelegramRetryAfter / 429) kicks in on busy chats."""
    for attempt in range(max_retries + 1):
        try:
            return await action()
        except TelegramRetryAfter as e:
            if attempt >= max_retries:
                raise
            wait_for = getattr(e, "retry_after", 5) + 1
            logging.warning(f"Flood control hit, waiting {wait_for}s before retry")
            await asyncio.sleep(wait_for)


async def _send_banner_rich(message: types.Message, text: str, icons: list[str]):
    """
    Send banner info as native Telegram photo(s) with an HTML caption.
    (send_media_slideshow's <figcaption> path HTML-escapes the caption, which
    would turn our <b>/<code> tags into literal text, so we build a plain
    Telegram media group here instead — that's what actually renders bold text
    and images together.)
    """
    # Telegram allows up to 10 items in a media group, but capping lower
    # keeps requests small and far less likely to trip flood control in busy chats.
    icons = [url for url in icons if url][:6]
    if not icons:
        await _reply_or_answer(message, text)
        return

    if len(icons) == 1:
        try:
            await _call_with_flood_retry(
                lambda: message.reply_photo(icons[0], caption=text, parse_mode="HTML")
            )
            return
        except TelegramBadRequest as e:
            if "message to be replied not found" in str(e):
                try:
                    await _call_with_flood_retry(
                        lambda: message.answer_photo(icons[0], caption=text, parse_mode="HTML")
                    )
                    return
                except Exception:
                    logging.exception("Failed to send single banner photo without reply ref")
            else:
                logging.exception("Failed to send single banner photo")
        except Exception:
            logging.exception("Failed to send single banner photo")
        await _reply_or_answer(message, text)
        return

    media = [
        types.InputMediaPhoto(media=url, caption=text, parse_mode="HTML") if idx == 0
        else types.InputMediaPhoto(media=url)
        for idx, url in enumerate(icons)
    ]
    try:
        await _call_with_flood_retry(
            lambda: message.answer_media_group(
                media,
                reply_parameters=types.ReplyParameters(message_id=message.message_id),
            )
        )
        return
    except TelegramBadRequest as e:
        if "message to be replied not found" in str(e):
            try:
                await _call_with_flood_retry(lambda: message.answer_media_group(media))
                return
            except Exception:
                logging.exception("Failed to send banner media group without reply ref")
        else:
            logging.exception("Failed to send banner media group")
    except Exception:
        logging.exception("Failed to send banner media group")
    await _reply_or_answer(message, text)


def build_special_media_keyboard(phase: str) -> types.InlineKeyboardMarkup:
    """
    Buttons shown under /next and /current.
    `phase` is "current" or "next" — each has its own independent image set.
    Uses the real Bot API 9.4 button `style` field: "danger" = red, "success" = green.
    Stygian is left with no style (default/no colour).
    """
    return types.InlineKeyboardMarkup(
        inline_keyboard=[[
            types.InlineKeyboardButton(text="Abyss", callback_data=f"specialmedia|{phase}|abyss", style="danger"),
            types.InlineKeyboardButton(text="Theatre", callback_data=f"specialmedia|{phase}|theatre", style="success"),
            types.InlineKeyboardButton(text="Stygian", callback_data=f"specialmedia|{phase}|stygian"),
        ]]
    )


async def _send_special_media_images(
    bot,
    chat_id: int,
    reply_to_message_id: int | None,
    file_ids: list[str],
    caption: str,
):
    """Send one or more images (by Telegram file_id) as a reply to reply_to_message_id."""
    if not file_ids:
        return

    reply_parameters = (
        types.ReplyParameters(message_id=reply_to_message_id) if reply_to_message_id else None
    )

    if len(file_ids) == 1:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_ids[0],
                caption=caption,
                parse_mode="HTML",
                reply_parameters=reply_parameters,
            )
        except TelegramBadRequest as e:
            if reply_parameters and "message to be replied not found" in str(e):
                await bot.send_photo(chat_id=chat_id, photo=file_ids[0], caption=caption, parse_mode="HTML")
            else:
                raise
        return

    CHUNK = 10
    for i in range(0, len(file_ids), CHUNK):
        chunk = file_ids[i:i + CHUNK]
        media = [
            types.InputMediaPhoto(media=fid, caption=caption, parse_mode="HTML") if idx == 0 and i == 0
            else types.InputMediaPhoto(media=fid)
            for idx, fid in enumerate(chunk)
        ]
        try:
            await bot.send_media_group(chat_id=chat_id, media=media, reply_parameters=reply_parameters)
        except TelegramBadRequest as e:
            if reply_parameters and "message to be replied not found" in str(e):
                await bot.send_media_group(chat_id=chat_id, media=media)
            else:
                raise


@router.message()
async def handle_message(message: types.Message):
    if not message.text:
        return

    message_text = message.text.strip()
    if message_text.startswith("/"):
        command = message_text.split()[0][1:].split('@')[0].lower()
    else:
        # Plain text such as "about" or "help" is not a command; only /commands are handled.
        return
    if not command:
        return

    logging.info(f"Command received: {command}")
    user = message.from_user

    SPECIAL_COMMANDS = {
        "start", "help", "search", "calculate", "allcommands", "complain",
        "artifacts", "guides", "cards", "bosses", "weapons", "about", "addgroup", "removegroup",
    }
    ADMIN_COMMANDS = {
        "admin",
        "addarti", "next", "current", "bupdate", "bossimg", "addcard", "addguide", "delcard", "delguide", "bsync",
        "addabyss", "addtheatre", "addstygian", "delabyss", "deltheatre", "delstygian",
        "addnextabyss", "addnexttheatre", "addnextstygian", "delnextabyss", "delnexttheatre", "delnextstygian",
        "nabyss", "ntheatre", "nstygian", "pabyss", "ptheatre", "pstygian",
        "broadcast", "tbroadcast", "rbroadcast", "trbroadcast", "answer",
        "ban", "unban",
    }

    should_ignore = command not in SEARCH_ITEMS and command not in SPECIAL_COMMANDS and command not in ADMIN_COMMANDS and command not in ALIASES
    logging.info(f"Command '{command}' - should_ignore={should_ignore}")

    if should_ignore:
        logging.info(f"Ignoring command: {command}")
        return

    if user and user.id not in ADMIN_IDS and is_banned(user.id):
        return

    # Track who/where the bot is being used, so /broadcast can reach them
    # later. Private chats save the user's ID; groups/supergroups save the
    # chat ID. Each check-and-save is a no-op if already known.
    try:
        if message.chat.type == "private" and user:
            record_user(user.id, name=user.full_name or "", username=user.username or "")
        elif message.chat.type in ("group", "supergroup"):
            record_group(message.chat.id, title=message.chat.title or "")
    except Exception:
        logging.exception("Failed to record broadcast target")


    try:
        username = f"@{user.username}" if user.username else "None"
        await send_log(
            message.bot,
            f"Command Used\n\n"
            f"User: {user.full_name}\n"
            f"ID: {user.id}\n"
            f"Username: {username}\n"
            f"Command: /{command}"
        )
    except Exception as e:
        logging.exception("Error in send_log: %s", e)

    if command == "start":
        bot_username = BOT_USERNAME
        if bot_username:
            bot_username = bot_username.lstrip("@")
        if not bot_username:
            try:
                me = await message.bot.get_me()
                bot_username = me.username
            except Exception:
                bot_username = None

        group_link = None
        if bot_username:
            group_link = f"https://t.me/{bot_username}?startgroup=true"

        inline_hint = ""
        if bot_username:
            inline_hint = f"\n\nYou can also search inline in any chat by typing @{bot_username} and your query."

        await message.reply(
            "Welcome to Collei Bot!\n\n"
            "Send a character command like /ganyu or /collei to get guides and cards.\n"
            "Use /search [name] to look up characters, artifacts, or bosses.\n"
            "Use /next or /current for banner countdowns and /allcommands to see every available search command.\n"
            "Use /help for full usage info and admin support." + inline_hint,
            reply_markup=build_main_menu_keyboard(bot_username),
        )
        return

    if command == "help":
        text, keyboard = help_view(message.from_user.id)
        await message.reply(text, reply_markup=keyboard, parse_mode=None)
        return

    if command in {"weapons", "artifacts"}:
        await message.reply("Use /search followed by a name, or search inline with the bot username.")
        return

    if command in {"guides", "cards", "bosses"}:
        await message.reply(
            MENU_CATEGORY_LABELS[command],
            reply_markup=build_category_keyboard(command, message.from_user.id),
        )
        return

    if command == "about":
        text, keyboard = about_view()
        await message.reply(text, reply_markup=keyboard, parse_mode=None)
        return

    if command == "addgroup":
        bot_username = BOT_USERNAME.lstrip("@") if BOT_USERNAME else None
        if not bot_username:
            try:
                bot_username = (await message.bot.get_me()).username
            except Exception:
                bot_username = None
        if not bot_username:
            await message.reply("The group invite link is unavailable right now.")
            return
        await message.reply(f"Add Collei Bot to your group: https://t.me/{bot_username}?startgroup=true")
        return

    if command == "removegroup":
        if message.chat.type not in {"group", "supergroup"}:
            await message.reply("This command can only be used inside a group.")
            return

        if not user:
            return

        if user.id not in ADMIN_IDS:
            try:
                member = await message.bot.get_chat_member(message.chat.id, user.id)
            except Exception:
                logging.exception("Failed to verify group administrator for /removegroup")
                await message.reply("I could not verify your group permissions.")
                return

            if member.status not in {"creator", "administrator"}:
                await message.reply("Only group administrators or the bot owner can remove me.")
                return

        await message.reply("Leaving this group now. Goodbye!")
        await message.bot.leave_chat(message.chat.id)
        return

    if command == "admin":
        await handle_admin_panel_command(message)
        return

    if command == "addarti":
        await handle_add_artifact_command(message)
        return

    if command in ("broadcast", "tbroadcast", "rbroadcast", "trbroadcast"):
        await handle_broadcast_command(message)
        return

    if command == "ban":
        await handle_ban_command(message)
        return

    if command == "unban":
        await handle_unban_command(message)
        return

    if command == "complain":
        await handle_complain_command(message)
        return

    if command == "answer":
        await handle_answer_command(message)
        return

    if command == "bossimg":
        await handle_bossimg_command(message)
        return

    if command == "addcard":
        await handle_addcard_command(message)
        return

    if command == "addguide":
        await handle_addguide_command(message)
        return

    if command == "delcard":
        await handle_delcard_command(message)
        return

    if command == "delguide":
        await handle_delguide_command(message)
        return

    if command == "addabyss":
        await handle_addabyss_command(message)
        return

    if command == "addtheatre":
        await handle_addtheatre_command(message)
        return

    if command == "addstygian":
        await handle_addstygian_command(message)
        return

    if command == "delabyss":
        await handle_delabyss_command(message)
        return

    if command == "deltheatre":
        await handle_deltheatre_command(message)
        return

    if command == "delstygian":
        await handle_delstygian_command(message)
        return

    if command == "addnextabyss":
        await handle_addnextabyss_command(message)
        return

    if command == "addnexttheatre":
        await handle_addnexttheatre_command(message)
        return

    if command == "addnextstygian":
        await handle_addnextstygian_command(message)
        return

    if command == "delnextabyss":
        await handle_delnextabyss_command(message)
        return

    if command == "delnexttheatre":
        await handle_delnexttheatre_command(message)
        return

    if command == "delnextstygian":
        await handle_delnextstygian_command(message)
        return

    if command == "nabyss":
        await handle_nabyss_command(message)
        return

    if command == "ntheatre":
        await handle_ntheatre_command(message)
        return

    if command == "nstygian":
        await handle_nstygian_command(message)
        return

    if command == "pabyss":
        await handle_pabyss_command(message)
        return

    if command == "ptheatre":
        await handle_ptheatre_command(message)
        return

    if command == "pstygian":
        await handle_pstygian_command(message)
        return

    if command == "allcommands":
        text, markup = allcommands_view(message.from_user.id)
        await message.reply(text, reply_markup=markup, parse_mode=None)
        return

    if command == "next":
        await ensure_schedule()
        query = message.text.partition(" ")[2].strip()
        if query:
            text = get_banner_countdown_text(query, mode="next") + "\n\n" + get_endgame_text(mode="next")
            await message.reply(text, parse_mode="HTML")
        else:
            text = get_banner_text(mode="next") + "\n\n" + get_endgame_text(mode="next")
            await _reply_or_answer_with_markup(message, text, build_special_media_keyboard("next"))
        return

    if command == "current":
        await ensure_schedule()
        query = message.text.partition(" ")[2].strip()
        if query:
            text = get_banner_countdown_text(query, mode="current") + "\n\n" + get_endgame_text(mode="current")
            await message.reply(text, parse_mode="HTML")
        else:
            text = get_banner_text(mode="current") + "\n\n" + get_endgame_text(mode="current")
            await _reply_or_answer_with_markup(message, text, build_special_media_keyboard("current"))
        return

    if command == "bupdate":
        parts = message.text.split(maxsplit=3)
        if len(parts) != 3:
            await message.reply("Usage: /bupdate [nextchar1] [nextchar2]")
            return
        if not message.from_user or message.from_user.id not in ADMIN_IDS:
            await message.reply("You are not authorized to use this command.")
            return
        next_characters = [parts[1], parts[2]]
        update_banner_data(next_characters=next_characters)
        await message.reply("Next banner characters updated.", parse_mode="HTML")
        return

    if command == "bsync":
        if not message.from_user or message.from_user.id not in ADMIN_IDS:
            await _reply_or_answer(message, "You are not authorized to use this command.")
            return

        if not GENSHIN_SYNC_UID:
            await _reply_or_answer(
                message,
                "❌ No Genshin UID configured for syncing.\n\n"
                "Set the <code>GENSHIN_SYNC_UID</code> environment variable to a real "
                "in-game UID on the server you want banner data pulled from "
                "(optionally set <code>GENSHIN_SYNC_REGION</code> too, default "
                "\"asia\"), then restart the bot and run /bsync again.",
            )
            return

        await _reply_or_answer(message, "🔄 Syncing banner data from the Genshin calendar...")
        result = await fetch_banner_data_from_hoyolab(GENSHIN_SYNC_UID, GENSHIN_SYNC_REGION)

        if result:
            current_chars = result.get("current_characters", [])
            next_chars = result.get("next_characters", [])
            current_icons = result.get("current_icons", [])
            next_icons = result.get("next_icons", [])

            current_label = ", ".join(current_chars) if current_chars else "—"
            next_label = ", ".join(next_chars) if next_chars else "—"
            text = (
                "✅ <b>Banner data synced successfully!</b>\n\n"
                f"<b>Current:</b> {current_label}\n"
                f"<b>Next:</b> {next_label}"
            )
            await _send_banner_rich(message, text, current_icons + next_icons)
        else:
            await _reply_or_answer(
                message,
                "❌ Failed to sync banner data.\n\n"
                "<b>Troubleshooting:</b>\n"
                "1. Double check <code>GENSHIN_SYNC_UID</code> is a real, valid UID on the "
                f"<code>{GENSHIN_SYNC_REGION}</code> server\n"
                "2. Make sure the bot's host can reach <code>sg-act-public-api.hoyolab.com</code> (check network/egress settings)\n"
                "3. The calendar API may be temporarily down — check the bot logs for details\n"
                "4. Use /bsync again after resolving the issue.",
            )
        return

    if command == "calculate":
        await send_calculate_prompt(message, user.id)
        return

    if command == "search":
        query = message.text.partition(" ")[2].strip()
        if not query:
            await message.reply("Usage: /search [name]\nExample: /search collei")
            return

        matches = find_search_matches(query)
        if not matches:
            await message.reply("No search results found. Try another keyword or /allcommands.")
            return

        if len(matches) == 1:
            await send_search_result(message, matches[0])
            return

        if RICH_MESSAGE_AVAILABLE and hasattr(message, "reply_rich"):
            rich_message = build_search_rich_message(query, matches, message.from_user.id)
            await message.reply_rich(rich_message=rich_message)
        else:
            from utils.search import search_catalog
            labels = search_catalog()
            rows = []
            for kind, title in (("c", "Characters"), ("w", "Weapons"), ("a", "Artifacts"), ("b", "Bosses")):
                for key in matches:
                    if key.startswith(kind+":"):
                        rows.append([types.InlineKeyboardButton(text=f"{title} · {labels[key]}", callback_data=f"search|{message.from_user.id}|{key}")])
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=rows)
            await message.reply(
                f"Search results for <b>{query}</b>:",
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        return

    from utils.search import search_catalog
    catalog = search_catalog()
    character = ALIASES.get(command, command)
    if "c:" + character not in catalog and "b:" + command in catalog:
        await send_search_result(message, "b:" + command)
        return
    if "c:" + character not in catalog and any(k in catalog for k in ("w:" + command, "a:" + command)):
        await message.reply("Use /search followed by the weapon or artifact name, or use inline search.")
        return
    # --- Character cards + guides ---
    await _send_character_results(message, character)


@router.callback_query(lambda c: c.data and c.data.startswith("menu_page|"))
async def handle_menu_page_button(callback: types.CallbackQuery):
    parts = callback.data.split("|", 3)
    if len(parts) != 4:
        return

    category, page_text, user_id_text = parts[1:]
    try:
        page = int(page_text)
        user_id = int(user_id_text)
    except ValueError:
        return

    if callback.from_user.id != user_id:
        await callback.answer("This menu is not for you.", show_alert=True)
        return

    if category not in MENU_CATEGORY_LABELS:
        return

    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            MENU_CATEGORY_LABELS[category],
            reply_markup=build_category_keyboard(category, user_id, page),
        )


@router.callback_query(lambda c: c.data and c.data.startswith("menu|"))
async def handle_main_menu_button(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

    if not callback.message:
        return

    category = callback.data.split("|", 1)[1]
    if category == "back":
        await edit_menu(callback.message, "Welcome to Collei Bot!\n\nChoose a section below. Open Help for commands and instructions.", build_main_menu_keyboard(BOT_USERNAME))
    elif category in MENU_CATEGORY_LABELS:
        await edit_menu(callback.message, MENU_CATEGORY_LABELS[category], build_category_keyboard(category, callback.from_user.id))
    elif category == "help" or category.startswith("help_"):
        text, keyboard = help_view(callback.from_user.id, category[5:] if category.startswith("help_") else None)
        await edit_menu(callback.message, text, keyboard)
    elif category == "about":
        text, keyboard = about_view()
        await edit_menu(callback.message, text, keyboard)


@router.callback_query(lambda c: c.data and c.data.startswith("search|"))
async def handle_search_button(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

    parts = callback.data.split("|", 2)
    if len(parts) != 3:
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        return

    if callback.from_user.id != user_id:
        try:
            await callback.answer("This button is not for you.", show_alert=True)
        except Exception:
            pass
        return

    key = parts[2]
    if not callback.message:
        return

    await send_search_result(callback.message, key)

    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith("weapon|"))
async def handle_weapon_refinement_button(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

    parts = callback.data.split("|", 3)
    if len(parts) != 4:
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        return

    if callback.from_user.id != user_id:
        try:
            await callback.answer("This button is not for you.", show_alert=True)
        except Exception:
            pass
        return

    key, refinement = parts[2], parts[3]
    if not callback.message:
        return

    # Rich messages can't be edited in place yet, so — same pattern as
    # handle_search_button above — send the updated card as a fresh reply
    # and remove the old one.
    await send_weapon_result(callback.message, key, refinement)

    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith("specialmedia|"))
async def handle_special_media_button(callback: types.CallbackQuery):
    if not callback.message:
        try:
            await callback.answer()
        except Exception:
            pass
        return

    # The button prompt message is a reply to the user's original /next or
    # /current command — that's who the images should be sent back to, and
    # the only person allowed to press these buttons.
    reply_target = callback.message.reply_to_message

    if reply_target and reply_target.from_user and callback.from_user.id != reply_target.from_user.id:
        try:
            await callback.answer("Only the person who used /next or /current can use these buttons.", show_alert=True)
        except Exception:
            pass
        return

    try:
        await callback.answer()
    except Exception:
        pass

    parts = callback.data.split("|")
    if len(parts) != 3:
        return
    _, phase, category = parts
    phase_label = "Next" if phase == "next" else "Current"
    label = LABELS.get(category, category.title())
    full_label = f"{phase_label} {label}"
    media = get_media(phase, category)

    if not media:
        text = f"No images added for {full_label} yet."
        try:
            if reply_target:
                await reply_target.reply(text)
            else:
                await callback.message.answer(text)
        except Exception:
            logging.exception("Failed to notify empty special media category")
        return

    file_ids = [m["file_id"] for m in media if m.get("file_id")]

    # Delete the original button message before sending the images.
    try:
        await callback.message.delete()
    except Exception:
        logging.exception("Failed to delete special media prompt message")

    try:
        await _send_special_media_images(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            reply_to_message_id=reply_target.message_id if reply_target else None,
            file_ids=file_ids,
            caption=f"<b>{full_label}</b>",
        )
    except Exception:
        logging.exception("Failed to send special media images for %s %s", phase, category)


@router.callback_query(lambda c: c.data == "admin_help")
async def handle_admin_help_button(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

    if callback.from_user.id not in ADMIN_IDS:
        try:
            await callback.answer("Admin help is only available to bot admins.", show_alert=True)
        except Exception:
            pass
        return

    admin_text = (
        "Admin commands:\n\n"
        "• /addarti - Add artifact info\n"
        "• /bossimg - Set boss image by replying to a photo\n"
        "• /addcard - Add a character card\n"
        "• /addguide - Add a guide\n"
        "• /delcard - Delete a card\n"
        "• /delguide - Delete a guide\n"
        "• /bupdate [nextchar1] [nextchar2] - Update next banner data\n"
        "• /bsync - Sync banner data from Hoyolab\n"
        "• /tbroadcast - Test broadcast in log group\n"
        "• /rbroadcast - Rich broadcast to everyone\n"
        "• /trbroadcast - Test rich broadcast in log group\n"
        "• /update - Retrieve and save the latest weapon dataset\n\n"
        "• /addabyss, /addtheatre, /addstygian - Reply to a photo to add a CURRENT-phase record image (repeatable)\n"
        "• /delabyss, /deltheatre, /delstygian - Delete ALL current-phase images for that category\n"
        "• /addnextabyss, /addnexttheatre, /addnextstygian - Reply to a photo to add a NEXT-phase record image (repeatable)\n"
        "• /delnextabyss, /delnexttheatre, /delnextstygian - Delete ALL next-phase images for that category\n\n"
        "• /nabyss, /ntheatre, /nstygian - Advance that category's cycle (auto-generates the new next card)\n"
        "• /pabyss, /ptheatre, /pstygian - Retreat that category's cycle by one (undo an advance / preview a past cycle)\n\n"
        "• /ban <user_id> - Ban a user (or reply to their message with /ban)\n"
        "• /unban <user_id> - Remove a user's ban (or reply to their message with /unban)\n\n"
        "• /answer [text] - Reply (in the support chat, to the complaint message) to send an answer back to the user who complained"
    )

    if callback.message:
        try:
            if callback.message.photo:
                await callback.answer("Open /help again to view the updated text menu.", show_alert=True)
                return
            await edit_menu(callback.message, admin_text, types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="Back to Help",callback_data="menu|help")]]))
        except Exception:
            logging.exception("Failed to send admin help text")