#!/usr/bin/env python3
"""
abyss_card.py
=============

Given a Spiral Abyss cycle number (e.g. 122, 123, ...):

  1. Downloads monster.json / character.json (kept for parity / future use).
  2. Downloads en/tower/{num}.json for that specific cycle
     (leyline disaster, floors 9-12, chambers, first/second half waves).
  3. Downloads tower.json for the global schedule (begin/end per cycle id).
  4. Renders a futuristic Spiral Abyss card in the same visual language
     as theatre_card.py.

Usage:
    python abyss_card.py 122
    python abyss_card.py 122 --no-update
"""

import argparse
import io
from utils import endgame_data_db
import json
import re
import os
import urllib.request
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ------------------------------------------------------------------ CONFIG

VERSION = "7.0.51"
LANG = "en"

BASE = f"https://static.nanoka.cc/gi/{VERSION}"

MONSTER_URL = f"{BASE}/monster.json"
CHARACTER_URL = f"{BASE}/character.json"

# Individual cycle data: leyline + floor/chamber/wave breakdown
TOWER_URL_TMPL = f"{BASE}/{LANG}/tower/{{num}}.json"

# IMPORTANT:
# This is the file containing, per cycle id:
#
# "122": {
#     "begin": "2026-08-06 04:00:00",
#     "end": "2026-08-07 03:59:59",
#     "icon": "UI_TowerBlessing_106",
#     "en": "Luster-Piercing Moon",
#     "desc": "...",
#     "live_begin": "...",   (not always present)
#     "live_end": "..."      (not always present)
# }
TOWER_SCHEDULE_URL = f"{BASE}/tower.json"

ASSET_BASE = "https://static.nanoka.cc/assets/gi"

ELEMENT_ICON_URL_TMPL = ASSET_BASE + "/{name}.webp"
CHARACTER_ICON_URL_TMPL = ASSET_BASE + "/{icon}.webp"


HERE = os.path.dirname(os.path.abspath(__file__))

CACHE_DIR = os.path.join(HERE, "cache")
ASSET_CACHE_DIR = os.path.join(CACHE_DIR, "assets")
OUTPUT_DIR = os.path.join(HERE, "output")

for d in (CACHE_DIR, ASSET_CACHE_DIR, OUTPUT_DIR):
    os.makedirs(d, exist_ok=True)


MONSTER_CACHE = os.path.join(CACHE_DIR, "monster.json")
CHARACTER_CACHE = os.path.join(CACHE_DIR, "character.json")

TOWER_SCHEDULE_CACHE = os.path.join(CACHE_DIR, "tower.json")


# ---------------------------------------------------------------- ELEMENTS

ELEMENT_COLORS = {
    "Pyro": (255, 90, 90),
    "Hydro": (90, 160, 255),
    "Anemo": (110, 225, 205),
    "Electro": (180, 120, 255),
    "Dendro": (120, 205, 105),
    "Cryo": (130, 220, 255),
    "Geo": (255, 205, 80),
}


# ------------------------------------------------------------- THEME / UI

W = 1560

BG_TOP = (8, 10, 13)
BG_BOTTOM = (8, 10, 13)

INK = (8, 10, 13)

PANEL = (13, 16, 20, 245)
PANEL_2 = (16, 19, 24, 245)

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
CHIP_LINE = (69, 76, 84)

# Abyss uses a violet accent instead of Theater's red "encore" accent,
# to visually distinguish the two card families at a glance.
ABYSS = (151, 120, 226)
ABYSS_DIM = (72, 58, 106)

FIRST_HALF = (126, 200, 219)
SECOND_HALF = (226, 150, 93)

MARGIN = 64
SECTION_GAP = 24
CONTENT_W = W - MARGIN * 2

BOT_USERNAME = "@collei_help_bot"


# --------------------------------------------------------------- FONTS

FONT_DIR = os.path.join(
    os.environ.get("WINDIR", "C:\\Windows"),
    "Fonts"
)

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
F_ACT = font(112, bold=True, serif=False)
F_SUB = font(24, bold=False, serif=False)
F_DATE = font(17, bold=False, serif=False)
F_KICKER = font(17, bold=True, serif=False)
F_H2 = font(23, bold=True, serif=False)
F_LABEL = font(19, bold=True, serif=False)
F_BODY = font(18, bold=False, serif=False)
F_SMALL = font(15, bold=False, serif=False)
F_NAME = font(17, bold=True, serif=False)
F_TAG = font(13, bold=True, serif=False)
F_BADGE = font(21, bold=True, serif=False)
F_MICRO = font(11, bold=True, serif=False)
F_HP = font(14, bold=True, serif=False)
F_BIG_MONO = font(42, bold=True, serif=False)


