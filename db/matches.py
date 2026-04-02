from datetime import datetime, timezone
import pytz
import config

tz = pytz.timezone(config.TIMEZONE)


async def get_all_matches(db) -> list:
    """Retorna todos los partidos ordenados por fecha."""
    cursor = db.matches.find({}).sort("kickoff_utc", 1)
    return await cursor.to_list(length=None)


async def get_matches_today(db) -> list:
    """Retorna los partidos del día de hoy en hora Argentina."""
    now_arg = datetime.now(tz)
    start = now_arg.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc)
    end = now_arg.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(pytz.utc)

    cursor = db.matches.find({
        "kickoff_utc": {"$gte": start, "$lte": end}
    }).sort("kickoff_utc", 1)
    return await cursor.to_list(length=None)


async def get_matches_by_team(db, team: str) -> list:
    """Retorna partidos donde juega un equipo (búsqueda parcial, case-insensitive)."""
    import re
    pattern = re.compile(team, re.IGNORECASE)
    cursor = db.matches.find({
        "$or": [
            {"home_team": {"$regex": pattern}},
            {"away_team": {"$regex": pattern}},
        ]
    }).sort("kickoff_utc", 1)
    return await cursor.to_list(length=None)


async def get_matches_by_group(db, group_name: str) -> list:
    """Retorna partidos de un grupo específico."""
    cursor = db.matches.find(
        {"group_name": group_name.upper()}
    ).sort("kickoff_utc", 1)
    return await cursor.to_list(length=None)


async def get_live_matches(db) -> list:
    """Retorna partidos actualmente en curso."""
    cursor = db.matches.find({"status": "live"})
    return await cursor.to_list(length=None)


async def get_match_by_id(db, match_id: str):
    """Retorna un partido por su ID."""
    return await db.matches.find_one({"match_id": match_id})


async def get_upcoming_matches(db, minutes_ahead: int = 70) -> list:
    """
    Retorna partidos que arrancan en los próximos X minutos.
    Útil para reminders y cierre de pronósticos.
    """
    from datetime import timedelta
    now = datetime.now(pytz.utc)
    future = now + timedelta(minutes=minutes_ahead)

    cursor = db.matches.find({
        "kickoff_utc": {"$gte": now, "$lte": future},
        "status": "scheduled",
    })
    return await cursor.to_list(length=None)


async def upsert_match(db, match_data: dict):
    """
    Inserta o actualiza un partido.
    Usa match_id como clave única.
    """
    await db.matches.update_one(
        {"match_id": match_data["match_id"]},
        {"$set": match_data},
        upsert=True,
    )


async def update_match_result(db, match_id: str, home_score: int, away_score: int, status: str):
    """Actualiza el resultado y estado de un partido."""
    await db.matches.update_one(
        {"match_id": match_id},
        {"$set": {
            "score.home": home_score,
            "score.away": away_score,
            "status": status,
            "last_updated": datetime.now(pytz.utc),
        }}
    )


async def get_team_recent_form(db, team: str, limit: int = 3) -> list:
    """
    Retorna los últimos N resultados de un equipo en el torneo.
    Solo partidos finalizados.
    """
    cursor = db.matches.find({
        "$or": [
            {"home_team": team},
            {"away_team": team},
        ],
        "status": "finished",
    }).sort("kickoff_utc", -1).limit(limit)

    matches = await cursor.to_list(length=None)

    form = []
    for match in reversed(matches):
        home = match["score"]["home"]
        away = match["score"]["away"]
        if home is None or away is None:
            continue

        is_home = match["home_team"] == team
        if is_home:
            if home > away:
                form.append("🟢")
            elif home < away:
                form.append("🔴")
            else:
                form.append("⚪")
        else:
            if away > home:
                form.append("🟢")
            elif away < home:
                form.append("🔴")
            else:
                form.append("⚪")

    return form