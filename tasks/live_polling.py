import logging
from datetime import datetime, timedelta
import pytz

import config
from tasks.sync_fixture import fetch_live_scores, parse_match
from db.matches import upsert_match, get_upcoming_matches
from utils.time_helpers import now_utc

log = logging.getLogger("worldcup-bot.live")

# Sets para trackear estados en memoria
_prediction_close_sent = set()   # Partidos con pronósticos ya cerrados
_result_processed = set()         # Partidos con resultado ya procesado


async def check_live_matches(bot):
    """
    Tarea que corre cada 2 minutos.
    1. Cierra pronósticos si faltan ≤10 min para el partido
    2. Hace polling de scores si hay partidos en vivo
    3. Procesa resultados cuando un partido termina
    """
    # ── Cierre de pronósticos ──────────────────────────────────
    await _handle_prediction_closing(bot)

    # ── Polling de partidos en vivo ────────────────────────────
    live_in_db = await bot.db.matches.count_documents({"status": "live"})

    # También verificar si hay partidos que deberían estar en vivo
    # (empezaron hace menos de 120 minutos)
    now = now_utc()
    recently_started = await bot.db.matches.count_documents({
        "kickoff_utc": {"$lte": now, "$gte": now - timedelta(minutes=120)},
        "status": "scheduled",
    })

    if live_in_db == 0 and recently_started == 0:
        return  # No hay nada en vivo ni próximo a estarlo

    log.debug("Hay partidos en vivo o recién iniciados, consultando API...")

    try:
        raw_live = await fetch_live_scores()
    except Exception as e:
        log.error(f"Error al obtener scores en vivo: {e}")
        return

    # Actualizar los que están en vivo
    live_ids = set()
    for raw in raw_live:
        match_data = parse_match(raw)
        if match_data["match_id"]:
            live_ids.add(match_data["match_id"])
            await upsert_match(bot.db, match_data)

    # ── Detectar partidos que terminaron ──────────────────────
    # Buscar partidos que estaban "live" en DB pero ya no están en la respuesta
    cursor = bot.db.matches.find({"status": "live"})
    live_in_db_list = await cursor.to_list(length=None)

    for match in live_in_db_list:
        match_id = match["match_id"]
        if match_id not in live_ids and match_id not in _result_processed:
            # El partido desapareció del live feed → probablemente terminó
            await _process_finished_match(bot, match_id)


async def _handle_prediction_closing(bot):
    """Cierra los pronósticos para partidos que empiezan en ≤10 minutos."""
    from tasks.daily_post import close_predictions_for_match

    now = now_utc()
    window_end = now + timedelta(minutes=config.PREDICTION_CLOSE_MINUTES + 1)

    cursor = bot.db.matches.find({
        "kickoff_utc": {"$lte": window_end, "$gte": now},
        "status": "scheduled",
    })
    matches = await cursor.to_list(length=None)

    for match in matches:
        close_key = f"close_{match['match_id']}"
        if close_key not in _prediction_close_sent:
            _prediction_close_sent.add(close_key)
            await close_predictions_for_match(bot, match)


async def _process_finished_match(bot, match_id: str):
    """
    Procesa el resultado final de un partido:
    1. Actualiza el estado en MongoDB
    2. Calcula puntos para cada pronóstico
    3. Postea el resultado en #resultados
    """
    from db.predictions import get_predictions_for_match, set_prediction_points
    from db.users import update_streak, add_points, ensure_user
    from utils.points import calculate_points
    from utils.embeds import build_result_embed

    _result_processed.add(match_id)

    # Marcar como finished en DB
    await bot.db.matches.update_one(
        {"match_id": match_id},
        {"$set": {"status": "finished"}}
    )

    match = await bot.db.matches.find_one({"match_id": match_id})
    if not match:
        return

    score = match.get("score", {})
    actual_home = score.get("home")
    actual_away = score.get("away")

    if actual_home is None or actual_away is None:
        log.warning(f"Partido {match_id} marcado como finished pero sin score")
        return

    log.info(f"Procesando resultado: {match.get('home_team')} {actual_home}-{actual_away} {match.get('away_team')}")

    predictions = await get_predictions_for_match(bot.db, match_id)
    points_map = {}

    guild = bot.guilds[0] if bot.guilds else None

    for pred in predictions:
        user_id = int(pred["user_id"])

        # Asegurar que el usuario existe en la DB
        member = guild.get_member(user_id) if guild else None
        username = member.display_name if member else str(user_id)
        await ensure_user(bot.db, user_id, username)

        # Obtener racha actual antes de calcular
        user = await bot.db.users.find_one({"user_id": str(user_id)})
        current_streak = user.get("streak", 0) if user else 0

        # Calcular puntos
        points, description = calculate_points(
            predicted_home=pred["predicted_home"],
            predicted_away=pred["predicted_away"],
            actual_home=actual_home,
            actual_away=actual_away,
            stage=match.get("round", "group"),
            streak=current_streak,
        )

        correct = points > 0

        # Actualizar racha y puntos
        new_streak = await update_streak(bot.db, user_id, correct)
        if points > 0:
            await add_points(bot.db, user_id, points)

        await set_prediction_points(bot.db, user_id, match_id, points)
        points_map[str(user_id)] = points
        pred["username"] = username

        log.info(f"  {username}: {pred['predicted_home']}-{pred['predicted_away']} → {points}pts ({description})")

    # Postear en #resultados
    channel = bot.get_channel(config.CHANNEL_RESULTADOS)
    if channel:
        embed = build_result_embed(match, predictions, points_map)
        await channel.send(embed=embed)

    # Actualizar embed del leaderboard en #estadisticas
    await _update_stats_embed(bot)

    log.info(f"Resultado procesado para partido {match_id}")


async def _update_stats_embed(bot):
    """Edita el embed fijo del canal #estadisticas con el ranking actualizado."""
    from db.users import get_leaderboard
    from utils.embeds import build_leaderboard_embed

    channel = bot.get_channel(config.CHANNEL_ESTADISTICAS)
    if not channel:
        return

    users = await get_leaderboard(bot.db, limit=15)
    embed = build_leaderboard_embed(users)

    # Buscar el mensaje fijo del leaderboard
    existing = await bot.db.bot_messages.find_one({"type": "leaderboard"})

    if existing:
        try:
            msg = await channel.fetch_message(existing["message_id"])
            await msg.edit(embed=embed)
            return
        except Exception:
            pass

    # Si no existe, crearlo
    msg = await channel.send(embed=embed)
    await bot.db.bot_messages.update_one(
        {"type": "leaderboard"},
        {"$set": {"type": "leaderboard", "message_id": msg.id}},
        upsert=True,
    )