# ------------------------------------------------------------ NETWORKING

def _get(url, timeout=15):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def update_core_data():
    """
    Re-download monster.json and character.json.
    """

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


def _page_tower(num):
    """Read the same versioned dataset that Nanoka's public page uses."""
    global TOWER_SCHEDULE_URL, MONSTER_URL, CHARACTER_URL
    page = _get(f"https://gi.nanoka.cc/tower/{int(num)}/").decode("utf-8")
    pattern = (r'https://static\.nanoka\.cc/gi/'
               r'(\d+(?:\.\d+)+)/en/tower/' + str(int(num)) + r'\.json')
    match = re.search(pattern, page)
    if not match:
        raise ValueError("Nanoka page did not provide a tower data URL")
    # Use a URL validated against our expected host, ID and numeric version.
    url = match.group(0)
    data = _get(url)
    parsed = json.loads(data)
    if not isinstance(parsed, dict) or "floor" not in parsed:
        raise ValueError("Nanoka returned an unexpected tower record")
    TOWER_SCHEDULE_URL = f"https://static.nanoka.cc/gi/{match.group(1)}/tower.json"
    MONSTER_URL = f"https://static.nanoka.cc/gi/{match.group(1)}/monster.json"
    CHARACTER_URL = f"https://static.nanoka.cc/gi/{match.group(1)}/character.json"
    return data


def fetch_tower(num):
    path = os.path.join(CACHE_DIR, f"tower_{num}.json")
    errors = []
    for fetch in (lambda: _page_tower(num),
                  lambda: _get(TOWER_URL_TMPL.format(num=num))):
        try:
            data = fetch()
            parsed = json.loads(data)
            if not isinstance(parsed, dict) or "floor" not in parsed:
                raise ValueError("Unexpected tower record")
            endgame_data_db.save(path, data)
            print(f"[update] tower {num} -> {path}")
            return path
        except Exception as e:
            errors.append(str(e))
            print(f"[update] tower {num} fetch failed: {e}")
    if endgame_data_db.exists(path):
        print(f"[update] using cached tower {num}")
        return path
    raise SystemExit(f"Could not fetch tower {num}: {'; '.join(errors)}. No cached copy exists.")


def fetch_tower_schedule():
    """
    Download the GLOBAL tower.json.

    This file contains, per cycle id, the begin/end window and the
    leyline disaster metadata:

        "122": {
            "begin": "2026-08-06 04:00:00",
            "end": "2026-08-07 03:59:59",
            "icon": "UI_TowerBlessing_106",
            "en": "Luster-Piercing Moon",
            "desc": "..."
        }
    """

    try:
        data = _get(TOWER_SCHEDULE_URL)

        parsed = json.loads(data)

        endgame_data_db.save(TOWER_SCHEDULE_CACHE, data)

        print(
            f"[update] tower.json -> {TOWER_SCHEDULE_CACHE} "
            f"({len(data)} bytes)"
        )

        return parsed

    except Exception as e:
        print(f"[update] FAILED to fetch global tower.json: {e}")

        if endgame_data_db.exists(TOWER_SCHEDULE_CACHE):
            print("[update] using cached tower.json")
            return load_json(TOWER_SCHEDULE_CACHE)

        raise SystemExit(
            "No cached tower.json exists either. "
            "Cannot determine START/END time."
        )


def load_json(path):
    return endgame_data_db.load(path)


# ---------------------------------------------------------------- ICONS

_icon_mem_cache = {}


def get_icon(kind, key, size):
    """
    kind:
        element
        character
        monster
        blessing

    key:
        element name, or an icon field (character/monster/blessing all
        resolve to ASSET_BASE/{key}.webp)
    """

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

        if kind == "element":
            url = ELEMENT_ICON_URL_TMPL.format(name=key)
        elif kind == "character":
            url = CHARACTER_ICON_URL_TMPL.format(icon=key)
        else:
            url = f"{ASSET_BASE}/{key}.webp"

        try:
            raw = _get(url)

            with open(local_path, "wb") as f:
                f.write(raw)

            img = Image.open(io.BytesIO(raw)).convert("RGBA")

        except Exception:
            img = _placeholder_icon(kind, key, 256)

    img = img.resize((size, size), Image.LANCZOS)

    _icon_mem_cache[cache_key] = img

    return img


