import json,re,html,secrets
from utils import storage
from pathlib import Path
from functools import lru_cache
from aiogram import Router,types,F
from data.aliases import ALIASES
from data.search_items import SEARCH_ITEMS
router=Router()
ROOT=Path(__file__).resolve().parents[1]
def norm(value):return re.sub(r"[^\w]","",value.casefold())
@lru_cache(maxsize=1)
def records():
    return storage.read("character_info", {"characters": []})["characters"]
def lookup(key):
    key=str(key)
    key=ALIASES.get(key,key)
    candidates={norm(key),norm(SEARCH_ITEMS.get(key,key))}
    matches=[c for c in records() if norm(c["name"]) in candidates or str(c["id"])==key]
    return matches[0] if len(matches)==1 else None

def safe(value):
    value=re.sub(r"</?color(?:=[^>]*)?>","",str(value),flags=re.I).replace("\\n","\n")
    value=re.sub(r"\{/?LINK\b[^{}]*\}","",value,flags=re.I)
    # Escape source HTML; restore only balanced, supported emphasis tags.
    value=html.escape(value)
    for tag in ("b","i","u","s"):
        if value.count(f"&lt;{tag}&gt;")==value.count(f"&lt;/{tag}&gt;"):
            value=value.replace(f"&lt;{tag}&gt;",f"<{tag}>").replace(f"&lt;/{tag}&gt;",f"</{tag}>")
    return value

def save_view(token, state):
    from datetime import datetime, timezone, timedelta
    storage.database()["character_views"].replace_one({"_id": token},
        {"_id": token, "state": state, "expires_at": datetime.now(timezone.utc)+timedelta(days=30)}, upsert=True)

def get_view(token):
    from datetime import datetime, timezone
    doc = storage.database()["character_views"].find_one({"_id": token, "expires_at": {"$gt": datetime.now(timezone.utc)}})
    return doc["state"] if doc else None

def remember(key,original,owner,media=None):
    record=lookup(key)
    if not record:return None
    token=secrets.token_hex(8)
    save_view(token, dict(character=record["id"],original=original,owner=owner,media=media or []))
    return token

def keyboard(token,tab=None):
    if tab is None:return {"inline_keyboard":[[{"text":"More info","callback_data":f"ci|{token}|cons"}]]}
    return {"inline_keyboard":[[
        {"text":"Cons","callback_data":f"ci|{token}|cons",**({"style":"primary"} if tab=="cons" else {})},
        {"text":"Skills","callback_data":f"ci|{token}|skills",**({"style":"primary"} if tab=="skills" else {})}],
        [{"text":"Back","callback_data":f"ci|{token}|back"}]]}

def details(record,tab):
    body=[f"<h2>{safe(record['name'])} · {'Constellations' if tab=='cons' else 'Skills'}</h2>"]
    if tab=="cons":
        entries=[(f"C{i} · {a.get('name','')}",a) for i,a in enumerate(record.get('constellations',[]),1)]
    else:
        entries=[(label,a) for label,a in [("Elemental Skill",record.get('elemental_skill')),("Elemental Burst",record.get('elemental_burst'))] if a]
        entries += [("Passive · "+a.get('name',''),a) for a in record.get('passive_talents',[])]
    for label,a in entries:
        title=label+(" · "+a.get('name','') if label in ("Elemental Skill","Elemental Burst") else "")
        body.append(f"<details><summary>{safe(title)}</summary><p>{safe(a.get('description','Details unavailable.')).replace(chr(10),'<br>')}</p></details>")
    return "".join(body)

