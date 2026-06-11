import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import logging

import config
from db.users import get_leaderboard, get_user, get_user_rank
from db.matches import get_matches_by_group
from utils.embeds import build_leaderboard_embed, build_standings_embed, get_flag

try:
    from utils.table_image import render_standings_image
except Exception as e:
    print("ERROR IMPORTANDO TABLE_IMAGE:", e)
    render_standings_image = None

log = logging.getLogger("worldcup-bot.stats")

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


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ──────────────────────────────────────────────────────────
    #   /puntos
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="puntos", description="Ver tus puntos y posición en el ranking")
    @only_in_chat()
    async def puntos(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        db = self.bot.db
        user_id = interaction.user.id
        user = await get_user(db, user_id)

        if not user or user.get("total_points", 0) == 0:
            await interaction.followup.send(
                "📭 Todavía no tenés puntos. ¡Empezá pronosticando con `/pronostico`!",
                ephemeral=True,
            )
            return

        rank, total_players = await get_user_rank(db, user_id)

        total_pts  = user.get("total_points", 0)
        correct    = user.get("correct_predictions", 0)
        total_pred = user.get("total_predictions", 0)
        streak     = user.get("streak", 0)
        max_streak = user.get("max_streak", 0)
        champion   = user.get("champion_pick")
        pct        = f"{int(correct / total_pred * 100)}%" if total_pred > 0 else "0%"

        embed = discord.Embed(
            title=f"📊 Estadísticas — {interaction.user.display_name}",
            color=0xF1C40F,
        )
        embed.add_field(name="🏆 Puntos totales", value=f"**{total_pts}**", inline=True)
        embed.add_field(name="📈 Posición",        value=f"**#{rank}** de {total_players}", inline=True)
        embed.add_field(name="🎯 % Aciertos",      value=f"**{pct}** ({correct}/{total_pred})", inline=True)
        embed.add_field(name="🔥 Racha actual",    value=f"**{streak}** partidos", inline=True)
        embed.add_field(name="⭐ Mejor racha",      value=f"**{max_streak}** partidos", inline=True)

        if champion:
            flag = get_flag(champion)
            embed.add_field(
                name="🏅 Campeón elegido",
                value=f"{flag} **{champion}**",
                inline=True,
            )

        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Mundial 2026")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ──────────────────────────────────────────────────────────
    #   /tabla (standings de grupos)
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="tabla", description="Ver la tabla de posiciones de un grupo")
    @app_commands.describe(grupo="Letra del grupo (A-L)")
    @only_in_chat()
    async def tabla(self, interaction: discord.Interaction, grupo: str):
        await interaction.response.defer()

        grupo = grupo.upper()
        if grupo not in GROUPS:
            await interaction.followup.send(
                f"❌ Grupo inválido. Los grupos son: {', '.join(GROUPS)}",
                ephemeral=True,
            )
            return

        standings = await self._calculate_standings(grupo)
        if not standings:
            await interaction.followup.send(
                f"❌ No encontré datos para el Grupo {grupo}.",
                ephemeral=True,
            )
            return

        # Intentar generar imagen con Pillow; caer al embed de texto si falla
        if render_standings_image is not None:
            try:
                buf   = await asyncio.to_thread(render_standings_image, standings, grupo)
                file  = discord.File(buf, filename="tabla.png")
                embed = discord.Embed(color=0x1B4F72)
                embed.set_image(url="attachment://tabla.png")
                await interaction.followup.send(embed=embed, file=file)
                return
            except Exception as e:
                log.warning(f"No se pudo generar la imagen de la tabla, uso texto: {e}")

        await interaction.followup.send(embed=build_standings_embed(standings, grupo))

    async def _calculate_standings(self, group_name: str) -> list:
        """
        Calcula la tabla de posiciones de un grupo desde los partidos
        guardados en MongoDB, sin necesitar un endpoint de standings.
        """
        matches  = await get_matches_by_group(self.bot.db, group_name)
        finished = [m for m in matches if m.get("status") == "finished"]

        teams = {}
        for m in matches:
            for team in [m.get("home_team"), m.get("away_team")]:
                if team and team != "TBD" and team not in teams:
                    teams[team] = {
                        "team": team, "played": 0, "won": 0, "drawn": 0,
                        "lost": 0, "goals_for": 0, "goals_against": 0,
                        "goal_difference": 0, "points": 0,
                    }

        for m in finished:
            score = m.get("score", {})
            hg = score.get("home")
            ag = score.get("away")
            if hg is None or ag is None:
                continue

            home = m["home_team"]
            away = m["away_team"]
            if home not in teams or away not in teams:
                continue

            teams[home]["played"] += 1
            teams[away]["played"] += 1
            teams[home]["goals_for"]     += hg
            teams[home]["goals_against"] += ag
            teams[away]["goals_for"]     += ag
            teams[away]["goals_against"] += hg

            if hg > ag:
                teams[home]["won"]    += 1
                teams[home]["points"] += 3
                teams[away]["lost"]   += 1
            elif ag > hg:
                teams[away]["won"]    += 1
                teams[away]["points"] += 3
                teams[home]["lost"]   += 1
            else:
                teams[home]["drawn"]  += 1
                teams[away]["drawn"]  += 1
                teams[home]["points"] += 1
                teams[away]["points"] += 1

        for team in teams.values():
            team["goal_difference"] = team["goals_for"] - team["goals_against"]

        return sorted(
            teams.values(),
            key=lambda t: (t["points"], t["goal_difference"], t["goals_for"]),
            reverse=True,
        )

    # ──────────────────────────────────────────────────────────
    #   /ranking
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="ranking", description="Ver el ranking general de pronósticos")
    @only_in_chat()
    async def ranking(self, interaction: discord.Interaction):
        await interaction.response.defer()

        users = await get_leaderboard(self.bot.db, limit=15)
        if not users:
            await interaction.followup.send(
                "📭 Todavía no hay puntos registrados. ¡Empezá pronosticando!",
            )
            return

        await interaction.followup.send(embed=build_leaderboard_embed(users))


async def setup(bot):
    await bot.add_cog(Stats(bot))