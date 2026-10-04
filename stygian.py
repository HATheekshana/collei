#!/usr/bin/env python3
"""
stygian_card.py
================

Given a Stygian Onslaught disaster id (e.g. 5269010, ...):

  1. Downloads monster.json / character.json (kept for parity).
  2. Downloads en/leyline/{id}.json for that disaster
     (6 difficulty tiers, each with the same rotating Nemeses,
      whose names/buffs/descriptions escalate with difficulty).
  3. Downloads leyline.json for the global schedule (begin/end per id).
  4. Renders a futuristic Stygian Onslaught card in the same visual
     language as theatre_card.py / abyss_card.py.

Usage:
    python stygian_card.py 5269010
    python stygian_card.py 5269010 --no-update
"""

import argparse
import io
from utils import endgame_data_db
import json
import os
import re
import urllib.request
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ------------------------------------------------------------------ CONFIG

VERSION = "7.1"
LANG = "en"

BASE = f"https://static.nanoka.cc/gi/{VERSION}"

MONSTER_URL = f"{BASE}/monster.json"
CHARACTER_URL = f"{BASE}/character.json"

# Individual disaster data: 6 difficulty tiers x rotating Nemeses
LEYLINE_URL_TMPL = f"{BASE}/{LANG}/leyline/{{num}}.json"

# IMPORTANT:
# This is the file containing, per disaster id, the begin/end window:
#
# "5269010": {
#     "begin": "2026-07-08 10:00:00",
#     "end": "2026-08-19 09:59:59",
#     "en": "Savage Tremors",
#     ...
# }
LEYLINE_SCHEDULE_URL = f"{BASE}/leyline.json"

ASSET_BASE = "https://static.nanoka.cc/assets/gi"


HERE = os.path.dirname(os.path.abspath(__file__))

CACHE_DIR = os.path.join(HERE, "cache")
ASSET_CACHE_DIR = os.path.join(CACHE_DIR, "assets")
OUTPUT_DIR = os.path.join(HERE, "output")

for d in (CACHE_DIR, ASSET_CACHE_DIR, OUTPUT_DIR):
    os.makedirs(d, exist_ok=True)


MONSTER_CACHE = os.path.join(CACHE_DIR, "monster.json")
CHARACTER_CACHE = os.path.join(CACHE_DIR, "character.json")

LEYLINE_SCHEDULE_CACHE = os.path.join(CACHE_DIR, "leyline.json")


# ------------------------------------------------------------- THEME / UI

W = 1560

BG_TOP = (8, 10, 13)

PANEL = (13, 16, 20, 245)

PANEL_LINE = (61, 68, 76)
PANEL_LINE_SOFT = (39, 45, 52)

WHITE = (241, 244, 247)
CREAM = (232, 228, 218)
FAINT = (137, 145, 154)
MUTED = (94, 103, 112)

GOLD = (232, 199, 135)
GOLD_SOFT = (193, 169, 121)
GOLD_DIM = (94, 80, 61)

CHIP = (20, 24, 29, 255)

# Stygian Onslaught gets a hellish ember accent -- distinct from the
# Theater's red "encore" and the Abyss's violet.
EMBER = (232, 122, 76)
EMBER_DIM = (110, 66, 45)

TIER_COLORS = {
    1: (150, 150, 150),   # Normal
    2: (126, 219, 154),   # Advancing
    3: (126, 200, 219),   # Hard
    4: (255, 196, 84),    # Menacing
    5: (232, 122, 76),    # Fearless
    6: (226, 93, 111),    # Dire
}

MARGIN = 64
SECTION_GAP = 24
CONTENT_W = W - MARGIN * 2

BOT_USERNAME = "@collei_help_bot"


# --------------------------------------------------------------- FONTS

FONT_DIR = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")

