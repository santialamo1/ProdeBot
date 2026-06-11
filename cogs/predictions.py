import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime

import config
from db.predictions import (
    get_prediction, upsert_prediction, get_user_predictions,
    get_quiniela, save_quiniela, get_user_quiniela,
    get_predictions_for_match,
)
from db.users import ensure_user, set_champion_pick, get_user
from db.matches import get_matches_by_team, get_matches_today, get_matches_by_group
from utils.time_helpers import minutes_until, format_match_datetime
from utils.embeds import get_flag, build_predictions_embed
from utils.name_normalizer import normalize_team_name

log = logging.getLogger("worldcup-bot.predictions")

GROUPS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]


def only_in_chat():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.channel_id != config.CHANNEL_CHAT:
            await interaction.response.send_message(
                f"⚽ Los comandos solo se pueden usar en <#{config.CHANNEL_CHAT}>",
                ephemeral=True,
            )
            return False
        return True
    return app_commands.check(predicate)


class Predictions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ──────────────────────────────────────────────────────────
    #   /pronostico
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="pronostico", description="Pronosticá el resultado de un partido de hoy")
    @app_commands.describe(
        equipo="Nombre de uno de los equipos (ej: Argentina, Francia, Brasil)",
        goles_local="Goles del equipo local",
        goles_visitante="Goles del equipo visitante",
    )
    @only_in_chat()
    async def pronostico(
        self,
        interaction: discord.Interaction,
        equipo: str,
        goles_local: int,
        goles_visitante: int,
    ):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        username = interaction.user.display_name
        db = self.bot.db

        # Validar goles no negativos
        if goles_local < 0 or goles_visitante < 0:
            await interaction.followup.send("❌ Los goles no pueden ser negativos.", ephemeral=True)
            return

        # Normalizar nombre del equipo (español → inglés exacto de la API)
        equipo = normalize_team_name(equipo)

        # Buscar el partido
        matches = await get_matches_by_team(db, equipo)
        today_matches = await get_matches_today(db)
        today_ids = {m["match_id"] for m in today_matches}

        # Filtrar por partidos de hoy
        today_team_matches = [m for m in matches if m["match_id"] in today_ids]

        if not today_team_matches:
            await interaction.followup.send(
                f"❌ No encontré partidos de hoy para **{equipo}**. "
                f"Usá `/fixture hoy` para ver los partidos del día.",
                ephemeral=True,
            )
            return

        match = today_team_matches[0]
        match_id = match["match_id"]

        # Verificar que el partido no empezó (ventana de cierre)
        kickoff = match.get("kickoff_utc")
        if isinstance(kickoff, str):
            kickoff = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))

        mins_left = minutes_until(kickoff)

        if mins_left <= config.PREDICTION_CLOSE_MINUTES:
            await interaction.followup.send(
                f"🔒 Los pronósticos para **{match['home_team']} vs {match['away_team']}** están cerrados.\n"
                f"Los pronósticos cierran {config.PREDICTION_CLOSE_MINUTES} minutos antes del partido.",
                ephemeral=True,
            )
            return

        if match.get("status") in ("live", "finished"):
            await interaction.followup.send(
                "❌ Este partido ya está en curso o finalizó.",
                ephemeral=True,
            )
            return

        # Verificar si ya tiene un pronóstico
        existing = await get_prediction(db, user_id, match_id)
        is_update = existing is not None

        # Guardar en DB
        await ensure_user(db, user_id, username)
        await upsert_prediction(db, user_id, match_id, goles_local, goles_visitante)

        home = match["home_team"]
        away = match["away_team"]
        home_flag = get_flag(home)
        away_flag = get_flag(away)

        action = "actualizado" if is_update else "registrado"
        await interaction.followup.send(
            f"✅ Pronóstico {action}: {home_flag} **{home}** {goles_local} - {goles_visitante} **{away}** {away_flag}\n"
            f"⏰ Quedan {int(mins_left)} minutos para el partido.",
            ephemeral=True,
        )

        # Actualizar el embed en #pronosticos
        await self._update_prediction_embed(match)

    async def _update_prediction_embed(self, match: dict):
        """Actualiza el embed de pronósticos en el canal #pronosticos."""
        db = self.bot.db
        channel = self.bot.get_channel(config.CHANNEL_PRONOSTICOS)
        if not channel:
            return

        predictions = await get_predictions_for_match(db, match["match_id"])

        guild = channel.guild
        for pred in predictions:
            uid = int(pred["user_id"])
            member = guild.get_member(uid) if guild else None
            if not member and guild:
                try:
                    member = await guild.fetch_member(uid)
                except Exception as e:
                    log.warning(f"No se pudo fetchear miembro {uid}: {e}")
            pred["username"] = member.display_name if member else f"Usuario {uid}"

        embed = build_predictions_embed(match, predictions, guild)

        existing = await db.prediction_messages.find_one({"match_id": match["match_id"]})
        if existing:
            try:
                msg = await channel.fetch_message(existing["message_id"])
                await msg.edit(embed=embed)
            except (discord.NotFound, discord.HTTPException):
                msg = await channel.send(embed=embed)
                await db.prediction_messages.update_one(
                    {"match_id": match["match_id"]},
                    {"$set": {"message_id": msg.id}}
                )
        else:
            msg = await channel.send(embed=embed)
            await db.prediction_messages.insert_one({
                "match_id": match["match_id"],
                "message_id": msg.id,
            })

    # ──────────────────────────────────────────────────────────
    #   /mispronosticos
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="mispronosticos", description="Ver tu historial de pronósticos")
    @only_in_chat()
    async def mispronosticos(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        predictions = await get_user_predictions(self.bot.db, interaction.user.id)

        if not predictions:
            await interaction.followup.send(
                "📭 Todavía no hiciste ningún pronóstico. Usá `/pronostico` para empezar.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🎯 Tus pronósticos — {interaction.user.display_name}",
            color=0x1B4F72,
        )

        total_pts = 0
        correct = 0

        for pred in predictions[:20]:  # Últimos 20
            match = pred.get("match", {})
            home = match.get("home_team", "?")
            away = match.get("away_team", "?")
            home_flag = get_flag(home)
            away_flag = get_flag(away)

            ph = pred.get("predicted_home", "?")
            pa = pred.get("predicted_away", "?")
            pts = pred.get("points_earned")
            status = match.get("status", "scheduled")

            score = match.get("score", {})
            ah = score.get("home")
            aa = score.get("away")

            if status == "finished":
                result_str = f"{ah}-{aa}"
                if pts is not None and pts > 0:
                    status_icon = f"✅ +{pts}pts"
                    correct += 1
                    total_pts += pts
                elif pts == 0:
                    status_icon = "❌"
                else:
                    status_icon = "⏳"
            elif status == "live":
                result_str = f"{ah}-{aa} 🔴"
                status_icon = "⏳ En juego"
            else:
                result_str = "Pendiente"
                status_icon = "⏳"

            kickoff = match.get("kickoff_utc")
            if isinstance(kickoff, str):
                kickoff = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            date_str = format_match_datetime(kickoff) if kickoff else ""

            embed.add_field(
                name=f"{home_flag} {home} vs {away} {away_flag}",
                value=f"Tu pronóstico: **{ph}-{pa}** | Resultado: **{result_str}** | {status_icon}\n📅 {date_str}",
                inline=False,
            )

        user = await get_user(self.bot.db, interaction.user.id)
        streak = user.get("streak", 0) if user else 0
        total_user_pts = user.get("total_points", 0) if user else 0
        streak_str = f" | 🔥 Racha: {streak}" if streak >= 1 else ""

        embed.set_footer(text=f"Total: {total_user_pts}pts{streak_str} · Mundial 2026")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ──────────────────────────────────────────────────────────
    #   /campeon
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="campeon", description="Elegí el campeón del Mundial (solo se puede hacer una vez)")
    @app_commands.describe(equipo="El equipo que creés que va a ganar el Mundial")
    @only_in_chat()
    async def campeon(self, interaction: discord.Interaction, equipo: str):
        await interaction.response.defer()

        db = self.bot.db
        user_id = interaction.user.id
        username = interaction.user.display_name

        await ensure_user(db, user_id, username)
        user = await get_user(db, user_id)

        if user and user.get("champion_pick"):
            current = user["champion_pick"]
            flag = get_flag(current)
            await interaction.followup.send(
                f"⚠️ Ya elegiste a {flag} **{current}** como campeón. No se puede cambiar.",
                ephemeral=True,
            )
            return

        # Normalizar nombre del equipo (español → inglés exacto de la API)
        equipo = normalize_team_name(equipo)

        # Verificar que el equipo existe en el fixture
        matches = await get_matches_by_team(db, equipo)
        if not matches:
            await interaction.followup.send(
                f"❌ No encontré **{equipo}** en el fixture. "
                f"Revisá el nombre (ej: Argentina, Francia, Brasil, Alemania).",
                ephemeral=True,
            )
            return

        # Tomar el nombre exacto del primer partido encontrado
        first_match = matches[0]
        if equipo.lower() in first_match["home_team"].lower():
            team_name = first_match["home_team"]
        else:
            team_name = first_match["away_team"]

        await set_champion_pick(db, user_id, team_name)
        flag = get_flag(team_name)

        await interaction.followup.send(
            f"🏆 {interaction.user.mention} eligió a {flag} **{team_name}** como campeón del Mundial 2026!\n"
            f"Si acertás, ganás **{config.POINTS_CHAMPION} puntos bonus**. ¡Buena suerte!"
        )

    # ──────────────────────────────────────────────────────────
    #   /quiniela
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="quiniela", description="Pronosticá quiénes clasifican de un grupo (solo antes del torneo)")
    @app_commands.describe(
        grupo="Letra del grupo (A-L)",
        equipo1="Primer equipo que clasifica",
        equipo2="Segundo equipo que clasifica",
    )
    @only_in_chat()
    async def quiniela(
        self,
        interaction: discord.Interaction,
        grupo: str,
        equipo1: str,
        equipo2: str,
    ):
        await interaction.response.defer(ephemeral=True)

        grupo = grupo.upper()
        if grupo not in GROUPS:
            await interaction.followup.send(
                f"❌ Grupo inválido. Los grupos válidos son: {', '.join(GROUPS)}",
                ephemeral=True,
            )
            return

        db = self.bot.db
        user_id = interaction.user.id
        username = interaction.user.display_name

        # Verificar que el torneo no empezó
        first_match = await db.matches.find_one({}, sort=[("kickoff_utc", 1)])
        if first_match:
            from utils.time_helpers import minutes_until
            from datetime import datetime
            kickoff = first_match["kickoff_utc"]
            if isinstance(kickoff, str):
                kickoff = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            mins = minutes_until(kickoff)
            if mins <= 0:
                await interaction.followup.send(
                    "⏰ El torneo ya comenzó, no se puede modificar la quiniela.",
                    ephemeral=True,
                )
                return

        # Normalizar nombres (español → inglés exacto de la API)
        equipo1 = normalize_team_name(equipo1)
        equipo2 = normalize_team_name(equipo2)

        # Verificar que los equipos existen en ese grupo
        group_matches = await get_matches_by_group(db, grupo)
        group_teams = set()
        for m in group_matches:
            group_teams.add(m["home_team"].lower())
            group_teams.add(m["away_team"].lower())

        if equipo1.lower() not in group_teams:
            await interaction.followup.send(
                f"❌ **{equipo1}** no juega en el Grupo {grupo}.",
                ephemeral=True,
            )
            return

        if equipo2.lower() not in group_teams:
            await interaction.followup.send(
                f"❌ **{equipo2}** no juega en el Grupo {grupo}.",
                ephemeral=True,
            )
            return

        if equipo1.lower() == equipo2.lower():
            await interaction.followup.send(
                "❌ Los dos equipos deben ser diferentes.",
                ephemeral=True,
            )
            return

        # Verificar si ya tiene quiniela para ese grupo
        existing = await get_quiniela(db, user_id, grupo)

        await ensure_user(db, user_id, username)
        await save_quiniela(db, user_id, grupo, equipo1, equipo2)

        action = "actualizada" if existing else "guardada"
        flag1 = get_flag(equipo1)
        flag2 = get_flag(equipo2)

        await interaction.followup.send(
            f"✅ Quiniela {action} para el **Grupo {grupo}**:\n"
            f"Clasifican: {flag1} **{equipo1}** y {flag2} **{equipo2}**\n"
            f"💰 Ambos correctos: +{config.POINTS_QUINIELA_BOTH}pts | Uno correcto: +{config.POINTS_QUINIELA_ONE}pts",
            ephemeral=True,
        )

    @app_commands.command(name="miquiniela", description="Ver tus predicciones de la quiniela de grupos")
    @only_in_chat()
    async def miquiniela(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        quinielas = await get_user_quiniela(self.bot.db, interaction.user.id)

        if not quinielas:
            await interaction.followup.send(
                "📭 No hiciste predicciones de quiniela todavía. Usá `/quiniela` para predecir quiénes clasifican de cada grupo.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🎰 Tu quiniela — {interaction.user.display_name}",
            color=0x1B4F72,
        )

        total_pts = 0
        for q in quinielas:
            grupo = q["group_name"]
            t1 = q["team1"]
            t2 = q["team2"]
            pts = q.get("points_earned")
            resolved = q.get("resolved", False)

            flag1 = get_flag(t1)
            flag2 = get_flag(t2)

            if resolved:
                pts_str = f"✅ +{pts}pts" if pts and pts > 0 else "❌ 0pts"
                total_pts += pts or 0
            else:
                pts_str = "⏳ Pendiente"

            embed.add_field(
                name=f"Grupo {grupo}",
                value=f"{flag1} {t1} y {flag2} {t2}\n{pts_str}",
                inline=True,
            )

        embed.set_footer(text=f"Puntos de quiniela: {total_pts}pts · Mundial 2026")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Predictions(bot))