def _placeholder_icon(kind, key, size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    d = ImageDraw.Draw(img)

    if kind == "element":

        color = ELEMENT_COLORS.get(key, (150, 150, 150))

        d.ellipse([3, 3, size - 3, size - 3], fill=color + (255,))

        letter = (key or "?")[0]

        f = font(int(size * 0.48), bold=True, serif=False)

        bbox = d.textbbox((0, 0), letter, font=f)

        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        d.text(
            ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
            letter,
            font=f,
            fill=(22, 17, 19, 255)
        )

    else:

        fill = (56, 43, 50, 255) if kind == "character" else (34, 28, 46, 255)

        d.ellipse([2, 2, size - 2, size - 2], fill=fill)

        name = (
            str(key)
            .replace("UI_AvatarIcon_", "")
            .replace("UI_MonsterIcon_", "")
            .replace("UI_TowerBlessing_", "")
            .replace("_", " ")
        )

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

def ornament_rule(draw, y, width=CONTENT_W, color=GOLD_DIM, cx=None):
    cx = cx if cx is not None else W / 2

    half = width / 2
    gap = 22

    draw.line([(cx - half, y), (cx - gap, y)], fill=color, width=2)
    draw.line([(cx + gap, y), (cx + half, y)], fill=color, width=2)

    d = 7

    draw.polygon(
        [(cx, y - d), (cx + d, y), (cx, y + d), (cx - d, y)],
        outline=GOLD,
        fill=None
    )


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


def text_center(draw, xy, text, f, fill, anchor_x_center):
    bbox = draw.textbbox((0, 0), text, font=f)

    tw = bbox[2] - bbox[0]

    draw.text((anchor_x_center - tw / 2, xy[1]), text, font=f, fill=fill)


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
    import re

    s = re.sub(r"</?color[^>]*>", "", s or "")

    s = s.replace("\\n", " ").replace("\n", " ")

    s = re.sub(r"\s+", " ", s).strip()

    return s


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


def wrapped_chip_row(draw, x, y, max_w, texts, **kwargs):
    """
    Lay chips out left-to-right, wrapping onto new rows when they'd
    overflow max_w. Returns the y position just below the last row.
    """

    gap = 10
    row_h = 0

    cx = x

    for t in texts:

        w, h = chip(draw, cx, y, t, **kwargs)

        row_h = max(row_h, h)

        cx += w + gap

        if cx > x + max_w:
            # measure again on a fresh row (the chip we just drew
            # overflowed visually, but since chip() already drew it
            # we accept the minor overflow on the final item rather
            # than double-drawing; callers keep text lists short).
            pass

    return y + row_h


# ------------------------------------------------------------- TIME DATA

def parse_source_time(value):
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def get_cycle_schedule(schedule_data, num, act_data):
    """
    Resolve START/END for a cycle.

    Preference order:
        1. live_begin / live_end from the global tower.json (when present)
        2. begin / end from the global tower.json
        3. open / close from the individual tower/{num}.json file
    """

    entry = schedule_data.get(str(num), {})

    begin_raw = str(
        entry.get("live_begin") or entry.get("begin") or ""
    ).strip()

    end_raw = str(
        entry.get("live_end") or entry.get("end") or ""
    ).strip()

    if not begin_raw:
        begin_raw = str(act_data.get("open", "")).strip()

    if not end_raw:
        end_raw = str(act_data.get("close", "")).strip()

    return begin_raw, end_raw


def format_hp(hp):
    try:
        return f"{int(round(float(hp))):,}"
    except (TypeError, ValueError):
        return str(hp)


def format_time_tiers(cond):
    """
    cond looks like [[2, 60], [2, 180], [2, 300]] -- a list of
    [tier, seconds_remaining_threshold] pairs describing the bonus-star
    time brackets for a chamber. We only render the seconds, ascending,
    since the tier index is not consistently documented.
    """

    seconds = sorted({
        int(pair[1])
        for pair in (cond or [])
        if isinstance(pair, (list, tuple)) and len(pair) >= 2
    })

    return [f"{s}s" for s in seconds]


# ------------------------------------------------------------- MAIN CARD

def build_card(num):

    # Loaded for parity with theatre_card.py / potential future use
    # (character & monster master lists aren't required to render the
    # abyss card since tower/{num}.json already embeds monster name+icon).
    load_json(MONSTER_CACHE)
    load_json(CHARACTER_CACHE)

    act = load_json(os.path.join(CACHE_DIR, f"tower_{num}.json"))

    schedule_data = load_json(TOWER_SCHEDULE_CACHE)

    leyline = act.get("leyline", {}) or {}

    floors_raw = act.get("floor", {}) or {}

    # Only the final two floors are shown on the card -- floors 9/10
    # are cleared automatically and aren't worth the space.
    SHOWN_FLOORS = {"11", "12"}

    floor_keys = sorted(
        (k for k in floors_raw.keys() if k in SHOWN_FLOORS),
        key=lambda x: int(x)
    )

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
        lines = wrap_text(draw, strip_color_tags(s), f, width)
        return lines[:limit]

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
            draw,
            W - MARGIN - (bbox[2] - bbox[0]),
            y + 5,
            code,
            F_MICRO,
            MUTED
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

    def monster_badge(img, draw, cx, cy, size, mon, accent=GOLD):
        key = mon.get("icon")

        if not key:
            return

        icon = get_icon("monster", key, size)

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

    def wave_column(img, draw, x, y, width, monsters, accent, label):
        """
        Renders one half's (first/second) monster wave list.
        Returns the height consumed.
        """

        txt(draw, x, y, label, F_TAG, accent)

        row_y = y + 24

        row_h = 54

        icon_size = 44

        for mon in monsters:

            monster_badge(
                img, draw,
                x + icon_size / 2, row_y + row_h / 2 - 2,
                icon_size,
                mon,
                accent
            )

            name = mon.get("name", "Unknown")

            name_lines = wrap_text(
                draw, name, F_SMALL, width - icon_size - 16
            )[:2]

            ty = row_y + row_h / 2 - (len(name_lines) * 17) / 2 - 6

            for i, s in enumerate(name_lines):
                txt(
                    draw,
                    x + icon_size + 14,
                    ty + i * 17,
                    s,
                    F_SMALL,
                    WHITE
                )

            hp_y = ty + len(name_lines) * 17 + 1

            txt(
                draw,
                x + icon_size + 14,
                hp_y,
                f"HP {format_hp(mon.get('hp', 0))}",
                F_MICRO,
                FAINT
            )

            row_y += row_h

        if not monsters:
            txt(draw, x, row_y, "—", F_SMALL, MUTED)
            row_y += 30

        return row_y - y

    # ------------------------------------------------------------
    # PRE-COMPUTE HEIGHTS
    # ------------------------------------------------------------

    hero_h = 300

    floor_blocks = []  # (floor_key, floor_h, chamber_layout)

    for fk in floor_keys:

        fdata = floors_raw[fk]

        buffs = fdata.get("buff", []) or []

        rooms = fdata.get("room", {}) or {}

        room_keys = sorted(rooms.keys(), key=lambda x: int(x))

        # header + wrapped buff chip rows (estimated 1 row unless long)
        header_h = 54

        buff_h = 0

        if buffs:
            # rough estimate: one row per ~2 buffs at this width
            buff_h = 46 * max(1, (len(buffs) + 1) // 2)

        extra_buff_h = 0

        if fk == "12":
            extras = [
                fdata.get("first_half_buff"),
                fdata.get("second_half_buff"),
            ]
            extras = [e for e in extras if e]
            if extras:
                extra_buff_h = 46 * len(extras)

        chamber_layouts = []

        chambers_h = 0

        for rk in room_keys:

            room = rooms[rk]

            first = room.get("first", []) or []
            second = room.get("second", []) or []

            max_rows = max(len(first), len(second), 1)

            body_h = max_rows * 54 + 30

            chamber_h = 56 + body_h  # header strip + wave columns

            chamber_layouts.append((rk, room, chamber_h))

            chambers_h = max(chambers_h, chamber_h)

        # chambers are laid out in a row of up to 3, same height each
        floor_h = (
            header_h
            + buff_h
            + extra_buff_h
            + 16
            + chambers_h
            + 20
        )

        floor_blocks.append((fk, floor_h, chamber_layouts, chambers_h))

    total_h = (
        48
        + hero_h
        + sum(SECTION_GAP + fh for _, fh, _, _ in floor_blocks)
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
    # HERO / ABYSS STATUS
    # ============================================================

    y = 48

    hero_y = y

    hero_box = [MARGIN, hero_y, W - MARGIN, hero_y + hero_h]

    technical_panel(draw, hero_box, accent=ABYSS)

    txt(draw, MARGIN + 22, hero_y + 18, "SPIRAL ABYSS", F_KICKER, ABYSS)
    txt(
        draw, MARGIN + 22, hero_y + 45,
        "ABYSSAL MOON SPIRE / DEEPEST DEPTHS", F_MICRO, MUTED
    )

    cycle_label = f"CYCLE  /  {num}"

    bbox = draw.textbbox((0, 0), cycle_label, font=F_MICRO)

    txt(
        draw,
        W - MARGIN - 24 - (bbox[2] - bbox[0]),
        hero_y + 20,
        cycle_label,
        F_KICKER,
        WHITE
    )

    line(
        draw, MARGIN + 20, hero_y + 72, W - MARGIN - 20, hero_y + 72,
        PANEL_LINE, 1
    )

    centered(draw, W / 2, hero_y + 88, "SPIRAL ABYSS", F_TITLE, CREAM)

    leyline_name = leyline.get("name") or leyline.get("en") or "Unknown Moon"

    centered(draw, W / 2, hero_y + 145, leyline_name.upper(), F_H2, ABYSS)

    desc_lines = fit_lines(
        draw, leyline.get("desc", ""), F_SMALL, CONTENT_W - 400, limit=2
    )

    for i, s in enumerate(desc_lines):
        centered(draw, W / 2, hero_y + 174 + i * 20, s, F_SMALL, FAINT)

    # Schedule / status

    begin_raw, end_raw = get_cycle_schedule(schedule_data, num, act)

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

    module_y = hero_y + 222

    module_h = 60

    gap = 14

    module_w = (CONTENT_W - gap * 2) / 3

    modules = [
        ("STATUS", status, status_fill),
        ("START", begin_raw or "—", WHITE),
        ("END", end_raw or "—", WHITE),
    ]

    for i, (label, value, color) in enumerate(modules):

        x0 = MARGIN + i * (module_w + gap)
        x1 = x0 + module_w

        draw.rounded_rectangle(
            [x0, module_y, x1, module_y + module_h],
            radius=8, fill=CHIP, outline=PANEL_LINE, width=1
        )

        txt(draw, x0 + 16, module_y + 8, label, F_MICRO, MUTED)

        if label == "STATUS":
            draw.ellipse(
                [x0 + 16, module_y + 33, x0 + 25, module_y + 42],
                fill=color
            )
            txt(draw, x0 + 34, module_y + 27, value, F_LABEL, color)
        else:
            txt(draw, x0 + 16, module_y + 30, value, F_SMALL, color)

    y = hero_y + hero_h

    # ============================================================
    # FLOORS
    # ============================================================

    for fk, floor_h, chamber_layouts, chambers_h in floor_blocks:

        y += SECTION_GAP

        section_header(
            draw, y, f"Floor {fk}", f"ABYSS / F{fk}", accent=ABYSS
        )

        y += 46

        fdata = floors_raw[fk]

        buffs = fdata.get("buff", []) or []

        if buffs:
            texts = [strip_color_tags(b) for b in buffs]

            cx = MARGIN
            cy = y
            row_h = 0

            for t in texts:
                w, h = chip(
                    draw, cx, cy, t,
                    f=F_SMALL, fg=CREAM, bg=CHIP, outline=ABYSS_DIM,
                    pad_x=14, pad_y=8
                )
                row_h = max(row_h, h)
                cx += w + 10
                if cx > MARGIN + CONTENT_W - 200:
                    cx = MARGIN
                    cy += row_h + 8
                    row_h = 0

            y = cy + row_h + 12

        if fk == "12":
            extras = [
                ("First Half", fdata.get("first_half_buff")),
                ("Second Half", fdata.get("second_half_buff")),
            ]

            for label, e in extras:
                if not e:
                    continue

                w, h = chip(
                    draw, MARGIN, y, f"{label}: {strip_color_tags(e)}",
                    f=F_SMALL, fg=GOLD, bg=CHIP, outline=GOLD_DIM,
                    pad_x=14, pad_y=8
                )
                y += h + 8

        y += 8

        # Chambers row

        n = len(chamber_layouts)

        cgap = 18

        cw = (CONTENT_W - cgap * (max(n, 1) - 1)) / max(n, 1)

        for i, (rk, room, _ch) in enumerate(chamber_layouts):

            x = MARGIN + i * (cw + cgap)

            box = [x, y, x + cw, y + chambers_h]

            draw.rectangle(box, fill=(11, 14, 18, 255))

            corner_frame(draw, box, ABYSS_DIM, cut=13, width=1)

            draw.rectangle(
                [x + 14, y + 14, x + 52, y + 48],
                outline=ABYSS,
                width=1
            )

            centered(draw, x + 33, y + 19, rk, F_LABEL, ABYSS)

            txt(
                draw, x + 64, y + 20,
                f"CHAMBER {rk}", F_TAG, WHITE
            )

            txt(
                draw, x + 64, y + 36,
                f"LV.{room.get('level', '?')}", F_MICRO, FAINT
            )

            tiers = format_time_tiers(room.get("cond"))

            if tiers:
                tier_text = "  ·  ".join(tiers)
                bbox = draw.textbbox((0, 0), tier_text, font=F_MICRO)
                txt(
                    draw,
                    x + cw - 16 - (bbox[2] - bbox[0]),
                    y + 26,
                    tier_text,
                    F_MICRO,
                    MUTED
                )

            line(draw, x + 14, y + 56, x + cw - 14, y + 56, PANEL_LINE_SOFT, 1)

            col_gap = 18

            col_w = (cw - 28 - col_gap) / 2

            col_y = y + 68

            wave_column(
                img, draw, x + 14, col_y, col_w,
                room.get("first", []) or [],
                FIRST_HALF, "FIRST HALF"
            )

            wave_column(
                img, draw, x + 14 + col_w + col_gap, col_y, col_w,
                room.get("second", []) or [],
                SECOND_HALF, "SECOND HALF"
            )

        y += chambers_h

    # ============================================================
    # FOOTER
    # ============================================================

    y += SECTION_GAP + 8

    line(draw, MARGIN, y, W - MARGIN, y, PANEL_LINE, 1)

    y += 18

    txt(draw, MARGIN, y, "SPIRAL // ABYSS", F_MICRO, GOLD_SOFT)

    centered(draw, W / 2, y, f" PROVIDED BY {BOT_USERNAME}", F_MICRO, GOLD)

    txt(draw, MARGIN, y + 22, f" PROVIDED BY {BOT_USERNAME}", F_MICRO, MUTED)

    right = "DESCEND, IF YOU DARE."

    bbox = draw.textbbox((0, 0), right, font=F_MICRO)

    txt(
        draw, W - MARGIN - (bbox[2] - bbox[0]), y, right, F_MICRO, GOLD_SOFT
    )

    return img.crop((0, 0, W, int(y + 34))).convert("RGB")


# ------------------------------------------------------------------ CLI

def main():

    ap = argparse.ArgumentParser(
        description="Generate a Spiral Abyss card"
    )

    ap.add_argument("num", type=int, help="Abyss cycle number, e.g. 122")

    ap.add_argument(
        "--no-update",
        action="store_true",
        help="Skip downloading data and use cached files"
    )

    args = ap.parse_args()

    if not args.no_update:

        fetch_tower(args.num)
        update_core_data()
        fetch_tower_schedule()

    else:

        if not (
            endgame_data_db.exists(MONSTER_CACHE) and endgame_data_db.exists(CHARACTER_CACHE)
        ):
            raise SystemExit(
                "No cached monster/character data yet. "
                "Run without --no-update first."
            )

        if not endgame_data_db.exists(
            os.path.join(CACHE_DIR, f"tower_{args.num}.json")
        ):
            raise SystemExit(
                f"No cached data for cycle {args.num} yet. "
                f"Run without --no-update first."
            )

        if not endgame_data_db.exists(TOWER_SCHEDULE_CACHE):
            raise SystemExit(
                "No cached tower.json schedule exists. "
                "Run without --no-update first."
            )

    card = build_card(args.num)

    out_path = os.path.join(OUTPUT_DIR, f"abyss_cycle{args.num}.png")

    card.save(out_path)

    print(f"[done] wrote {out_path} ({card.width}x{card.height})")


if __name__ == "__main__":
    main()