if not os.path.exists(FONT_DIR):
    FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def font(size, bold=False, serif=True):
    candidates = []

    if serif:
        candidates += [
            "georgiab.ttf" if bold else "georgia.ttf",
            "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf",
        ]
    else:
        candidates += [
            "arialbd.ttf" if bold else "arial.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        ]

    for name in candidates:
        path = os.path.join(FONT_DIR, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default(size=size)


F_TITLE = font(52, bold=True, serif=False)
F_SUB = font(24, bold=False, serif=False)
F_KICKER = font(17, bold=True, serif=False)
F_H2 = font(23, bold=True, serif=False)
F_LABEL = font(19, bold=True, serif=False)
F_BODY = font(16, bold=False, serif=False)
F_SMALL = font(15, bold=False, serif=False)
F_NAME = font(18, bold=True, serif=False)
F_TAG = font(13, bold=True, serif=False)
F_BADGE = font(21, bold=True, serif=False)
F_MICRO = font(11, bold=True, serif=False)


# ------------------------------------------------------------ NETWORKING

def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def update_core_data():
    for url, path, label in (
        (MONSTER_URL, MONSTER_CACHE, "monster.json"),
        (CHARACTER_URL, CHARACTER_CACHE, "character.json"),
    ):
        try:
            data = _get(url)
            json.loads(data)
            endgame_data_db.save(path, data)
            print(f"[update] {label} -> {path} ({len(data)} bytes)")
        except Exception as e:
            print(f"[update] FAILED to fetch {label} from {url}: {e}")
            if not endgame_data_db.exists(path):
                raise SystemExit(
                    f"No cached copy of {label} exists either. "
                    f"Check your network / URL."
                )
            print(f"[update] keeping existing cached copy of {label}")


def _page_leyline(num):
    """Read the same versioned dataset that Nanoka's public page uses."""
    global LEYLINE_SCHEDULE_URL
    page = _get(f"https://gi.nanoka.cc/leyline/{int(num)}/").decode("utf-8")
    pattern = (r'https://static\.nanoka\.cc/gi/'
               r'(\d+(?:\.\d+)+)/en/leyline/' + str(int(num)) + r'\.json')
    match = re.search(pattern, page)
    if not match:
        raise ValueError("Nanoka page did not provide a leyline data URL")
    # Use a URL validated against our expected host, ID and numeric version.
    url = match.group(0)
    data = _get(url)
    parsed = json.loads(data)
    if not isinstance(parsed, dict) or str(parsed.get("id")) != str(num):
        raise ValueError("Nanoka returned an unexpected leyline record")
    LEYLINE_SCHEDULE_URL = f"https://static.nanoka.cc/gi/{match.group(1)}/leyline.json"
    return data


def fetch_leyline(num):
    path = os.path.join(CACHE_DIR, f"leyline_{num}.json")
    errors = []
    for fetch in (lambda: _page_leyline(num),
                  lambda: _get(LEYLINE_URL_TMPL.format(num=num))):
        try:
            data = fetch()
            parsed = json.loads(data)
            if not isinstance(parsed, dict) or str(parsed.get("id")) != str(num):
                raise ValueError("Unexpected leyline record")
            endgame_data_db.save(path, data)
            print(f"[update] leyline {num} -> {path}")
            return path
        except Exception as e:
            errors.append(str(e))
            print(f"[update] leyline {num} fetch failed: {e}")
    if endgame_data_db.exists(path):
        print(f"[update] using cached leyline {num}")
        return path
    raise SystemExit(f"Could not fetch leyline {num}: {'; '.join(errors)}. No cached copy exists.")


def fetch_leyline_schedule():
    try:
        data = _get(LEYLINE_SCHEDULE_URL)
        parsed = json.loads(data)
        endgame_data_db.save(LEYLINE_SCHEDULE_CACHE, data)
        print(
            f"[update] leyline.json -> {LEYLINE_SCHEDULE_CACHE} "
            f"({len(data)} bytes)"
        )
        return parsed
    except Exception as e:
        print(f"[update] FAILED to fetch global leyline.json: {e}")
        if endgame_data_db.exists(LEYLINE_SCHEDULE_CACHE):
            print("[update] using cached leyline.json")
            return load_json(LEYLINE_SCHEDULE_CACHE)
        raise SystemExit(
            "No cached leyline.json exists either. "
            "Cannot determine START/END time."
        )


def load_json(path):
    return endgame_data_db.load(path)


# ---------------------------------------------------------------- ICONS

_icon_mem_cache = {}


def get_icon(kind, key, size):
    cache_key = (kind, key, size)

    if cache_key in _icon_mem_cache:
        return _icon_mem_cache[cache_key]

    fname = f"{kind}_{key}.webp".replace("/", "_")
    local_path = os.path.join(ASSET_CACHE_DIR, fname)

    img = None

    if os.path.exists(local_path):
        try:
            img = Image.open(local_path).convert("RGBA")
        except Exception:
            img = None

    if img is None:
        url = f"{ASSET_BASE}/{key}.webp"
        try:
            raw = _get(url)
            with open(local_path, "wb") as f:
                f.write(raw)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            img = _placeholder_icon(key, 256)

    img = img.resize((size, size), Image.LANCZOS)

    _icon_mem_cache[cache_key] = img

    return img


def _placeholder_icon(key, size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.ellipse([2, 2, size - 2, size - 2], fill=(46, 30, 28, 255))

    name = str(key).replace("UI_MonsterIcon_", "").replace("_", " ")

    initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"

    f = font(int(size * 0.34), bold=True, serif=False)

    bbox = d.textbbox((0, 0), initials, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    d.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
        initials,
        font=f,
        fill=CREAM + (255,)
    )

    return img


def circle_mask(img):
    size = img.size
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size[0], size[1]], fill=255)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


# --------------------------------------------------------------- DRAWING

def drop_shadow_panel(img, box, radius=18, blur=12, offset=5):
    x0, y0, x1, y1 = box
    pad = blur * 2

    shadow = Image.new(
        "RGBA",
        (int(x1 - x0 + pad * 2), int(y1 - y0 + pad * 2)),
        (0, 0, 0, 0)
    )

    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        [pad, pad + offset, x1 - x0 + pad, y1 - y0 + pad + offset],
        radius=radius,
        fill=(0, 0, 0, 120)
    )

    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))

    img.alpha_composite(shadow, (int(x0 - pad), int(y0 - pad)))


