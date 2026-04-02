import discord
import logging
from datetime import datetime, timedelta
import pytz

import config
from db.matches import get_matches_today, get_upcoming_matches
from utils.embeds import build_daily_matches_embed, build_match_embed
from utils.time_helpers import format_match_date, now_utc

log = logging.getLogger("worldcup-bot.daily")

# Set para trackear reminders ya enviados (en memoria, se resetea al reiniciar)
_reminders_sent = set()


async def post_partidos_hoy(bot):
    """
    Postea en #partidos-de-hoy los partidos del día actual.
    Se ejecuta todos los días a las 9AM hora Argentina.
    """
    channel = bot.get_channel(config.CHANNEL_PARTIDOS_HOY)
    if not channel:
        log.error(f"Canal #partidos-de-hoy no encontrado (ID: {config.CHANNEL_PARTIDOS_HOY})")
        return

    matches = await get_matches_today(bot.db)
    date_str = format_match_date(datetime.now(pytz.timezone(config.TIMEZONE)))

    embed = build_daily_matches_embed(matches, date_str)
    await channel.send(embed=embed)

    log.info(f"Post diario enviado: {len(matches)} partidos para {date_str}")

    # Si hay partidos hoy, también crear los embeds de pronósticos
    if matches:
        await _setup_prediction_embeds(bot, matches)


async def _setup_prediction_embeds(bot, matches: list):
    """
    Para cada partido del día, crea o edita el embed en #pronosticos.
    """
    from utils.embeds import build_predictions_embed

    channel = bot.get_channel(config.CHANNEL_PRONOSTICOS)
    if not channel:
        return

    for match in matches:
        # Verificar si ya existe un mensaje para este partido
        existing = await bot.db.prediction_messages.find_one({"match_id": match["match_id"]})

        embed = build_predictions_embed(match, [], bot.guilds[0] if bot.guilds else None)

        if existing:
            try:
                msg = await channel.fetch_message(existing["message_id"])
                await msg.edit(embed=embed)
            except (discord.NotFound, discord.HTTPException):
                msg = await channel.send(embed=embed)
                await bot.db.prediction_messages.update_one(
                    {"match_id": match["match_id"]},
                    {"$set": {"message_id": msg.id}}
                )
        else:
            msg = await channel.send(embed=embed)
            await bot.db.prediction_messages.insert_one({
                "match_id": match["match_id"],
                "message_id": msg.id,
            })


async def send_reminders(bot):
    """
    Verifica si hay partidos que empiezan en ~60 minutos y envía reminder.
    Corre cada minuto pero solo actúa cuando toca.
    """
    channel = bot.get_channel(config.CHANNEL_PARTIDOS_HOY)
    if not channel:
        return

    # Partidos en la ventana de 59 a 61 minutos
    now = now_utc()
    window_start = now + timedelta(minutes=59)
    window_end = now + timedelta(minutes=61)

    cursor = bot.db.matches.find({
        "kickoff_utc": {"$gte": window_start, "$lte": window_end},
        "status": "scheduled",
    })
    matches = await cursor.to_list(length=None)

    for match in matches:
        match_id = match["match_id"]
        reminder_key = f"reminder_{match_id}"

        if reminder_key in _reminders_sent:
            continue

        _reminders_sent.add(reminder_key)

        home = match.get("home_team", "TBD")
        away = match.get("away_team", "TBD")

        from utils.embeds import get_flag
        home_flag = get_flag(home)
        away_flag = get_flag(away)

        embed = discord.Embed(
            title="⏰ ¡Partido en 1 hora!",
            description=f"## {home_flag} {home}  vs  {away} {away_flag}\n\n"
                        f"¡Hacé tu pronóstico antes de que cierren! Usá `/pronostico` en #mundial-chat",
            color=0xFF6B35,
        )
        embed.set_footer(text="Los pronósticos cierran 10 minutos antes del partido · Mundial 2026")

        await channel.send(embed=embed)
        log.info(f"Reminder enviado: {home} vs {away}")


async def close_predictions_for_match(bot, match: dict):
    """
    Marca los pronósticos como cerrados para un partido que está por empezar.
    Edita el embed de #pronosticos indicando el cierre.
    """
    from utils.embeds import build_predictions_embed, COLOR_DANGER
    from db.predictions import get_predictions_for_match

    channel = bot.get_channel(config.CHANNEL_PRONOSTICOS)
    if not channel:
        return

    existing = await bot.db.prediction_messages.find_one({"match_id": match["match_id"]})
    if not existing:
        return

    predictions = await get_predictions_for_match(bot.db, match["match_id"])

    # Añadir username a cada predicción
    for pred in predictions:
        user_id = int(pred["user_id"])
        member = bot.guilds[0].get_member(user_id) if bot.guilds else None
        pred["username"] = member.display_name if member else pred["user_id"]

    embed = build_predictions_embed(match, predictions, bot.guilds[0] if bot.guilds else None)
    embed.color = COLOR_DANGER
    embed.set_footer(text="🔒 Pronósticos cerrados · Mundial 2026")

    # Agregar campo de cierre
    embed.add_field(name="🔒 Estado", value="Los pronósticos están cerrados. ¡El partido está por comenzar!", inline=False)

    try:
        msg = await channel.fetch_message(existing["message_id"])
        await msg.edit(embed=embed)
        log.info(f"Pronósticos cerrados para: {match.get('home_team')} vs {match.get('away_team')}")
    except (discord.NotFound, discord.HTTPException) as e:
        log.error(f"No se pudo editar el mensaje de pronósticos: {e}")