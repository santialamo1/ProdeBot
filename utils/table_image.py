"""Render de la tabla de posiciones como imagen PNG (alineacion pixel-perfect).

Genera un 'card' con tema oscuro estilo Discord, con bandera y nombre de
cada equipo. Se usa en /tabla; si falla, el comando cae al embed de texto.
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from utils.embeds import FLAG_EMOJIS

BASE_DIR = Path(__file__).resolve().parent.parent
FONT_PATH = BASE_DIR / "assets" / "fonts" / "InterVariable.ttf"

# Paleta (estilo Discord dark)
_BG        = (43, 45, 49)       # #2B2D31  fondo del card
_HEADER_BG = (32, 34, 37)       # #202225  franja del encabezado
_TEXT      = (255, 255, 255)
_MUTED     = (181, 186, 193)    # #B5BAC1  labels/numeros
_LINE      = (63, 65, 71)       # #3F4147  separadores
_QUALIFY   = (87, 242, 135)     # #57F287  verde Discord (clasificados)
_QUALIFY_BG= (40, 56, 47)       # fondo suave para filas que clasifican
_ACCENT    = (88, 101, 242)     # #5865F2  blurple (titulo)

# Columnas numericas
_NUM_COLS = ["PJ", "G", "E", "P", "GF", "GA", "DG", "Pts"]
_NUM_KEYS = {
    "PJ": "played", "G": "won", "E": "drawn", "P": "lost",
    "GF": "goals_for", "GA": "goals_against", "DG": "goal_difference",
    "Pts": "points",
}

# Geometria
_PAD         = 28
_ROW_H       = 46
_COL_W       = 48
_TEAM_X      = 80
_FLAG_BOX_W  = 52   # ancho reservado para la bandera emoji
_NAME_RESERVE= 250
_TITLE_H     = 74
_HEADER_H    = 42
_FOOTER_H    = 46


def _font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        return ImageFont.load_default()


def _emoji_font(size: int):
    candidates = [
        BASE_DIR / "assets" / "fonts" / "NotoColorEmoji.ttf",

        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/noto/NotoColorEmoji.ttf",
        "C:/Windows/Fonts/seguiemj.ttf",
        "/Library/Fonts/Apple Color Emoji.ttc",
    ]

    for path in candidates:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue

    return _font(size)


def _get_flag_emoji(team_name: str) -> str:
    """Retorna el emoji de bandera para el equipo."""
    if not team_name:
        return "🏳"
    if team_name in FLAG_EMOJIS:
        return FLAG_EMOJIS[team_name]
    low = team_name.lower()
    for name, emoji in FLAG_EMOJIS.items():
        if name.lower() == low:
            return emoji
    return "🏳"


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    """Trunca con '…' si el texto no entra en max_w pixeles."""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def render_standings_image(standings: list, group_name: str) -> io.BytesIO:
    """Devuelve un BytesIO con el PNG de la tabla del grupo."""
    n = len(standings)
    width  = _TEAM_X + _NAME_RESERVE + _COL_W * len(_NUM_COLS) + _PAD
    height = _TITLE_H + _HEADER_H + _ROW_H * n + _FOOTER_H

    img  = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(img)

    f_title  = _font(30, bold=True)
    f_head   = _font(20, bold=True)
    f_row    = _font(22)
    f_row_b  = _font(22, bold=True)
    f_foot   = _font(18)
    f_emoji  = _emoji_font(22)

    # x derecho de cada columna numerica (alineacion a derecha)
    col_right = {}
    base = width - _PAD
    for i, col in enumerate(reversed(_NUM_COLS)):
        col_right[col] = base - i * _COL_W

    name_x     = _TEAM_X + _FLAG_BOX_W
    team_max_w = col_right["PJ"] - _COL_W + 8 - name_x

    # ── Titulo ────────────────────────────────────────────────
    draw.rectangle([0, 0, width, 6], fill=_ACCENT)
    draw.text((_PAD, _TITLE_H // 2 + 3),
              f"Tabla · Grupo {group_name.upper()}",
              font=f_title, fill=_TEXT, anchor="lm")

    # ── Encabezado de columnas ────────────────────────────────
    head_y = _TITLE_H
    draw.rectangle([0, head_y, width, head_y + _HEADER_H], fill=_HEADER_BG)
    hy = head_y + _HEADER_H // 2
    draw.text((_PAD, hy),    "#",       font=f_head, fill=_MUTED, anchor="lm")
    draw.text((_TEAM_X, hy), "EQUIPO",  font=f_head, fill=_MUTED, anchor="lm")
    for col in _NUM_COLS:
        draw.text((col_right[col], hy), col, font=f_head, fill=_MUTED, anchor="rm")

    # ── Filas ─────────────────────────────────────────────────
    y = head_y + _HEADER_H
    for i, team in enumerate(standings):
        qualifies = i < 2
        row_top   = y + i * _ROW_H
        cy        = row_top + _ROW_H // 2

        if qualifies:
            draw.rectangle([0, row_top, width, row_top + _ROW_H], fill=_QUALIFY_BG)
            draw.rectangle([0, row_top, 5, row_top + _ROW_H],     fill=_QUALIFY)

        name_color = _QUALIFY if qualifies else _TEXT
        pos_color  = _QUALIFY if qualifies else _MUTED

        draw.text((_PAD, cy), str(i + 1), font=f_row_b, fill=pos_color, anchor="lm")

        # Bandera como emoji
        flag_emoji = _get_flag_emoji(team.get("team", ""))
        try:
            draw.text((_TEAM_X, cy), flag_emoji, font=f_emoji, fill=_TEXT, anchor="lm")
        except Exception:
            pass  # si la fuente no soporta el emoji, se omite

        name = _fit(draw, team.get("team", "?"), f_row, team_max_w)
        draw.text((name_x, cy), name, font=f_row, fill=name_color, anchor="lm")

        for col in _NUM_COLS:
            val  = team.get(_NUM_KEYS[col], 0)
            if col == "DG" and isinstance(val, int) and val > 0:
                val = f"+{val}"
            font  = f_row_b if col == "Pts" else f_row
            color = _TEXT   if col == "Pts" else _MUTED
            draw.text((col_right[col], cy), str(val), font=font, fill=color, anchor="rm")

        # linea separadora (la del corte de clasificacion mas marcada)
        line_color = _QUALIFY if i == 1 else _LINE
        draw.line(
            [_PAD, row_top + _ROW_H, width - _PAD, row_top + _ROW_H],
            fill=line_color, width=1,
        )

    # ── Footer ────────────────────────────────────────────────
    fy = head_y + _HEADER_H + _ROW_H * n + _FOOTER_H // 2
    draw.rectangle([_PAD, fy - 9, _PAD + 16, fy + 7], fill=_QUALIFY)
    draw.text(
        (_PAD + 24, fy),
        "Clasifican a la siguiente ronda · Mundial 2026",
        font=f_foot, fill=_MUTED, anchor="lm",
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
