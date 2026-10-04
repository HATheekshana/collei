"""Fetch Lunaris weapon data; preserve existing records on partial failures."""
import asyncio
import html
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from utils.update_report import changes, entry
from utils import weapon_db

BASE = 'https://api.lunaris.moe/data'

def clean(value):
    return html.unescape(re.sub(r'<[^>]*>|\{/?LINK\b[^{}]*\}', '', str(value or ''), flags=re.I)).replace('\\n', '\n')

def convert(wid, data, listing, old, version):
    name=clean(data.get('name') or listing.get('enName'))
    stats=data.get('stats') or {}
    # Low-rarity weapons may stop below level 90.
    level=max((int(k) for k in stats if str(k).isdigit()), default=0)
    values=stats.get('90') or stats.get(str(level))
    if not name or not isinstance(values,dict) or not isinstance(values.get('atk'),(int,float)):
        raise ValueError('Missing weapon name or stats')
    secondary=next(({'name':clean(k),'value':v} for k,v in values.items() if k.lower()!='atk'),None)
    passive=data.get('passive') or {}
    refinements=passive.get('refinements') or {}
    result={**old,'id':int(wid),'name':name,'level_90':{'atk':values['atk'],'main_stat':secondary},
            'max_level':90 if stats.get('90') else level,
            'passive':{'name':clean(passive.get('name')) or None,'refinements':{f'R{i}':clean(refinements[str(i)].get('description')) for i in range(1,6) if isinstance(refinements.get(str(i)),dict)}},
            'source_version':version}
    if passive.get('name') and not result['passive']['refinements'].get('R1'):
        raise ValueError('Missing passive description')
    icon=data.get('weaponIcon') or listing.get('weaponIcon')
    if not result.get('image_url') and icon and re.fullmatch(r'[A-Za-z0-9_]+',icon):
        result['image_url']=f'{BASE}/assets/weaponicon/{icon}.webp'
    result.pop('error',None)
    return result

async def get_json(session,url):
    for attempt in range(3):
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()
        except (aiohttp.ClientError,asyncio.TimeoutError):
            if attempt==2:raise
            await asyncio.sleep(attempt+1)


async def update_weapons(progress=None):
    existing=await asyncio.to_thread(weapon_db.read_all)
    old={str(w['id']):w for w in existing}
    timeout=aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout,headers={'User-Agent':'Mozilla/5.0'}) as session:
        manifest=await get_json(session,f'{BASE}/version.json')
        version=manifest.get('version','')
        if not isinstance(version,str) or not re.fullmatch(r'\d+(?:\.\d+){1,3}',version):raise ValueError('Invalid provider version')
        listing=await get_json(session,f'{BASE}/{version}/weaponlist.json')
        if not isinstance(listing,dict) or not listing or any(not str(k).isdigit() or not isinstance(v,dict) for k,v in listing.items()):raise ValueError('Invalid weapon catalog')
        pending=list(listing)
        if progress:await progress(f'Updating weapons from dataset {version}…\nFetching {len(pending)} records. Existing data stays available.')
        semaphore=asyncio.Semaphore(6)
        async def fetch(wid):
            async with semaphore:
                try:
                    data=await get_json(session,f'{BASE}/{version}/en/weapon/{wid}.json')
                    return wid,convert(wid,data,listing[wid],old.get(wid,{}),version),None
                except (aiohttp.ClientError,asyncio.TimeoutError,ValueError,TypeError,KeyError,AttributeError) as error:
                    return wid,None,f"{type(error).__name__}" + (f" HTTP {error.status}" if isinstance(error,aiohttp.ClientResponseError) else "")
        results=await asyncio.gather(*(fetch(wid) for wid in pending))
    added=updated=unchanged=0;failed=[];added_records=[];changed_records=[]
    merged=dict(old)
    persisted, write_errors = await asyncio.to_thread(weapon_db.save_many, [item for _,item,error in results if item is not None])
    for wid,item,error in results:
        if item is None:
            failed.append(entry(wid, old.get(wid) or listing[wid], reason=error))
            continue
        if wid not in persisted:
            failed.append(entry(wid,item,reason=write_errors.get(wid,"Database write failed")))
            continue
        fields=changes(old.get(wid,{}),item)
        if wid not in old:
            added+=1;added_records.append(entry(wid,item))
        elif fields:
            updated+=1;changed_records.append(entry(wid,item,fields))
        else:
            unchanged+=1
        merged[wid]=item
    return {'version':version,'added':added,'updated':updated,'unchanged':unchanged,'failed':len(failed),'total':len(merged),
            'added_records':added_records,'changed_records':changed_records,'failures':failed}
