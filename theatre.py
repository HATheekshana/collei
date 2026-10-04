#!/usr/bin/env python3
"""
theatre_card.py
===============

Given an Imaginarium Theater "act" number (e.g. 30, 31, ...):

  1. Downloads monster.json and character.json.
  2. Downloads en/rolecombat/{num}.json for that specific act.
  3. Downloads rolecombat.json for the START/END schedule.
  4. Renders a futuristic Imaginarium Theater card.

Usage:
    python theatre_card.py 30
    python theatre_card.py 31 --difficulty 3
    python theatre_card.py 30 --no-update
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

VERSION = "7.0.50"
LANG = "en"

BASE = f"https://static.nanoka.cc/gi/{VERSION}"

MONSTER_URL = f"{BASE}/monster.json"
CHARACTER_URL = f"{BASE}/character.json"

# Individual act combat data
ROLECOMBAT_URL_TMPL = f"{BASE}/{LANG}/rolecombat/{{num}}.json"

# IMPORTANT:
# This is the file containing:
#
# "30": {
#     "begin": "2026-08-06 04:00:00",
#     "end": "2026-08-25 03:59:59"
# }
#
# etc.
ROLECOMBAT_SCHEDULE_URL = f"{BASE}/rolecombat.json"

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

# NEW:
ROLECOMBAT_SCHEDULE_CACHE = os.path.join(
    CACHE_DIR,
    "rolecombat.json"
)


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

ENCORE = (226, 93, 111)
ENCORE_DIM = (110, 54, 62)

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

            # Validate JSON
            json.loads(data)

            endgame_data_db.save(path, data)

            print(
                f"[update] {label} -> "
                f"{path} ({len(data)} bytes)"
            )

        except Exception as e:
            print(
                f"[update] FAILED to fetch {label} "
                f"from {url}: {e}"
            )

            if not endgame_data_db.exists(path):
                raise SystemExit(
                    f"No cached copy of {label} exists either. "
                    f"Check your network / URL."
                )

            print(
                f"[update] keeping existing cached copy "
                f"of {label}"
            )


def _page_rolecombat(num):
    """Read the same versioned dataset that Nanoka's public page uses."""
    global ROLECOMBAT_SCHEDULE_URL, MONSTER_URL, CHARACTER_URL
    page = _get(f"https://gi.nanoka.cc/rolecombat/{int(num)}/").decode("utf-8")
    pattern = (r'https://static\.nanoka\.cc/gi/'
               r'(\d+(?:\.\d+)+)/en/rolecombat/' + str(int(num)) + r'\.json')
    match = re.search(pattern, page)
    if not match:
        raise ValueError("Nanoka page did not provide a rolecombat data URL")
    # Use a URL validated against our expected host, ID and numeric version.
    url = match.group(0)
    data = _get(url)
    parsed = json.loads(data)
    if not isinstance(parsed, dict) or "difficulty_config" not in parsed:
        raise ValueError("Nanoka returned an unexpected rolecombat record")
    ROLECOMBAT_SCHEDULE_URL = f"https://static.nanoka.cc/gi/{match.group(1)}/rolecombat.json"
    MONSTER_URL = f"https://static.nanoka.cc/gi/{match.group(1)}/monster.json"
    CHARACTER_URL = f"https://static.nanoka.cc/gi/{match.group(1)}/character.json"
    return data


def fetch_rolecombat(num):
    path = os.path.join(CACHE_DIR, f"rolecombat_{num}.json")
    errors = []
    for fetch in (lambda: _page_rolecombat(num),
                  lambda: _get(ROLECOMBAT_URL_TMPL.format(num=num))):
        try:
            data = fetch()
            parsed = json.loads(data)
            if not isinstance(parsed, dict) or "difficulty_config" not in parsed:
                raise ValueError("Unexpected rolecombat record")
            endgame_data_db.save(path, data)
            print(f"[update] rolecombat {num} -> {path}")
            return path
        except Exception as e:
            errors.append(str(e))
            print(f"[update] rolecombat {num} fetch failed: {e}")
    if endgame_data_db.exists(path):
        print(f"[update] using cached rolecombat {num}")
        return path
    raise SystemExit(f"Could not fetch rolecombat {num}: {'; '.join(errors)}. No cached copy exists.")