def wrap_text(draw, text, f, max_width):
    words = text.split()
    lines = []
    cur = ""

    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textbbox((0, 0), trial, font=f)[2] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w

    if cur:
        lines.append(cur)

    return lines


def strip_color_tags(s):
    s = re.sub(r"</?color[^>]*>", "", s or "", flags=re.IGNORECASE)
    s = re.sub(r"</?Color[^>]*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\{SPRITE_PRESET#\d+\}", "", s)
    s = s.replace("\\n", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_recommend(entries):
    """
    recommend_list entries look like:
        "{SPRITE_PRESET#11001} Characters <Color=#FFFFFF40> | </Color> Ranged Characters"
    Split on '|' after stripping tags/presets, keep non-empty parts.
    """

    out = []

    for e in entries or []:
        cleaned = strip_color_tags(e)
        for part in cleaned.split("|"):
            part = part.strip(" .")
            if part:
                out.append(part)

    # de-dupe while preserving order
    seen = set()
    result = []
    for p in out:
        if p not in seen:
            seen.add(p)
            result.append(p)

    return result


def chip(
    draw, x, y, text,
    f=F_SMALL, fg=FAINT, bg=CHIP, outline=PANEL_LINE,
    pad_x=14, pad_y=8
):
    bbox = draw.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    x0, y0 = x, y
    x1 = x + tw + pad_x * 2
    y1 = y + th + pad_y * 2

    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=(y1 - y0) / 2,
        fill=bg,
        outline=outline,
        width=1
    )

    draw.text(
        (x0 + pad_x - bbox[0], y0 + pad_y - bbox[1]),
        text,
        font=f,
        fill=fg
    )

    return x1 - x0, y1 - y0


# ------------------------------------------------------------- TIME DATA

