"""
Render de la tabla de posiciones como imagen PNG (alineacion pixel-perfect).

Genera un 'card' con tema oscuro estilo Discord, con bandera PNG y nombre de
cada equipo. Se usa en /tabla; si falla, el comando cae al embed de texto.
"""

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from utils.embeds import get_flag_code

BASE_DIR = Path(__file__).resolve().parent.parent

FONT_REGULAR  = BASE_DIR / "assets" / "fonts" / "Inter_24pt-Regular.ttf"
FONT_SEMIBOLD = BASE_DIR / "assets" / "fonts" / "Inter_24pt-SemiBold.ttf"
FONT_BOLD     = BASE_DIR / "assets" / "fonts" / "Inter_24pt-Bold.ttf"

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
_FLAG_BOX_W  = 40   # ancho reservado para la bandera PNG
_FLAG_BOX_H  = 30   # alto de la bandera, proporcional a 64x48
_NAME_RESERVE= 250
_TITLE_H     = 74
_HEADER_H    = 42
_FOOTER_H    = 46


def _font(size: int, weight: int = 400):
    """Carga Inter Regular, SemiBold o Bold según el peso pedido."""
    if weight >= 700:
        path = FONT_BOLD
    elif weight >= 600:
        path = FONT_SEMIBOLD
    else:
        path = FONT_REGULAR
    try:
        return ImageFont.truetype(str(path), size)
    except Exception as e:
        print(f"No se pudo cargar {path}: {e}")
        return ImageFont.load_default()


@lru_cache(maxsize=64)
def _get_flag_image(team_name: str) -> Image.Image | None:
    """Carga (y cachea) la bandera PNG usando el código de Flagpedia."""
    try:
        code = get_flag_code(team_name)
        if not code:
            print(f"Sin código de bandera para '{team_name}'")
            return None
        path = BASE_DIR / "assets" / "flags" / f"{code}.png"
        if path.exists():
            img = Image.open(path).convert("RGBA")
            return img.resize((_FLAG_BOX_W, _FLAG_BOX_H), Image.Resampling.LANCZOS)
        else:
            print(f"No existe el archivo de bandera: {path}")
    except Exception as e:
        print(f"No se pudo cargar bandera {team_name}: {e}")
    return None


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

    f_title  = _font(30, weight=700)
    f_head   = _font(20, weight=700)
    f_row    = _font(22, weight=400)
    f_row_b  = _font(22, weight=700)
    f_foot   = _font(18, weight=400)

    # x derecho de cada columna numerica (alineacion a derecha)
    col_right = {}
    base = width - _PAD
    for i, col in enumerate(reversed(_NUM_COLS)):
        col_right[col] = base - i * _COL_W

    name_x     = _TEAM_X + _FLAG_BOX_W + 8
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

        # Bandera PNG
        team_name = team.get("team", "")
        flag_img = _get_flag_image(team_name)
        if flag_img:
            flag_y = row_top + (_ROW_H - _FLAG_BOX_H) // 2
            img.paste(flag_img, (_TEAM_X, flag_y), flag_img)

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