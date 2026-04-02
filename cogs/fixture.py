import discord
from discord import app_commands
from discord.ext import commands
import logging

import config
from db.matches import (
    get_all_matches, get_matches_today, get_matches_by_team,
    get_matches_by_group, get_team_recent_form
)
from utils.embeds import build_match_embed, build_daily_matches_embed, get_round_label
from utils.time_helpers import format_match_time, format_match_date, format_match_datetime
import pytz
from datetime import datetime

log = logging.getLogger("worldcup-bot.fixture")

GROUPS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]


def only_in_chat():
    """Check que restringe el uso a #mundial-chat."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.channel_id != config.CHANNEL_CHAT:
            await interaction.response.send_message(
                f"⚽ Los comandos solo se pueden usar en <#{config.CHANNEL_CHAT}>",
                ephemeral=True,
            )
            return False
        return True
    return app_commands.check(predicate)


class Fixture(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="fixture", description="Ver el fixture del Mundial 2026")
    @app_commands.describe(
        filtro="Filtrá por: 'hoy', nombre de equipo (ej: Argentina) o grupo (ej: A)",
    )
    @only_in_chat()
    async def fixture(self, interaction: discord.Interaction, filtro: str = None):
        await interaction.response.defer()

        db = self.bot.db

        if filtro is None:
            # Fixture completo — mostrar próximos 10 partidos
            matches = await get_all_matches(db)
            upcoming = [m for m in matches if m.get("status") != "finished"][:10]
            await self._send_fixture_list(interaction, upcoming, "📅 Próximos partidos")

        elif filtro.lower() == "hoy":
            matches = await get_matches_today(db)
            tz = pytz.timezone(config.TIMEZONE)
            date_str = format_match_date(datetime.now(tz))
            embed = build_daily_matches_embed(matches, date_str)
            await interaction.followup.send(embed=embed)

        elif filtro.upper() in GROUPS:
            matches = await get_matches_by_group(db, filtro.upper())
            await self._send_fixture_list(interaction, matches, f"📊 Grupo {filtro.upper()}")

        else:
            # Buscar por equipo
            matches = await get_matches_by_team(db, filtro)
            if not matches:
                await interaction.followup.send(
                    f"❌ No encontré partidos para **{filtro}**. "
                    f"Probá con el nombre en inglés (ej: Argentina, Brazil, France).",
                    ephemeral=True,
                )
                return
            await self._send_fixture_list(interaction, matches, f"🔍 Partidos de {filtro.title()}")

    async def _send_fixture_list(self, interaction: discord.Interaction, matches: list, title: str):
        """Envía una lista de partidos como embed."""
        if not matches:
            await interaction.followup.send("😴 No hay partidos para mostrar.", ephemeral=True)
            return

        embed = discord.Embed(title=title, color=0x1B4F72)
        tz = pytz.timezone(config.TIMEZONE)

        for match in matches[:15]:  # Máximo 15 para no superar el límite de Discord
            kickoff = match.get("kickoff_utc")
            if isinstance(kickoff, str):
                kickoff = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))

            home = match.get("home_team", "TBD")
            away = match.get("away_team", "TBD")
            status = match.get("status", "scheduled")

            from utils.embeds import get_flag, get_round_label
            home_flag = get_flag(home)
            away_flag = get_flag(away)

            round_label = get_round_label(match.get("round", ""))
            group = match.get("group_name", "")
            phase = f"Grupo {group}" if group else round_label

            if status == "finished":
                score = match.get("score", {})
                result = f"**{score.get('home', '?')} - {score.get('away', '?')}** ✅"
                time_str = result
            elif status == "live":
                score = match.get("score", {})
                time_str = f"**{score.get('home', '?')} - {score.get('away', '?')}** 🔴 EN VIVO"
            else:
                time_str = format_match_datetime(kickoff) if kickoff else "Por confirmar"

            embed.add_field(
                name=f"{home_flag} {home} vs {away} {away_flag}",
                value=f"🕐 {time_str}  |  {phase}",
                inline=False,
            )

        embed.set_footer(text="Horarios en ART (hora Argentina) · Mundial 2026")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="partido", description="Ver detalle de un partido específico")
    @app_commands.describe(equipo="Nombre de uno de los equipos del partido")
    @only_in_chat()
    async def partido(self, interaction: discord.Interaction, equipo: str):
        """Muestra el detalle completo de un partido, con forma reciente."""
        await interaction.response.defer()

        matches = await get_matches_by_team(self.bot.db, equipo)

        if not matches:
            await interaction.followup.send(
                f"❌ No encontré partidos para **{equipo}**.",
                ephemeral=True,
            )
            return

        # Tomar el próximo partido del equipo
        upcoming = [m for m in matches if m.get("status") != "finished"]
        match = upcoming[0] if upcoming else matches[-1]

        home = match.get("home_team", "TBD")
        away = match.get("away_team", "TBD")

        # Obtener forma reciente
        home_form = await get_team_recent_form(self.bot.db, home)
        away_form = await get_team_recent_form(self.bot.db, away)

        embed = build_match_embed(
            match,
            show_form=True,
            home_form=home_form,
            away_form=away_form,
        )
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Fixture(bot))