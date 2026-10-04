"""Refresh Nanoka character descriptions, retaining records on partial failures."""
import asyncio
import json
import re
from pathlib import Path
from datetime import datetime, timezone
import aiohttp
from utils.update_report import changes, entry
from utils.weapon_update import get_json
from utils import storage

BASE = "https://static.nanoka.cc/gi"
ROSTER = "https://sg-act-public-api.hoyolab.com/event/e20200928calculate/v1/avatar/list"

def clean(text):
    text = re.sub(r"</?color(?:=[^>]*)?>", "", str(text or ""), flags=re.I)
    return re.sub(r"\{/?LINK\b[^{}]*\}", "", text, flags=re.I).replace("\\n", "\n")

def part(item):
    if not isinstance(item, dict) or not item.get("name") or not item.get("desc"):
        raise ValueError("Incomplete skill/constellation")
    description = clean(item["desc"])
    special = clean(item.get("special_desc"))
    if special.strip() and special.strip() != description.strip():
        description += "\n\n<b>Special version</b>\n" + special
    return {"id": item.get("id"), "name": clean(item["name"]), "description": description}

def convert(cid, data, version):
    skills = data["skills"]
    def icon(item):
        return str(next(iter(item.get("promote", {}).values()), {}).get("icon", ""))
    skill = next((s for s in skills if icon(s).startswith("Skill_S_")), None)
    burst = next((s for s in skills if icon(s).startswith("Skill_E_")), None)
    if skill is None or burst is None:
        raise ValueError("Cannot identify elemental skill/burst safely")
    cons = [part(c) for c in data["constellations"]]
    if len(cons) != 6 or not data.get("name"):
        raise ValueError("Incomplete character")
    return {"id": str(cid), "name": clean(data["name"]), "constellations": cons,
            "elemental_skill": part(skill), "elemental_burst": part(burst),
            "passive_talents": [part(t) for t in data["passives"]],
            "source_version": version}

async def roster_ids(session):
    ids = set()
    for page in range(1, 21):
        async with session.post(ROSTER, json={"page": page, "size": 100, "is_all": True},
                                headers={"x-rpc-language": "en-us", "Referer": "https://act.hoyolab.com/"}) as response:
            response.raise_for_status()
            payload = await response.json()
        if payload.get("retcode") != 0:
            raise ValueError("HoYoLAB roster rejected")
        data = payload.get("data") or {}
        rows = data.get("list")
        if not isinstance(rows, list):
            raise ValueError("Invalid HoYoLAB roster")
        new = {str(item["id"]) for item in rows if isinstance(item, dict) and str(item.get("id", "")).isdigit()}
        if not new or new <= ids:
            break
        ids.update(new)
        if len(rows) < 100:
            break
    if not ids:
        raise ValueError("Empty HoYoLAB roster")
    return ids

async def choose_version(session, old, override, hints=()):
    if override:
        if not re.fullmatch(r"\d+\.\d+(?:\.\d+)*", override):
            raise ValueError("Use /update or /update 7.1")
        return override
    match = re.search(r"/gi/(\d+)\.(\d+)", old.get("source", ""))
    major, minor = max((7, 1), tuple(map(int, match.groups())) if match else (7, 1))
    # Check consecutive minor releases and the next major release.
    version = f"{major}.{minor}"
    await get_json(session, f"{BASE}/{version}/en/character/10000109.json")
    for candidate in [f"{major}.{n}" for n in range(minor+1, minor+4)] + [f"{major+1}.0"]:
        try:
            await get_json(session, f"{BASE}/{candidate}/en/character/10000109.json")
            version = candidate
        except aiohttp.ClientResponseError as error:
            if error.status != 404:
                raise
    # Patch releases may contain characters absent from the major.minor dataset.
    stored = re.search(r"/gi/(\d+(?:\.\d+)+)", old.get("source", ""))
    candidates = set(hints)
    if stored:
        candidates.add(stored.group(1))
    def version_key(value):
        return tuple(map(int, value.split(".")))
    for candidate in sorted((v for v in candidates if isinstance(v,str) and re.fullmatch(r"\d+(?:\.\d+)+",v)), key=version_key):
        if version_key(candidate) <= version_key(version):
            continue
        try:
            data = await get_json(session, f"{BASE}/{candidate}/en/character/10000109.json")
            convert("10000109",data,candidate)
            version = candidate
        except aiohttp.ClientResponseError as error:
            if error.status != 404:
                raise
    return version