def fetch_rolecombat_schedule():
    """
    Download the GLOBAL rolecombat.json.

    This file contains the START/END schedule.

    Example:

        "30": {
            "begin": "2026-08-06 04:00:00",
            "end": "2026-08-25 03:59:59"
        }

    """

    try:
        data = _get(ROLECOMBAT_SCHEDULE_URL)

        parsed = json.loads(data)

        endgame_data_db.save(ROLECOMBAT_SCHEDULE_CACHE, data)

        print(
            f"[update] rolecombat.json -> "
            f"{ROLECOMBAT_SCHEDULE_CACHE} "
            f"({len(data)} bytes)"
        )

        return parsed

    except Exception as e:
        print(
            "[update] FAILED to fetch global "
            f"rolecombat.json: {e}"
        )

        if endgame_data_db.exists(
            ROLECOMBAT_SCHEDULE_CACHE
        ):
            print(
                "[update] using cached "
                "rolecombat.json"
            )

            return load_json(
                ROLECOMBAT_SCHEDULE_CACHE
            )

        raise SystemExit(
            "No cached rolecombat.json exists either. "
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

    key:
        element name or icon field
    """

    cache_key = (kind, key, size)

    if cache_key in _icon_mem_cache:
        return _icon_mem_cache[cache_key]

    fname = (
        f"{kind}_{key}.webp"
        .replace("/", "_")
    )

    local_path = os.path.join(
        ASSET_CACHE_DIR,
        fname
    )

    img = None

    if os.path.exists(local_path):
        try:
            img = Image.open(
                local_path
            ).convert("RGBA")
        except Exception:
            img = None

    if img is None:

        if kind == "element":
            url = ELEMENT_ICON_URL_TMPL.format(
                name=key
            )

        elif kind == "character":
            url = CHARACTER_ICON_URL_TMPL.format(
                icon=key
            )

        else:
            url = f"{ASSET_BASE}/{key}.webp"

        try:
            raw = _get(url)

            with open(local_path, "wb") as f:
                f.write(raw)

            img = Image.open(
                io.BytesIO(raw)
            ).convert("RGBA")

        except Exception:
            img = _placeholder_icon(
                kind,
                key,
                256
            )

    img = img.resize(
        (size, size),
        Image.LANCZOS
    )

    _icon_mem_cache[cache_key] = img

    return img


def _placeholder_icon(kind, key, size):
    """
    Draw placeholder if image cannot be downloaded.
    """

    img = Image.new(
        "RGBA",
        (size, size),
        (0, 0, 0, 0)
    )

    d = ImageDraw.Draw(img)

    if kind == "element":

        color = ELEMENT_COLORS.get(
            key,
            (150, 150, 150)
        )

        d.ellipse(
            [3, 3, size - 3, size - 3],
            fill=color + (255,)
        )

        letter = (key or "?")[0]

        f = font(
            int(size * 0.48),
            bold=True,
            serif=False
        )

        bbox = d.textbbox(
            (0, 0),
            letter,
            font=f
        )

        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        d.text(
            (
                (size - tw) / 2 - bbox[0],
                (size - th) / 2 - bbox[1]
            ),
            letter,
            font=f,
            fill=(22, 17, 19, 255)
        )

    else:

        d.ellipse(
            [2, 2, size - 2, size - 2],
            fill=(56, 43, 50, 255)
        )

        name = (
            str(key)
            .replace(
                "UI_AvatarIcon_",
                ""
            )
            .replace("_", " ")
        )

        initials = "".join(
            w[0]
            for w in name.split()[:2]
        ).upper() or "?"

        f = font(
            int(size * 0.34),
            bold=True,
            serif=False
        )

        bbox = d.textbbox(
            (0, 0),
            initials,
            font=f
        )

        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        d.text(
            (
                (size - tw) / 2 - bbox[0],
                (size - th) / 2 - bbox[1]
            ),
            initials,
            font=f,
            fill=CREAM + (255,)
        )

    return img


def circle_mask(img):
    size = img.size

    mask = Image.new(
        "L",
        size,
        0
    )

    ImageDraw.Draw(mask).ellipse(
        [0, 0, size[0], size[1]],
        fill=255
    )

    out = Image.new(
        "RGBA",
        size,
        (0, 0, 0, 0)
    )

    out.paste(
        img,
        (0, 0),
        mask
    )

    return out


def paste_circle_icon(
    img,
    icon,
    cx,
    cy,
    size,
    ring_color,
    ring_width=4
):
    circ = circle_mask(icon)

    img.paste(
        circ,
        (
            int(cx - size / 2),
            int(cy - size / 2)
        ),
        circ
    )

    d = ImageDraw.Draw(img)

    d.ellipse(
        [
            cx - size / 2,
            cy - size / 2,
            cx + size / 2,
            cy + size / 2
        ],
        outline=ring_color,
        width=ring_width
    )


def number_medallion(
    img,
    cx,
    cy,
    size,
    number,
    ring_color=GOLD,
    fill=(26, 20, 24, 255)
):
    d = ImageDraw.Draw(img)

    d.ellipse(
        [
            cx - size / 2,
            cy - size / 2,
            cx + size / 2,
            cy + size / 2
        ],
        fill=fill,
        outline=ring_color,
        width=3
    )

    text = str(number)

    bbox = d.textbbox(
        (0, 0),
        text,
        font=F_BADGE
    )

    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    d.text(
        (
            cx - tw / 2 - bbox[0],
            cy - th / 2 - bbox[1]
        ),
        text,
        font=F_BADGE,
        fill=ring_color
    )


# --------------------------------------------------------------- DRAWING

def vertical_gradient(
    w,
    h,
    top,
    bottom
):
    base = Image.new(
        "RGB",
        (w, h),
        top
    )

    draw = ImageDraw.Draw(base)

    for y in range(h):

        t = y / max(
            h - 1,
            1
        )

        c = tuple(
            int(
                top[i]
                + (bottom[i] - top[i]) * t
            )
            for i in range(3)
        )

        draw.line(
            [(0, y), (w, y)],
            fill=c
        )

    return base


def ornament_rule(
    draw,
    y,
    width=CONTENT_W,
    color=GOLD_DIM,
    cx=None
):
    cx = (
        cx
        if cx is not None
        else W / 2
    )

    half = width / 2
    gap = 22

    draw.line(
        [
            (cx - half, y),
            (cx - gap, y)
        ],
        fill=color,
        width=2
    )

    draw.line(
        [
            (cx + gap, y),
            (cx + half, y)
        ],
        fill=color,
        width=2
    )

    d = 7

    draw.polygon(
        [
            (cx, y - d),
            (cx + d, y),
            (cx, y + d),
            (cx - d, y)
        ],
        outline=GOLD,
        fill=None
    )


def drop_shadow_panel(
    img,
    box,
    radius=18,
    blur=12,
    offset=5
):
    x0, y0, x1, y1 = box

    pad = blur * 2

    shadow = Image.new(
        "RGBA",
        (
            int(x1 - x0 + pad * 2),
            int(y1 - y0 + pad * 2)
        ),
        (0, 0, 0, 0)
    )

    sd = ImageDraw.Draw(shadow)

    sd.rounded_rectangle(
        [
            pad,
            pad + offset,
            x1 - x0 + pad,
            y1 - y0 + pad + offset
        ],
        radius=radius,
        fill=(0, 0, 0, 120)
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(blur)
    )

    img.alpha_composite(
        shadow,
        (
            int(x0 - pad),
            int(y0 - pad)
        )
    )


def rounded_panel(
    img,
    draw,
    box,
    radius=18,
    fill=PANEL,
    outline=PANEL_LINE,
    width=2,
    shadow=True
):
    if shadow:
        drop_shadow_panel(
            img,
            box,
            radius=radius
        )

    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width
    )


def kicker(
    draw,
    y,
    text,
    color=GOLD_SOFT,
    cx=None
):
    cx = (
        cx
        if cx is not None
        else W / 2
    )

    text_center(
        draw,
        (0, y),
        text.upper(),
        F_KICKER,
        color,
        cx
    )

    return y + 30


def text_center(
    draw,
    xy,
    text,
    f,
    fill,
    anchor_x_center
):
    bbox = draw.textbbox(
        (0, 0),
        text,
        font=f
    )

    tw = bbox[2] - bbox[0]

    draw.text(
        (
            anchor_x_center - tw / 2,
            xy[1]
        ),
        text,
        font=f,
        fill=fill
    )


def wrap_text(
    draw,
    text,
    f,
    max_width
):
    words = text.split()

    lines = []
    cur = ""

    for w in words:

        trial = (
            cur + " " + w
        ).strip()

        if draw.textbbox(
            (0, 0),
            trial,
            font=f
        )[2] <= max_width:

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

    s = re.sub(
        r"</?color[^>]*>",
        "",
        s or ""
    )

    s = s.replace(
        "\\n",
        " "
    ).replace(
        "\n",
        " "
    )

    s = re.sub(
        r"\s+",
        " ",
        s
    ).strip()

    return s


def chip(
    draw,
    x,
    y,
    text,
    f=F_SMALL,
    fg=FAINT,
    bg=CHIP,
    outline=PANEL_LINE,
    pad_x=14,
    pad_y=8
):
    bbox = draw.textbbox(
        (0, 0),
        text,
        font=f
    )

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
        (
            x0 + pad_x - bbox[0],
            y0 + pad_y - bbox[1]
        ),
        text,
        font=f,
        fill=fg
    )

    return x1 - x0


# ------------------------------------------------------------- DATA PREP

def derive_featured_elements(
    ac,
    characters
):
    """
    Get the featured elements from buff_avatar_list.
    """

    order = []
    by_element = {}

    for b in ac.get(
        "buff_avatar_list",
        []
    ):

        c = characters.get(
            str(b["id"])
        ) or {}

        el = c.get("element")

        if el is None:
            continue

        if el not in by_element:
            by_element[el] = []
            order.append(el)

        by_element[el].append(
            {
                "id": b["id"],
                "en": c.get(
                    "en",
                    str(b["id"])
                ),
                "icon": c.get(
                    "icon",
                    str(b["id"])
                )
            }
        )

    return [
        (
            el,
            by_element[el]
        )
        for el in order
    ]


def grid_rows(
    items,
    n_cols=2
):
    rows = []

    for i in range(
        0,
        len(items),
        n_cols
    ):
        rows.append(
            items[i:i + n_cols]
        )

    return rows


# ------------------------------------------------------------- TIME DATA

def parse_source_time(value):
    """
    Parse the time format used by rolecombat.json.

    Example:
        2026-08-06 04:00:00
    """

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%S"
        )

    except (
        TypeError,
        ValueError
    ):
        return None


def get_act_schedule(
    schedule_data,
    num
):
    """
    Get START/END information for a specific act.

    rolecombat.json structure:

        {
            "30": {
                "begin": "...",
                "end": "...",
                ...
            }
        }
    """

    act = schedule_data.get(
        str(num),
        {}
    )

    begin_raw = str(
        act.get("live_begin", "")
    ).strip()

    end_raw = str(
        act.get("live_end", "")
    ).strip()

    return begin_raw, end_raw


# ------------------------------------------------------------- MAIN CARD

def build_card(
    num,
    difficulty="5"
):

    monsters = load_json(
        MONSTER_CACHE
    )

    characters = load_json(
        CHARACTER_CACHE
    )

    # Individual combat data
    combat = load_json(
        os.path.join(
            CACHE_DIR,
            f"rolecombat_{num}.json"
        )
    )

    # NEW:
    # Global schedule data
    schedule_data = load_json(
        ROLECOMBAT_SCHEDULE_CACHE
    )

    ac = combat["avatar_config"]

    diff = combat[
        "difficulty_config"
    ][str(difficulty)]

    rooms = diff.get(
        "room",
        {}
    )

    hard_rooms = diff.get(
        "hard_room",
        {}
    )


    def char(cid):
        return characters.get(
            str(cid)
        ) or {}


    starter_groups = derive_featured_elements(
        ac,
        characters
    )

    invite_ids = ac.get(
        "invite_avatar_list",
        []
    )


    star_rooms = [
        (rk, r)
        for rk, r in sorted(
            rooms.items(),
            key=lambda x: int(x[0])
        )
        if r.get("title")
    ]


    encore_rooms = [
        (rk, r)
        for rk, r in sorted(
            hard_rooms.items(),
            key=lambda x: int(x[0])
        )
    ]


    # ------------------------------------------------------------
    # SMALL DRAWING HELPERS
    # ------------------------------------------------------------

    def txt(
        draw,
        x,
        y,
        s,
        f,
        fill=WHITE
    ):
        draw.text(
            (x, y),
            s,
            font=f,
            fill=fill
        )


    def centered(
        draw,
        cx,
        y,
        s,
        f,
        fill=WHITE
    ):
        bbox = draw.textbbox(
            (0, 0),
            s,
            font=f
        )

        tw = bbox[2] - bbox[0]

        draw.text(
            (
                cx - tw / 2 - bbox[0],
                y
            ),
            s,
            font=f,
            fill=fill
        )


    def fit_lines(
        draw,
        s,
        f,
        width,
        limit=3
    ):
        lines = wrap_text(
            draw,
            strip_color_tags(s),
            f,
            width
        )

        return lines[:limit]


    def line(
        draw,
        x1,
        y1,
        x2,
        y2,
        fill=PANEL_LINE_SOFT,
        width=1
    ):
        draw.line(
            (
                x1,
                y1,
                x2,
                y2
            ),
            fill=fill,
            width=width
        )


    def corner_frame(
        draw,
        box,
        color=PANEL_LINE,
        cut=14,
        width=1
    ):
        x0, y0, x1, y1 = box

        pts = [
            (x0 + cut, y0),
            (x1 - cut, y0),
            (x1, y0 + cut),
            (x1, y1 - cut),
            (x1 - cut, y1),
            (x0 + cut, y1),
            (x0, y1 - cut),
            (x0, y0 + cut),
        ]

        draw.line(
            pts + [pts[0]],
            fill=color,
            width=width,
            joint="curve"
        )


    def section_header(
        draw,
        y,
        title,
        code,
        accent=GOLD
    ):
        draw.rectangle(
            [
                MARGIN,
                y + 4,
                MARGIN + 5,
                y + 25
            ],
            fill=accent
        )

        txt(
            draw,
            MARGIN + 18,
            y,
            title.upper(),
            F_KICKER,
            WHITE
        )

        bbox = draw.textbbox(
            (0, 0),
            code,
            font=F_MICRO
        )

        txt(
            draw,
            W - MARGIN
            - (bbox[2] - bbox[0]),
            y + 5,
            code,
            F_MICRO,
            MUTED
        )

        line(
            draw,
            MARGIN,
            y + 35,
            W - MARGIN,
            y + 35,
            PANEL_LINE,
            1
        )

        cx = W / 2

        draw.rectangle(
            [
                cx - 3,
                y + 33,
                cx + 3,
                y + 37
            ],
            fill=accent
        )


    def technical_panel(
        draw,
        box,
        accent=None
    ):
        x0, y0, x1, y1 = box

        draw.rectangle(
            box,
            fill=PANEL
        )

        corner_frame(
            draw,
            box,
            PANEL_LINE,
            cut=16,
            width=1
        )

        if accent:
            draw.rectangle(
                [
                    x0,
                    y0,
                    x0 + 3,
                    y1
                ],
                fill=accent
            )


    def avatar_tile(
        img,
        draw,
        cx,
        cy,
        size,
        icon_key,
        element=None
    ):
        color = ELEMENT_COLORS.get(
            element,
            PANEL_LINE
        )

        x0 = int(
            cx - size / 2
        )

        y0 = int(
            cy - size / 2
        )

        x1 = int(
            cx + size / 2
        )

        y1 = int(
            cy + size / 2
        )

        draw.rounded_rectangle(
            [
                x0,
                y0,
                x1,
                y1
            ],
            radius=9,
            fill=(10, 13, 17, 255),
            outline=PANEL_LINE,
            width=1
        )

        b = 12

        draw.line(
            [
                (x0, y0 + b),
                (x0, y0),
                (x0 + b, y0)
            ],
            fill=color,
            width=3
        )

        draw.line(
            [
                (x1 - b, y1),
                (x1, y1),
                (x1, y1 - b)
            ],
            fill=color,
            width=3
        )

        icon = get_icon(
            "character",
            icon_key,
            size - 10
        )

        img.paste(
            icon,
            (
                x0 + 5,
                y0 + 5
            ),
            icon
        )


    def monster_badge(
        img,
        draw,
        cx,
        cy,
        size,
        mon,
        accent=GOLD
    ):
        key = (
            mon.get("icon")
            or mon.get("filename_icon")
        )

        if not key:
            return

        icon = get_icon(
            "monster",
            key,
            size
        )

        circ = circle_mask(icon)

        img.paste(
            circ,
            (
                int(cx - size / 2),
                int(cy - size / 2)
            ),
            circ
        )

        draw.ellipse(
            [
                cx - size / 2,
                cy - size / 2,
                cx + size / 2,
                cy + size / 2
            ],
            outline=(205, 205, 205),
            width=2
        )

        draw.arc(
            [
                cx - size / 2 - 4,
                cy - size / 2 - 4,
                cx + size / 2 + 4,
                cy + size / 2 + 4
            ],
            205,
            325,
            fill=accent,
            width=2
        )


    def room_title(
        draw,
        x,
        y,
        room,
        width,
        accent=WHITE
    ):
        lines = fit_lines(
            draw,
            room.get(
                "title",
                ""
            ),
            F_NAME,
            width,
            3
        )

        for i, s in enumerate(lines):

            txt(
                draw,
                x,
                y + i * 23,
                s,
                F_NAME,
                accent
            )


    # ------------------------------------------------------------
    # HEIGHT
    # ------------------------------------------------------------

    hero_h = 315

    starter_h = (
        300
        if starter_groups
        else 0
    )

    cast_h = (
        218
        if invite_ids
        else 0
    )

    star_h = (
        320
        if star_rooms
        else 0
    )

    encore_h = (
        250
        if encore_rooms
        else 0
    )


    total_h = (
        48
        + hero_h
        + (
            SECTION_GAP
            + starter_h
            if starter_groups
            else 0
        )
        + (
            SECTION_GAP
            + cast_h
            if invite_ids
            else 0
        )
        + (
            SECTION_GAP
            + 54
            + star_h
            if star_rooms
            else 0
        )
        + (
            SECTION_GAP
            + 54
            + encore_h
            if encore_rooms
            else 0
        )
        + 70
    )


    # ------------------------------------------------------------
    # CANVAS
    # ------------------------------------------------------------

    img = Image.new(
        "RGBA",
        (
            W,
            int(total_h)
        ),
        BG_TOP + (255,)
    )

    draw = ImageDraw.Draw(img)


    # Technical grid

    for gx in range(
        MARGIN,
        W - MARGIN + 1,
        120
    ):
        line(
            draw,
            gx,
            0,
            gx,
            total_h,
            (20, 24, 29),
            1
        )

    for gy in range(
        30,
        int(total_h),
        120
    ):
        line(
            draw,
            MARGIN,
            gy,
            W - MARGIN,
            gy,
            (19, 23, 28),
            1
        )


    # Outer frame

    corner_frame(
        draw,
        [
            22,
            22,
            W - 22,
            total_h - 22
        ],
        (82, 89, 97),
        cut=22,
        width=2
    )

    corner_frame(
        draw,
        [
            31,
            31,
            W - 31,
            total_h - 31
        ],
        (38, 44, 51),
        cut=14,
        width=1
    )


    # ============================================================
    # HERO / THEATER STATUS
    # ============================================================

    y = 48

    hero_y = y

    hero_box = [
        MARGIN,
        hero_y,
        W - MARGIN,
        hero_y + hero_h
    ]

    technical_panel(
        draw,
        hero_box
    )


    # Top strip

    txt(
        draw,
        MARGIN + 22,
        hero_y + 18,
        "IMAGINARIUM THEATER",
        F_KICKER,
        GOLD
    )

    txt(
        draw,
        MARGIN + 22,
        hero_y + 45,
        "SEASONAL COMBAT ARCHIVE",
        F_MICRO,
        MUTED
    )


    # Theater number

    theater_label = (
        f"THEATER  /  {num:02d}"
    )

    bbox = draw.textbbox(
        (0, 0),
        theater_label,
        font=F_MICRO
    )

    txt(
        draw,
        W - MARGIN
        - 24
        - (bbox[2] - bbox[0]),
        hero_y + 20,
        theater_label,
        F_KICKER,
        WHITE
    )


    line(
        draw,
        MARGIN + 20,
        hero_y + 72,
        W - MARGIN - 20,
        hero_y + 72,
        PANEL_LINE,
        1
    )


    # Center title

    centered(
        draw,
        W / 2,
        hero_y + 88,
        "IMAGINARIUM THEATER",
        F_TITLE,
        CREAM
    )

    centered(
        draw,
        W / 2,
        hero_y + 145,
        f"ACT {num:02d}",
        F_H2,
        GOLD
    )


    # ============================================================
    # IMPORTANT:
    # Get begin/end from GLOBAL rolecombat.json
    # ============================================================

    begin_raw, end_raw = get_act_schedule(
        schedule_data,
        num
    )


    begin_dt = parse_source_time(
        begin_raw
    )

    end_dt = parse_source_time(
        end_raw
    )

    now_dt = datetime.now()


    # Status

    if begin_dt and now_dt < begin_dt:

        status = "UPCOMING"
        status_fill = (
            255,
            196,
            84
        )

    elif end_dt and now_dt > end_dt:

        status = "ENDED"
        status_fill = (
            150,
            150,
            150
        )

    elif begin_dt or end_dt:

        status = "ONLINE"
        status_fill = (
            126,
            219,
            154
        )

    else:

        status = "UNKNOWN"
        status_fill = MUTED


    # ============================================================
    # TELEMETRY MODULES
    # ============================================================

    module_y = hero_y + 198

    module_h = 72

    gap = 14

    module_w = (
        CONTENT_W - gap * 2
    ) / 3


    modules = [
        (
            "STATUS",
            status,
            status_fill
        ),
        (
            "START",
            begin_raw or "—",
            WHITE
        ),
        (
            "END",
            end_raw or "—",
            WHITE
        )
    ]


    for i, (
        label,
        value,
        color
    ) in enumerate(modules):

        x0 = (
            MARGIN
            + i * (
                module_w + gap
            )
        )

        x1 = x0 + module_w


        draw.rounded_rectangle(
            [
                x0,
                module_y,
                x1,
                module_y + module_h
            ],
            radius=8,
            fill=CHIP,
            outline=PANEL_LINE,
            width=1
        )


        txt(
            draw,
            x0 + 16,
            module_y + 10,
            label,
            F_MICRO,
            MUTED
        )


        if label == "STATUS":

            draw.ellipse(
                [
                    x0 + 16,
                    module_y + 39,
                    x0 + 25,
                    module_y + 48
                ],
                fill=color
            )

            txt(
                draw,
                x0 + 34,
                module_y + 32,
                value,
                F_LABEL,
                color
            )

        else:

            txt(
                draw,
                x0 + 16,
                module_y + 34,
                value,
                F_SMALL,
                color
            )


    # Difficulty

    diff_y = hero_y + 282

    txt(
        draw,
        MARGIN + 20,
        diff_y,
        f"DIFFICULTY  {difficulty}",
        F_MICRO,
        GOLD
    )

    txt(
        draw,
        MARGIN + 178,
        diff_y,
        "VISIONARY MODE / TACTICAL SIMULATION",
        F_MICRO,
        MUTED
    )


    y = hero_y + hero_h


    # ============================================================
    # STARTER CHARACTERS
    # ============================================================

    if starter_groups:

        y += SECTION_GAP

        box = [
            MARGIN,
            y,
            W - MARGIN,
            y + starter_h
        ]

        technical_panel(
            draw,
            box
        )

        section_header(
            draw,
            y + 18,
            "Starter Characters",
            "STARTER / 06"
        )


        n = len(starter_groups)

        cell_w = (
            CONTENT_W
            / max(n, 1)
        )


        for i, (
            el,
            chars_for_element
        ) in enumerate(
            starter_groups
        ):

            cx = (
                MARGIN
                + cell_w * i
                + cell_w / 2
            )

            color = ELEMENT_COLORS.get(
                el,
                GOLD
            )


            if i:

                line(
                    draw,
                    MARGIN + cell_w * i,
                    y + 66,
                    MARGIN + cell_w * i,
                    y + starter_h - 18,
                    PANEL_LINE_SOFT,
                    1
                )


            # Element icon

            element_icon = get_icon(
                "element",
                el,
                62
            )

            circ = circle_mask(
                element_icon
            )

            img.paste(
                circ,
                (
                    int(cx - 31),
                    int(y + 74)
                ),
                circ
            )

            draw.ellipse(
                [
                    cx - 34,
                    y + 71,
                    cx + 34,
                    y + 139
                ],
                outline=color,
                width=2
            )

            centered(
                draw,
                cx,
                y + 146,
                el.upper(),
                F_TAG,
                color
            )


            # Character pair

            pair = chars_for_element[:2]

            tile_size = 86
            tile_gap = 20

            total = (
                len(pair) * tile_size
                + max(
                    0,
                    len(pair) - 1
                ) * tile_gap
            )

            left = (
                cx - total / 2
            )


            for j, c in enumerate(
                pair
            ):

                tcx = (
                    left
                    + tile_size / 2
                    + j * (
                        tile_size
                        + tile_gap
                    )
                )


                avatar_tile(
                    img,
                    draw,
                    tcx,
                    y + 211,
                    tile_size,
                    c.get(
                        "icon",
                        str(
                            c.get(
                                "id",
                                ""
                            )
                        )
                    ),
                    el
                )


                name = c.get(
                    "en",
                    str(
                        c.get(
                            "id",
                            ""
                        )
                    )
                )

                name_lines = wrap_text(
                    draw,
                    name,
                    F_MICRO,
                    tile_size + 30
                )


                for k, s in enumerate(
                    name_lines[:2]
                ):

                    centered(
                        draw,
                        tcx,
                        y + 260 + k * 16,
                        s,
                        F_MICRO,
                        WHITE
                    )


            if len(pair) != 2:

                centered(
                    draw,
                    cx,
                    y + starter_h - 24,
                    f"{len(pair)} / 2 AVAILABLE",
                    F_MICRO,
                    MUTED
                )


        y += starter_h


    # ============================================================
    # GUEST CAST
    # ============================================================

    if invite_ids:

        y += SECTION_GAP

        box = [
            MARGIN,
            y,
            W - MARGIN,
            y + cast_h
        ]

        technical_panel(
            draw,
            box
        )

        section_header(
            draw,
            y + 18,
            "Guest Cast",
            "ROSTER / %02d" % len(invite_ids)
        )


        n = len(invite_ids)

        cell_w = CONTENT_W / n

        tile_size = 126


        for i, cid in enumerate(
            invite_ids
        ):

            c = char(cid)

            cx = (
                MARGIN
                + cell_w * i
                + cell_w / 2
            )

            element = c.get(
                "element"
            )


            avatar_tile(
                img,
                draw,
                cx,
                y + 119,
                tile_size,
                c.get(
                    "icon",
                    str(cid)
                ),
                element
            )


            name = c.get(
                "en",
                str(cid)
            )

            lines = wrap_text(
                draw,
                name,
                F_NAME,
                cell_w - 20
            )


            for j, s in enumerate(
                lines[:2]
            ):

                centered(
                    draw,
                    cx,
                    y + 190 + j * 20,
                    s,
                    F_NAME,
                    WHITE
                )


            if element:

                centered(
                    draw,
                    cx,
                    y + 229,
                    element.upper(),
                    F_TAG,
                    ELEMENT_COLORS.get(
                        element,
                        FAINT
                    )
                )


        y += cast_h


    # ============================================================
    # STAR CHALLENGES
    # ============================================================

    if star_rooms:

        y += SECTION_GAP

        section_header(
            draw,
            y,
            "Star Challenges",
            f"COMBAT / {len(star_rooms):02d}"
        )

        y += 54


        n = len(star_rooms)

        gap = 16

        cols = min(
            4,
            max(1, n)
        )

        card_w = (
            CONTENT_W
            - gap * (cols - 1)
        ) / cols

        card_h = star_h


        for i, (
            rk,
            r
        ) in enumerate(
            star_rooms
        ):

            x = (
                MARGIN
                + i * (
                    card_w + gap
                )
            )


            draw.rectangle(
                [
                    x,
                    y,
                    x + card_w,
                    y + card_h
                ],
                fill=(11, 14, 18, 255)
            )


            corner_frame(
                draw,
                [
                    x,
                    y,
                    x + card_w,
                    y + card_h
                ],
                PANEL_LINE,
                cut=13,
                width=1
            )


            # Room number

            draw.rectangle(
                [
                    x + 14,
                    y + 14,
                    x + 52,
                    y + 48
                ],
                outline=GOLD_DIM,
                width=1
            )

            centered(
                draw,
                x + 33,
                y + 19,
                str(rk),
                F_LABEL,
                GOLD
            )


            txt(
                draw,
                x + card_w - 82,
                y + 20,
                f"LV.{r.get('monster_level', '?')}",
                F_TAG,
                FAINT
            )


            mons = r.get(
                "monster_preview_list",
                []
            ) or []


            if mons:

                monster_badge(
                    img,
                    draw,
                    x + card_w / 2,
                    y + 122,
                    116,
                    mons[0],
                    GOLD
                )


            if len(mons) > 1:

                for j, mon in enumerate(
                    mons[1:4]
                ):

                    side = (
                        -1
                        if j % 2 == 0
                        else 1
                    )

                    yy = (
                        y
                        + 92
                        + (j // 2) * 54
                    )

                    xx = (
                        x
                        + card_w / 2
                        + side * 76
                    )


                    monster_badge(
                        img,
                        draw,
                        xx,
                        yy,
                        40,
                        mon,
                        GOLD_DIM
                    )


            title = r.get(
                "title",
                ""
            )

            title_lines = wrap_text(
                draw,
                strip_color_tags(title),
                F_NAME,
                card_w - 34
            )

            ty = y + 184


            for j, s in enumerate(
                title_lines[:3]
            ):

                centered(
                    draw,
                    x + card_w / 2,
                    ty + j * 21,
                    s,
                    F_NAME,
                    WHITE
                )


            line_y = (
                y + card_h - 46
            )

            line(
                draw,
                x + 18,
                line_y,
                x + card_w - 18,
                line_y,
                PANEL_LINE_SOFT,
                1
            )


            centered(
                draw,
                x + card_w / 2,
                line_y + 14,
                "DEFEAT TARGET",
                F_MICRO,
                MUTED
            )


        y += card_h


    # ============================================================
    # ENCORE CHALLENGES
    # ============================================================

    if encore_rooms:

        y += SECTION_GAP

        section_header(
            draw,
            y,
            "Encore Challenges",
            f"VISIONARY / {len(encore_rooms):02d}",
            ENCORE
        )

        y += 54


        n = len(encore_rooms)

        gap = 18

        cols = min(
            2,
            n
        )

        card_w = (
            CONTENT_W
            - gap * (cols - 1)
        ) / cols

        card_h = encore_h


        for i, (
            rk,
            r
        ) in enumerate(
            encore_rooms
        ):

            x = (
                MARGIN
                + i * (
                    card_w + gap
                )
            )


            draw.rectangle(
                [
                    x,
                    y,
                    x + card_w,
                    y + card_h
                ],
                fill=(12, 13, 17, 255)
            )


            corner_frame(
                draw,
                [
                    x,
                    y,
                    x + card_w,
                    y + card_h
                ],
                ENCORE_DIM,
                cut=18,
                width=1
            )


            # Red status rail

            draw.rectangle(
                [
                    x,
                    y + 20,
                    x + 3,
                    y + card_h - 20
                ],
                fill=ENCORE
            )


            txt(
                draw,
                x + 22,
                y + 22,
                f"ENCORE // {rk}",
                F_KICKER,
                ENCORE
            )


            txt(
                draw,
                x + card_w - 90,
                y + 24,
                f"LV.{r.get('monster_level', '?')}",
                F_TAG,
                FAINT
            )


            mons = r.get(
                "monster_preview_list",
                []
            ) or []


            if mons:

                monster_badge(
                    img,
                    draw,
                    x + 100,
                    y + 126,
                    118,
                    mons[0],
                    ENCORE
                )


            title_lines = wrap_text(
                draw,
                strip_color_tags(
                    r.get(
                        "title",
                        ""
                    )
                ),
                F_NAME,
                card_w - 170
            )


            tx = x + 180

            ty = y + 92


            for j, s in enumerate(
                title_lines[:4]
            ):

                txt(
                    draw,
                    tx,
                    ty + j * 23,
                    s,
                    F_NAME,
                    WHITE
                )


            line(
                draw,
                tx,
                y + 184,
                x + card_w - 24,
                y + 184,
                ENCORE_DIM,
                1
            )


            txt(
                draw,
                tx,
                y + 201,
                "VISIONARY MODE",
                F_MICRO,
                ENCORE
            )

            txt(
                draw,
                tx,
                y + 222,
                "DEFEAT TARGET",
                F_TAG,
                MUTED
            )


        y += card_h


    # ============================================================
    # FOOTER
    # ============================================================

    y += SECTION_GAP + 8

    line(
        draw,
        MARGIN,
        y,
        W - MARGIN,
        y,
        PANEL_LINE,
        1
    )

    y += 18


    txt(
        draw,
        MARGIN,
        y,
        "IMAGINARIUM // THEATER",
        F_MICRO,
        GOLD_SOFT
    )


    centered(
        draw,
        W / 2,
        y,
        f" PROVIDED BY {BOT_USERNAME}",
        F_MICRO,
        GOLD
    )


    txt(
        draw,
        MARGIN,
        y + 22,
        f" PROVIDED BY {BOT_USERNAME}",
        F_MICRO,
        MUTED
    )


    right = "THE STAGE IS SET."

    bbox = draw.textbbox(
        (0, 0),
        right,
        font=F_MICRO
    )

    txt(
        draw,
        W - MARGIN
        - (bbox[2] - bbox[0]),
        y,
        right,
        F_MICRO,
        GOLD_SOFT
    )


    return img.crop(
        (
            0,
            0,
            W,
            int(y + 34)
        )
    ).convert("RGB")


# ------------------------------------------------------------------ CLI

def main():

    ap = argparse.ArgumentParser(
        description=(
            "Generate an Imaginarium "
            "Theater card"
        )
    )


    ap.add_argument(
        "num",
        type=int,
        help="Act number, e.g. 30 or 31"
    )


    ap.add_argument(
        "--difficulty",
        default="5",
        choices=[
            "1",
            "2",
            "3",
            "4",
            "5"
        ],
        help=(
            "Difficulty tier "
            "(default: 5)"
        )
    )


    ap.add_argument(
        "--no-update",
        action="store_true",
        help=(
            "Skip downloading data "
            "and use cached files"
        )
    )


    args = ap.parse_args()


    # ------------------------------------------------------------
    # UPDATE DATA
    # ------------------------------------------------------------

    if not args.no_update:

        fetch_rolecombat(args.num)
        update_core_data()

        # NEW:
        # Download global schedule
        fetch_rolecombat_schedule()

    else:

        if not (
            endgame_data_db.exists(
                MONSTER_CACHE
            )
            and
            endgame_data_db.exists(
                CHARACTER_CACHE
            )
        ):
            raise SystemExit(
                "No cached monster/character "
                "data yet. Run without "
                "--no-update first."
            )


        if not endgame_data_db.exists(
            os.path.join(
                CACHE_DIR,
                f"rolecombat_{args.num}.json"
            )
        ):
            raise SystemExit(
                f"No cached data for act "
                f"{args.num} yet. Run "
                f"without --no-update first."
            )


        # NEW:
        # Schedule file is also required
        if not endgame_data_db.exists(
            ROLECOMBAT_SCHEDULE_CACHE
        ):
            raise SystemExit(
                "No cached rolecombat.json "
                "schedule exists. Run "
                "without --no-update first."
            )


    # ------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------

    card = build_card(
        args.num,
        args.difficulty
    )


    out_path = os.path.join(
        OUTPUT_DIR,
        f"theater_act"
        f"{args.num}"
        f"_d"
        f"{args.difficulty}.png"
    )


    card.save(out_path)


    print(
        f"[done] wrote {out_path} "
        f"({card.width}x{card.height})"
    )


# ------------------------------------------------------------------ RUN

if __name__ == "__main__":
    main()