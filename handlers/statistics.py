import asyncio
import logging
import re
from html import escape
from aiogram import BaseMiddleware,Router,types
from aiogram.filters import Command
from data.config import ADMIN_IDS,LOG_CHAT_ID
from utils import usage_stats
from utils import broadcast_targets
router=Router()

class UsageMiddleware(BaseMiddleware):
    async def __call__(self,handler,event,data):
        bot=data['bot']
        message=event.message
        inline=event.inline_query
        member=event.my_chat_member
        callback=event.callback_query
        user=(inline.from_user if inline else member.from_user if member else callback.from_user if callback else message.from_user if message else None)
        if user and user.is_bot:user=None
        chat=member.chat if member else message.chat if message else None
        group=chat.id if member and chat and chat.type in ('group','supergroup') else None
        active=True
        if member:
            value=member.new_chat_member
            active=value.status in ('member','administrator','creator') or (value.status=='restricted' and value.is_member)
        command=False
        if message and user:
            text=message.text or message.caption or ''
            entities=message.entities or message.caption_entities or []
            if any(e.type=='bot_command' and e.offset==0 for e in entities):
                token=text.split()[0]
                if '@' not in token:command=True
                else:command=token.split('@',1)[1].casefold()==(await bot.me()).username.casefold()
        private_start = bool(message and user and message.chat.type=='private' and command
                             and text.split()[0].split('@')[0].casefold()=='/start')
        try:
            # Keep aggregate usage, but notification eligibility comes from the
            # broadcast audience, not people speaking in groups or using inline mode.
            await asyncio.to_thread(usage_stats.record,event.update_id,
                command=command,inline=inline is not None)
            notices=[]
            if private_start and broadcast_targets.record_user(user.id,user.full_name,user.username or ''):
                notices.append('user')
            if group:
                old=member.old_chat_member
                was_active=old.status in ('member','administrator','creator') or (old.status=='restricted' and old.is_member)
                if active:
                    added=broadcast_targets.record_group(group,chat.title or '')
                    if not was_active and added:notices.append('group')
                else:
                    broadcast_targets.remove_group(group)
            if message and getattr(message,'migrate_to_chat_id',None):
                broadcast_targets.remove_group(message.chat.id)
                broadcast_targets.record_group(message.migrate_to_chat_id,message.chat.title or '')
            if LOG_CHAT_ID:
                for kind in notices:
                    if kind=='user':
                        body=f"👤 <b>New user</b>\n{escape(user.full_name)}\nID: <code>{user.id}</code>"
                        if user.username:body+=f"\n@{escape(user.username)}"
                    else:
                        body=f"👥 <b>New group / bot joined</b>\n{escape(chat.title or 'Group')}\nID: <code>{chat.id}</code>"
                    try:await bot.send_message(LOG_CHAT_ID,body,parse_mode='HTML')
                    except Exception:logging.warning('Could not send usage notification to log chat')
        except Exception:logging.exception('Usage tracking failed')
        return await handler(event,data)

@router.my_chat_member()
async def membership(event:types.ChatMemberUpdated):
    # Membership tracking is done once by the update middleware.
    pass

@router.message(Command('stat'))
async def stat(message:types.Message):
    if not message.from_user or message.from_user.id not in ADMIN_IDS:
        return await message.reply('Only bot admins can use /stat.')
    values=await asyncio.to_thread(usage_stats.totals)
    users,groups=broadcast_targets.get_target_counts()
    text=(f"📊 <b>Collei statistics</b>\n\n"
          f"Users: <b>{users:,}</b>\nGroups: <b>{groups:,}</b>\n"
          f"Inline searches: <b>{values.get('inline',0):,}</b>\n"
          f"Commands used: <b>{values.get('commands',0):,}</b>\n\n"
          f"Usage counted since {values['since']} UTC. Each received inline query counts once; /stat is included in command usage.")
    await message.reply(text,parse_mode='HTML')