def parse_source_time(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def get_disaster_schedule(schedule_data, num, act_data):
    entry = schedule_data.get(str(num), {})

    begin_raw = str(
        entry.get("live_begin") or entry.get("begin") or ""
    ).strip()

    end_raw = str(
        entry.get("live_end") or entry.get("end") or ""
    ).strip()

    if not begin_raw:
        begin_raw = str(act_data.get("begin_time", "")).strip()

    if not end_raw:
        end_raw = str(act_data.get("end_time", "")).strip()

    return begin_raw, end_raw


# ------------------------------------------------------------- MAIN CARD

def build_card(num):

    load_json(MONSTER_CACHE)
    load_json(CHARACTER_CACHE)

    act = load_json(os.path.join(CACHE_DIR, f"leyline_{num}.json"))

    schedule_data = load_json(LEYLINE_SCHEDULE_CACHE)

    levels = act.get("level", {}) or {}

    tier_keys = sorted(levels.keys(), key=lambda x: int(x))

    if not tier_keys:
        raise SystemExit(f"No difficulty tiers found in leyline {num} data.")

    # The highest tier carries the most "evolved" Nemesis names/buffs --
    # used to populate the featured roster at the top of the card.
    top_tier = levels[tier_keys[-1]]

    nemeses = list((top_tier.get("level_config") or {}).values())

    # ------------------------------------------------------------
    # SMALL DRAWING HELPERS
    # ------------------------------------------------------------

    def txt(draw, x, y, s, f, fill=WHITE):
        draw.text((x, y), s, font=f, fill=fill)

    def centered(draw, cx, y, s, f, fill=WHITE):
        bbox = draw.textbbox((0, 0), s, font=f)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw / 2 - bbox[0], y), s, font=f, fill=fill)

    def fit_lines(draw, s, f, width, limit=3):
        return wrap_text(draw, strip_color_tags(s), f, width)[:limit]

    def line(draw, x1, y1, x2, y2, fill=PANEL_LINE_SOFT, width=1):
        draw.line((x1, y1, x2, y2), fill=fill, width=width)

    def corner_frame(draw, box, color=PANEL_LINE, cut=14, width=1):
        x0, y0, x1, y1 = box
        pts = [
            (x0 + cut, y0), (x1 - cut, y0), (x1, y0 + cut),
            (x1, y1 - cut), (x1 - cut, y1), (x0 + cut, y1),
            (x0, y1 - cut), (x0, y0 + cut),
        ]
        draw.line(pts + [pts[0]], fill=color, width=width, joint="curve")

    def section_header(draw, y, title, code, accent=GOLD):
        draw.rectangle([MARGIN, y + 4, MARGIN + 5, y + 25], fill=accent)
        txt(draw, MARGIN + 18, y, title.upper(), F_KICKER, WHITE)

        bbox = draw.textbbox((0, 0), code, font=F_MICRO)
        txt(
            draw, W - MARGIN - (bbox[2] - bbox[0]), y + 5,
            code, F_MICRO, MUTED
        )

        line(draw, MARGIN, y + 35, W - MARGIN, y + 35, PANEL_LINE, 1)

        cx = W / 2
        draw.rectangle([cx - 3, y + 33, cx + 3, y + 37], fill=accent)

    def technical_panel(draw, box, accent=None):
        x0, y0, x1, y1 = box
        draw.rectangle(box, fill=PANEL)
        corner_frame(draw, box, PANEL_LINE, cut=16, width=1)
        if accent:
            draw.rectangle([x0, y0, x0 + 3, y1], fill=accent)

    def monster_badge(img, draw, cx, cy, size, icon_key, accent=EMBER):
        if not icon_key:
            return

        icon = get_icon("monster", icon_key, size)
        circ = circle_mask(icon)

        img.paste(circ, (int(cx - size / 2), int(cy - size / 2)), circ)

        draw.ellipse(
            [cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2],
            outline=(205, 205, 205),
            width=2
        )

        draw.arc(
            [
                cx - size / 2 - 4, cy - size / 2 - 4,
                cx + size / 2 + 4, cy + size / 2 + 4
            ],
            205, 325,
            fill=accent,
            width=2
        )

    # ------------------------------------------------------------
    # PRE-COMPUTE HEIGHTS
    # ------------------------------------------------------------

    hero_h = 260

    n_nem = max(len(nemeses), 1)

    nem_gap = 18
    nem_w = (CONTENT_W - nem_gap * (n_nem - 1)) / n_nem

    nem_h = 460

    total_h = (
        48
        + hero_h
        + SECTION_GAP + 54 + nem_h
        + 70
    )

    # ------------------------------------------------------------
    # CANVAS
    # ------------------------------------------------------------

    img = Image.new("RGBA", (W, int(total_h)), BG_TOP + (255,))
    draw = ImageDraw.Draw(img)

    for gx in range(MARGIN, W - MARGIN + 1, 120):
        line(draw, gx, 0, gx, total_h, (20, 24, 29), 1)

    for gy in range(30, int(total_h), 120):
        line(draw, MARGIN, gy, W - MARGIN, gy, (19, 23, 28), 1)

    corner_frame(
        draw, [22, 22, W - 22, total_h - 22], (82, 89, 97), cut=22, width=2
    )
    corner_frame(
        draw, [31, 31, W - 31, total_h - 31], (38, 44, 51), cut=14, width=1
    )

    # ============================================================
    # HERO
    # ============================================================

    y = 48
    hero_y = y

    hero_box = [MARGIN, hero_y, W - MARGIN, hero_y + hero_h]

    technical_panel(draw, hero_box, accent=EMBER)

    txt(draw, MARGIN + 22, hero_y + 18, "STYGIAN ONSLAUGHT", F_KICKER, EMBER)
    txt(
        draw, MARGIN + 22, hero_y + 45,
        "DEEP DOMAIN / LEY LINE DISTURBANCE", F_MICRO, MUTED
    )

    id_label = f"DISASTER  /  {num}"
    bbox = draw.textbbox((0, 0), id_label, font=F_MICRO)
    txt(
        draw, W - MARGIN - 24 - (bbox[2] - bbox[0]), hero_y + 20,
        id_label, F_KICKER, WHITE
    )

    line(
        draw, MARGIN + 20, hero_y + 72, W - MARGIN - 20, hero_y + 72,
        PANEL_LINE, 1
    )

    centered(draw, W / 2, hero_y + 88, "STYGIAN ONSLAUGHT", F_TITLE, CREAM)

    disaster_name = act.get("name") or "Unknown Disturbance"

    centered(draw, W / 2, hero_y + 145, disaster_name.upper(), F_H2, EMBER)

    begin_raw, end_raw = get_disaster_schedule(schedule_data, num, act)

    begin_dt = parse_source_time(begin_raw)
    end_dt = parse_source_time(end_raw)
    now_dt = datetime.now()

    if begin_dt and now_dt < begin_dt:
        status = "UPCOMING"
        status_fill = (255, 196, 84)
    elif end_dt and now_dt > end_dt:
        status = "ENDED"
        status_fill = (150, 150, 150)
    elif begin_dt or end_dt:
        status = "ONLINE"
        status_fill = (126, 219, 154)
    else:
        status = "UNKNOWN"
        status_fill = MUTED

    module_y = hero_y + 178
    module_h = 60
    mgap = 14
    module_w = (CONTENT_W - mgap * 2) / 3

    modules = [
        ("STATUS", status, status_fill),
        ("START", begin_raw or "—", WHITE),
        ("END", end_raw or "—", WHITE),
    ]

    for i, (label, value, color) in enumerate(modules):
        x0 = MARGIN + i * (module_w + mgap)
        x1 = x0 + module_w

        draw.rounded_rectangle(
            [x0, module_y, x1, module_y + module_h],
            radius=8, fill=CHIP, outline=PANEL_LINE, width=1
        )

        txt(draw, x0 + 16, module_y + 8, label, F_MICRO, MUTED)

        if label == "STATUS":
            draw.ellipse(
                [x0 + 16, module_y + 33, x0 + 25, module_y + 42], fill=color
            )
            txt(draw, x0 + 34, module_y + 27, value, F_LABEL, color)
        else:
            txt(draw, x0 + 16, module_y + 30, value, F_SMALL, color)

    y = hero_y + hero_h

    # ============================================================
    # NEMESES
    # ============================================================

    y += SECTION_GAP

    section_header(
        draw, y, "Nemeses", f"THREAT / {len(nemeses):02d}", accent=EMBER
    )

    y += 54

    for i, boss in enumerate(nemeses):

        x = MARGIN + i * (nem_w + nem_gap)

        box = [x, y, x + nem_w, y + nem_h]

        draw.rectangle(box, fill=(13, 12, 14, 255))

        corner_frame(draw, box, EMBER_DIM, cut=15, width=1)

        draw.rectangle([x, y + 16, x + 3, y + nem_h - 16], fill=EMBER)

        badge_cx = x + nem_w / 2

        monster_badge(img, draw, badge_cx, y + 84, 128, boss.get("icon"))

        name = boss.get("name", "Unknown")

        name_lines = fit_lines(draw, name, F_NAME, nem_w - 32, limit=2)

        ny = y + 160

        for j, s in enumerate(name_lines):
            centered(draw, badge_cx, ny + j * 22, s, F_NAME, WHITE)

        by = ny + len(name_lines) * 22 + 10

        line(draw, x + 18, by, x + nem_w - 18, by, PANEL_LINE_SOFT, 1)

        by += 12

        buff_names = boss.get("monster_buff_name_list", []) or []
        buff_descs = boss.get("monster_buff_desc_list", []) or []

        for bi, bname in enumerate(buff_names[:2]):

            txt(draw, x + 18, by, strip_color_tags(bname).upper(), F_TAG, EMBER)

            by += 20

            desc = buff_descs[bi] if bi < len(buff_descs) else ""

            desc_lines = fit_lines(draw, desc, F_BODY, nem_w - 36, limit=3)

            for s in desc_lines:
                txt(draw, x + 18, by, s, F_BODY, FAINT)
                by += 18

            by += 8

        recs = clean_recommend(boss.get("recommend_list"))

        if recs:
            rx = x + 18
            ry = min(by, y + nem_h - 40)

            for r in recs[:2]:
                w, h = chip(
                    draw, rx, ry, r,
                    f=F_MICRO, fg=CREAM, bg=CHIP, outline=EMBER_DIM,
                    pad_x=10, pad_y=6
                )
                rx += w + 8

    y += nem_h

    # ============================================================
    # FOOTER
    # ============================================================

    y += SECTION_GAP + 8

    line(draw, MARGIN, y, W - MARGIN, y, PANEL_LINE, 1)

    y += 18

    txt(draw, MARGIN, y, "STYGIAN // ONSLAUGHT", F_MICRO, GOLD_SOFT)

    centered(draw, W / 2, y, f" PROVIDED BY {BOT_USERNAME}", F_MICRO, GOLD)

    txt(draw, MARGIN, y + 22, f" PROVIDED BY {BOT_USERNAME}", F_MICRO, MUTED)

    right = "THE DEEP DOES NOT FORGIVE."

    bbox = draw.textbbox((0, 0), right, font=F_MICRO)

    txt(
        draw, W - MARGIN - (bbox[2] - bbox[0]), y, right, F_MICRO, GOLD_SOFT
    )

    return img.crop((0, 0, W, int(y + 34))).convert("RGB")


