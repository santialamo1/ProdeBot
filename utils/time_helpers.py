from datetime import datetime, timezone
import pytz
import config

tz = pytz.timezone(config.TIMEZONE)


def utc_to_local(dt: datetime) -> datetime:
    """Convierte un datetime UTC a hora Argentina."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)
    return dt.astimezone(tz)


def format_match_time(dt: datetime) -> str:
    """Formatea la hora del partido en hora Argentina. Ej: '18:00 ART'"""
    local = utc_to_local(dt)
    return local.strftime("%H:%M ART")


def format_match_date(dt: datetime) -> str:
    """Formatea la fecha del partido. Ej: 'Lunes 14 de Junio'"""
    local = utc_to_local(dt)
    days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    months = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]
    day_name = days[local.weekday()]
    month_name = months[local.month - 1]
    return f"{day_name} {local.day} de {month_name}"


def format_match_datetime(dt: datetime) -> str:
    """Formatea fecha y hora completa. Ej: 'Lunes 14/06 - 18:00 ART'"""
    local = utc_to_local(dt)
    return local.strftime("%a %d/%m - %H:%M ART")


def is_today(dt: datetime) -> bool:
    """Verifica si un datetime UTC corresponde al día de hoy en Argentina."""
    local = utc_to_local(dt)
    now_local = datetime.now(tz)
    return local.date() == now_local.date()


def minutes_until(dt: datetime) -> float:
    """Retorna los minutos que faltan hasta un datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)
    now = datetime.now(pytz.utc)
    delta = dt - now
    return delta.total_seconds() / 60


def now_utc() -> datetime:
    """Retorna el datetime actual en UTC."""
    return datetime.now(pytz.utc)


def now_local() -> datetime:
    """Retorna el datetime actual en hora Argentina."""
    return datetime.now(tz)


def to_discord_timestamp(dt: datetime, format: str = "F") -> str:
    """
    Convierte un datetime a timestamp de Discord (Hammertime).
    Cada usuario lo ve en su propia timezone automáticamente.

    Formatos:
      t = hora corta          → 4:00 PM
      T = hora larga          → 4:00:00 PM
      d = fecha corta         → 11/06/2026
      D = fecha larga         → 11 de junio de 2026
      f = fecha + hora corta  → 11 de junio de 2026 4:00 PM
      F = fecha + hora larga  → jueves, 11 de junio de 2026 4:00 PM
      R = relativo            → en 2 meses
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)
    unix = int(dt.timestamp())
    return f"<t:{unix}:{format}>"


def to_discord_timestamp_tr(dt: datetime) -> str:
    """Shortcut para hora corta + relativo. Ej: '4:00 PM · en 2 horas'"""
    return f"{to_discord_timestamp(dt, 't')} · {to_discord_timestamp(dt, 'R')}"