@router.callback_query(F.data.startswith("ci|"))
async def change_view(callback:types.CallbackQuery):
    from handlers.media import _raw_api_request
    _,token,tab=callback.data.split("|")
    if tab not in ("cons","skills","back"):return await callback.answer()
    state=get_view(token)
    if not state:return await callback.answer("This view expired. Request the character again.",show_alert=True)
    if state['owner'] and callback.from_user.id!=state['owner']:
        return await callback.answer("This menu belongs to another user.",show_alert=True)
    record=lookup(state['character'])
    if not record:return await callback.answer("Character data unavailable.",show_alert=True)
    body=state['original'] if tab=='back' else details(record,tab)
    payload={"rich_message":{"html":body},"reply_markup":keyboard(token,None if tab=='back' else tab)}
    if tab=="back" and state.get("media"):
        payload["rich_message"]["media"]=state["media"]
    if callback.inline_message_id:payload['inline_message_id']=callback.inline_message_id
    elif callback.message:payload.update(chat_id=callback.message.chat.id,message_id=callback.message.message_id)
    else:return await callback.answer()
    try:
        await _raw_api_request(callback.bot,"editMessageText",payload)
    except Exception as exc:
        if "not modified" not in str(exc).lower():
            return await callback.answer("Could not update this message. Please request the character again.",show_alert=True)
    await callback.answer()


def remember_inline(key, original, owner, images, title):
    record = lookup(key)
    if not record:
        return None
    token = secrets.token_hex(8)
    state = dict(character=record["id"], original=original, owner=owner,
                 images=images, title=title, inline=True)
    save_view(token, state)
    return token


def inline_keyboard(token, images, index=0, detail=False):
    if detail:
        return {"inline_keyboard": [[{"text": "Back", "callback_data": f"ici|{token}|back|{index}"}]]}
    rows = []
    if images:
        total = len(images)
        rows.append([
            {"text": "Previous", "callback_data": f"ici|{token}|back|{(index-1)%total}"},
            {"text": f"{index+1}/{total}", "callback_data": f"ici|{token}|back|{index}"},
            {"text": "Next", "callback_data": f"ici|{token}|back|{(index+1)%total}"},
        ])
    rows.append([{"text": "More info", "callback_data": f"ici|{token}|cons|{index}"}])
    return {"inline_keyboard": rows}


def inline_detail_body(record, token, tab, index):
    buttons = []
    for target, label in (("cons", "Cons"), ("skills", "Skills")):
        style = ' style="primary"' if target == tab else ""
        buttons.append(f'<tg-button type="callback_data"{style} data="ici|{token}|{target}|{index}">{label}</tg-button>')
    return '<tg-button-row>' + "".join(buttons) + '</tg-button-row>' + details(record, tab)


@router.callback_query(F.data.startswith("ici|"))
async def change_inline_info(callback: types.CallbackQuery):
    from handlers.media import _raw_api_request
    try:
        _, token, tab, raw_index = callback.data.split("|")
        index = int(raw_index)
        if tab not in ("cons", "skills", "back"):
            raise ValueError
    except (ValueError, TypeError):
        return await callback.answer("Invalid button.")
    state = get_view(token)
    if not state:
        return await callback.answer("This menu expired. Search for the character again.", show_alert=True)
    if callback.from_user.id != state["owner"]:
        return await callback.answer("Use your own inline search to open this menu.", show_alert=True)
    images = state["images"]
    index = max(0, min(index, len(images)-1)) if images else 0
    if tab == "back":
        text = state["original"] if index == 0 else (
            html.escape(state["title"]) + f'\n\nPreview:<a href="{html.escape(images[index], quote=True)}">&#8203;</a>')
        payload = {"text": text, "parse_mode": "HTML",
                   "reply_markup": inline_keyboard(token, images, index)}
    else:
        record = lookup(state["character"])
        if not record:
            return await callback.answer("Character information unavailable.", show_alert=True)
        payload = {"rich_message": {"html": inline_detail_body(record, token, tab, index)},
                   "reply_markup": inline_keyboard(token, images, index, detail=True)}
    if callback.inline_message_id:
        payload["inline_message_id"] = callback.inline_message_id
    elif callback.message:
        payload.update(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    else:
        return await callback.answer()
    try:
        await _raw_api_request(callback.bot, "editMessageText", payload)
    except Exception as error:
        if "not modified" not in str(error).lower():
            return await callback.answer("Could not update this message. Try again.", show_alert=True)
    await callback.answer()