async def update_characters(path, progress=None, version=None, extra_ids=(), version_hints=()):
    path = Path(path)
    old = await asyncio.to_thread(storage.read, "character_info", {"characters": []})
    previous = {str(c["id"]): c for c in old["characters"]}
    warnings = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25),
                                     headers={"User-Agent": "Mozilla/5.0"}) as session:
        version = await choose_version(session, old, version, version_hints)
        try:
            ids = await roster_ids(session)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as error:
            ids = set()
            warnings.append(f"HoYoLAB roster unavailable ({type(error).__name__}); saved and explicitly linked IDs only. Other new characters may be missing.")
        ids.update(str(cid) for cid in extra_ids if re.fullmatch(r"1000\d{4}", str(cid)))
        ids.update(cid for cid in previous if cid.isdigit())
        if not ids:
            raise ValueError("No character IDs available; existing data kept")
        # Also discover roster gaps and upcoming IDs directly from Nanoka.
        # Never infer a character exists from its ID: require a complete valid record.
        playable = [int(cid) for cid in ids if re.fullmatch(r"1000\d{4}", cid)]
        top = max(playable, default=10000002)
        discovery = {str(cid) for cid in range(10000002, min(top + 25, 10010000))} - ids
        semaphore = asyncio.Semaphore(5)
        blocked = asyncio.Event()
        async def fetch(cid):
            async with semaphore:
                try:
                    if cid in discovery:
                        if blocked.is_set():
                            return cid, None, "Discovery stopped after upstream rejection"
                        # A missing ID is expected during discovery; do not retry 404s.
                        async with session.get(f"{BASE}/{version}/en/character/{cid}.json") as response:
                            if response.status == 404:
                                return cid, None, None
                            if response.status in (403, 429):
                                blocked.set()
                            response.raise_for_status()
                            data = await response.json()
                    else:
                        data = await get_json(session, f"{BASE}/{version}/en/character/{cid}.json")
                    return cid, convert(cid, data, version), None
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, TypeError, AttributeError) as error:
                    return cid, None, type(error).__name__ + (f" HTTP {error.status}" if isinstance(error, aiohttp.ClientResponseError) else "")
        if progress:
            await progress(f"Updating character Cons and Skills from Nanoka {version}…\nChecking {len(ids)} known characters and {len(discovery)} possible new IDs.")
        results = await asyncio.gather(*(fetch(cid) for cid in sorted(ids | discovery)))
    if blocked.is_set():
        warnings.append("Nanoka rejected discovery requests. Discovery was stopped; retry later. Existing records are retained.")
    merged = dict(previous)
    added = updated = unchanged = 0
    failed, added_records, changed_records = [], [], []
    for cid, record, error in results:
        if record is None:
            if cid in discovery and error is None:
                continue
            failed.append(entry(cid, previous.get(cid, {}), reason=error))
            continue
        fields = changes(previous.get(cid, {}), record)
        if cid not in previous:
            added += 1
            added_records.append(entry(cid, record))
        elif fields:
            updated += 1
            changed_records.append(entry(cid, record, fields))
        else:
            unchanged += 1
        merged[cid] = record
    if added or updated or unchanged:
        saved = {**old, "source": f"{BASE}/{version}", "locale": "en",
                 "generated_at": datetime.now(timezone.utc).isoformat(),
                 "character_count": len(merged), "characters": list(merged.values()), "failures": failed}
        await asyncio.to_thread(storage.save, "character_info", saved)
    return {"version": version, "added": added, "updated": updated, "unchanged": unchanged,
            "failed": len(failed), "total": len(merged), "warnings": warnings, "failures": failed,
            "added_records": added_records, "changed_records": changed_records}