# ------------------------------------------------------------------ CLI

def main():

    ap = argparse.ArgumentParser(
        description="Generate a Stygian Onslaught card"
    )

    ap.add_argument(
        "num", type=int, help="Disaster id, e.g. 5269010"
    )

    ap.add_argument(
        "--no-update",
        action="store_true",
        help="Skip downloading data and use cached files"
    )

    args = ap.parse_args()

    if not args.no_update:
        update_core_data()
        fetch_leyline(args.num)
        fetch_leyline_schedule()
    else:
        if not (
            endgame_data_db.exists(MONSTER_CACHE) and endgame_data_db.exists(CHARACTER_CACHE)
        ):
            raise SystemExit(
                "No cached monster/character data yet. "
                "Run without --no-update first."
            )

        if not endgame_data_db.exists(
            os.path.join(CACHE_DIR, f"leyline_{args.num}.json")
        ):
            raise SystemExit(
                f"No cached data for disaster {args.num} yet. "
                f"Run without --no-update first."
            )

        if not endgame_data_db.exists(LEYLINE_SCHEDULE_CACHE):
            raise SystemExit(
                "No cached leyline.json schedule exists. "
                "Run without --no-update first."
            )

    card = build_card(args.num)

    out_path = os.path.join(OUTPUT_DIR, f"stygian_{args.num}.png")

    card.save(out_path)

    print(f"[done] wrote {out_path} ({card.width}x{card.height})")


if __name__ == "__main__":
    main()