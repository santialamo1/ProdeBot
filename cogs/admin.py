import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timedelta
import pytz

import config
from tasks.live_polling import _process_finished_match
from tasks.sync_fixture import sync_fixture

log = logging.getLogger("worldcup-bot.admin")


def only_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Solo los administradores pueden usar este comando.",
                ephemeral=True,
            )
            return False
        return True
    return app_commands.check(predicate)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ──────────────────────────────────────────────────────────
    #   FIXTURE & PARTIDOS
    # ──────────────────────────────────────────────────────────

    @app_commands.command(name="admin_match_id", description="[ADMIN] Ver match_id de los partidos de hoy")
    @only_admin()
    async def admin_match_id(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        from db.matches import get_matches_today
        matches = await get_matches_today(self.bot.db)

        if not matches:
            await interaction.followup.send("No hay partidos hoy.", ephemeral=True)
            return

        lines = []
        for m in matches:
            lines.append(
                f"`{m['match_id']}` — {m.get('home_team')} vs {m.get('away_team')} ({m.get('status')})"
            )

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="admin_partido_hoy", description="[ADMIN] Forzar el post de partidos del dia")
    @only_admin()
    async def admin_partido_hoy(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from tasks.daily_post import post_partidos_hoy
        await post_partidos_hoy(self.bot)
        await interaction.followup.send("✅ Post de partidos del día enviado.", ephemeral=True)

    @app_commands.command(name="admin_sync", description="[ADMIN] Forzar sincronizacion del fixture con la API")
    @only_admin()
    async def admin_sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await sync_fixture(self.bot)
        await interaction.followup.send("✅ Sync completado.", ephemeral=True)

    @app_commands.command(name="admin_set_fecha", description="[ADMIN] Cambiar la fecha de un partido para testing")
    @app_commands.describe(
        match_id="ID del partido",
        minutos="En cuantos minutos empieza (ej: 15 = en 15 min, -30 = hace 30 min)",
    )
    @only_admin()
    async def admin_set_fecha(self, interaction: discord.Interaction, match_id: str, minutos: int):
        await interaction.response.defer(ephemeral=True)

        match = await self.bot.db.matches.find_one({"match_id": match_id})
        if not match:
            await interaction.followup.send(f"No encontre el partido `{match_id}`.", ephemeral=True)
            return

        nueva_fecha = datetime.now(pytz.utc) + timedelta(minutes=minutos)
        await self.bot.db.matches.update_one(
            {"match_id": match_id},
            {"$set": {
                "kickoff_utc": nueva_fecha,
                "status": "scheduled",
                "score.home": None,
                "score.away": None,
            }}
        )

        home = match.get("home_team", "?")
        away = match.get("away_team", "?")
        signo = "+" if minutos >= 0 else ""
        await interaction.followup.send(
            f"Partido **{home} vs {away}** actualizado.\n"
            f"Kickoff en `{signo}{minutos} minutos` — UTC: `{nueva_fecha.strftime('%H:%M:%S')}`",
            ephemeral=True,
        )

    # ──────────────────────────────────────────────────────────
    #   PRONOSTICOS & RESULTADOS
    # ──────────────────────────────────────────────────────────

    @app_commands.command(name="admin_resultado", description="[ADMIN] Forzar resultado de un partido y calcular puntos")
    @app_commands.describe(
        match_id="ID del partido",
        goles_local="Goles del equipo local",
        goles_visitante="Goles del equipo visitante",
    )
    @only_admin()
    async def admin_resultado(
        self,
        interaction: discord.Interaction,
        match_id: str,
        goles_local: int,
        goles_visitante: int,
    ):
        await interaction.response.defer(ephemeral=True)

        match = await self.bot.db.matches.find_one({"match_id": match_id})
        if not match:
            await interaction.followup.send(f"No encontre el partido `{match_id}`.", ephemeral=True)
            return

        await self.bot.db.matches.update_one(
            {"match_id": match_id},
            {"$set": {
                "status": "finished",
                "score.home": goles_local,
                "score.away": goles_visitante,
            }}
        )

        home = match.get("home_team", "?")
        away = match.get("away_team", "?")

        await interaction.followup.send(
            f"Resultado: **{home} {goles_local} - {goles_visitante} {away}** — procesando puntos...",
            ephemeral=True,
        )

        await _process_finished_match(self.bot, match_id)
        await interaction.followup.send("Puntos calculados y posteados en #resultados.", ephemeral=True)

    @app_commands.command(name="admin_cerrar_pronosticos", description="[ADMIN] Forzar el cierre de pronosticos de un partido")
    @app_commands.describe(match_id="ID del partido")
    @only_admin()
    async def admin_cerrar_pronosticos(self, interaction: discord.Interaction, match_id: str):
        await interaction.response.defer(ephemeral=True)

        match = await self.bot.db.matches.find_one({"match_id": match_id})
        if not match:
            await interaction.followup.send(f"No encontre el partido `{match_id}`.", ephemeral=True)
            return

        from tasks.daily_post import close_predictions_for_match
        await close_predictions_for_match(self.bot, match)
        await interaction.followup.send(
            f"Pronosticos cerrados para **{match.get('home_team')} vs {match.get('away_team')}**.",
            ephemeral=True,
        )

    @app_commands.command(name="admin_reminder", description="[ADMIN] Forzar el reminder de un partido")
    @app_commands.describe(match_id="ID del partido")
    @only_admin()
    async def admin_reminder(self, interaction: discord.Interaction, match_id: str):
        await interaction.response.defer(ephemeral=True)

        match = await self.bot.db.matches.find_one({"match_id": match_id})
        if not match:
            await interaction.followup.send(f"No encontre el partido `{match_id}`.", ephemeral=True)
            return

        channel = self.bot.get_channel(config.CHANNEL_PARTIDOS_HOY)
        if not channel:
            await interaction.followup.send("Canal #partidos-de-hoy no encontrado.", ephemeral=True)
            return

        home = match.get("home_team", "?")
        away = match.get("away_team", "?")

        from utils.embeds import get_flag
        home_flag = get_flag(home)
        away_flag = get_flag(away)

        embed = discord.Embed(
            title="⏰ ¡Partido en 1 hora!",
            description=f"## {home_flag} {home}  vs  {away} {away_flag}\n\n"
                        f"¡Hace tu pronostico antes de que cierren! Usa `/pronostico` en #mundial-chat",
            color=0xFF6B35,
        )
        embed.set_footer(text="Los pronosticos cierran 10 minutos antes del partido · Mundial 2026")

        await channel.send(embed=embed)
        await interaction.followup.send("Reminder enviado en #partidos-de-hoy.", ephemeral=True)

    # ──────────────────────────────────────────────────────────
    #   PUNTOS & USUARIOS
    # ──────────────────────────────────────────────────────────

    @app_commands.command(name="admin_reset_usuario", description="[ADMIN] Resetear puntos y stats de un usuario")
    @app_commands.describe(usuario="El usuario a resetear")
    @only_admin()
    async def admin_reset_usuario(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer(ephemeral=True)

        await self.bot.db.users.update_one(
            {"user_id": str(usuario.id)},
            {"$set": {
                "total_points": 0,
                "streak": 0,
                "max_streak": 0,
                "correct_predictions": 0,
                "total_predictions": 0,
                "champion_pick": None,
                "champion_points_earned": None,
            }}
        )
        await self.bot.db.predictions.delete_many({"user_id": str(usuario.id)})
        await self.bot.db.quiniela.delete_many({"user_id": str(usuario.id)})

        await interaction.followup.send(
            f"Usuario **{usuario.display_name}** reseteado — puntos, pronosticos y quiniela eliminados.",
            ephemeral=True,
        )

    @app_commands.command(name="admin_dar_puntos", description="[ADMIN] Dar o restar puntos a un usuario")
    @app_commands.describe(
        usuario="El usuario",
        puntos="Cantidad de puntos (negativo para restar)",
    )
    @only_admin()
    async def admin_dar_puntos(self, interaction: discord.Interaction, usuario: discord.Member, puntos: int):
        await interaction.response.defer(ephemeral=True)

        await self.bot.db.users.update_one(
            {"user_id": str(usuario.id)},
            {"$inc": {"total_points": puntos}},
            upsert=True,
        )

        signo = "+" if puntos >= 0 else ""
        await interaction.followup.send(
            f"**{usuario.display_name}** → `{signo}{puntos}pts`.",
            ephemeral=True,
        )

    @app_commands.command(name="admin_resolver_campeon", description="[ADMIN] Resolver las predicciones del campeon")
    @app_commands.describe(campeon="Nombre del equipo campeon")
    @only_admin()
    async def admin_resolver_campeon(self, interaction: discord.Interaction, campeon: str):
        await interaction.response.defer(ephemeral=True)

        cursor = self.bot.db.users.find({
            "champion_pick": {"$ne": None},
            "champion_points_earned": None,
        })
        users = await cursor.to_list(length=None)

        if not users:
            await interaction.followup.send("No hay predicciones de campeon pendientes.", ephemeral=True)
            return

        ganadores = []
        for user in users:
            pick = user.get("champion_pick", "")
            if pick.lower() == campeon.lower():
                await self.bot.db.users.update_one(
                    {"user_id": user["user_id"]},
                    {"$inc": {"total_points": config.POINTS_CHAMPION},
                     "$set": {"champion_points_earned": config.POINTS_CHAMPION}}
                )
                ganadores.append(user.get("username", user["user_id"]))
            else:
                await self.bot.db.users.update_one(
                    {"user_id": user["user_id"]},
                    {"$set": {"champion_points_earned": 0}}
                )

        from utils.embeds import get_flag
        flag = get_flag(campeon)

        channel = self.bot.get_channel(config.CHANNEL_RESULTADOS)
        if channel:
            embed = discord.Embed(
                title="¡Campeon del Mundial!",
                description=f"## {flag} {campeon}",
                color=0xF1C40F,
            )
            if ganadores:
                embed.add_field(
                    name=f"Acertaron el campeon (+{config.POINTS_CHAMPION}pts)",
                    value="\n".join([f"⭐ **{g}**" for g in ganadores]),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="Nadie acerto el campeon",
                    value="¡Nadie eligio al campeon correctamente!",
                    inline=False,
                )
            await channel.send(embed=embed)

        await interaction.followup.send(
            f"Campeon resuelto: **{campeon}** — {len(ganadores)} usuario(s) acertaron.",
            ephemeral=True,
        )

    @app_commands.command(name="admin_resolver_quiniela", description="[ADMIN] Resolver la quiniela de un grupo")
    @app_commands.describe(
        grupo="Letra del grupo (A-L)",
        clasificado1="Primer equipo clasificado",
        clasificado2="Segundo equipo clasificado",
    )
    @only_admin()
    async def admin_resolver_quiniela(
        self,
        interaction: discord.Interaction,
        grupo: str,
        clasificado1: str,
        clasificado2: str,
    ):
        await interaction.response.defer(ephemeral=True)

        from db.predictions import resolve_quiniela
        await resolve_quiniela(self.bot.db, grupo.upper(), clasificado1, clasificado2)

        await interaction.followup.send(
            f"Quiniela del **Grupo {grupo.upper()}** resuelta.\n"
            f"Clasificados: **{clasificado1}** y **{clasificado2}**",
            ephemeral=True,
        )

    # ──────────────────────────────────────────────────────────
    #   TEST FLUJO COMPLETO
    # ──────────────────────────────────────────────────────────

    @app_commands.command(name="admin_test_flujo", description="[ADMIN] Simula el flujo completo de un partido")
    @app_commands.describe(
        match_id="ID del partido",
        goles_local="Goles del local para el resultado final",
        goles_visitante="Goles del visitante para el resultado final",
    )
    @only_admin()
    async def admin_test_flujo(
        self,
        interaction: discord.Interaction,
        match_id: str,
        goles_local: int,
        goles_visitante: int,
    ):
        """
        Simula el flujo completo en orden:
        1. Post diario en #partidos-de-hoy
        2. Reminder 1h antes
        3. Cierre de pronosticos
        4. Resultado final + puntos
        5. Update del leaderboard
        """
        await interaction.response.defer(ephemeral=True)

        match = await self.bot.db.matches.find_one({"match_id": match_id})
        if not match:
            await interaction.followup.send(f"No encontre el partido `{match_id}`.", ephemeral=True)
            return

        home = match.get("home_team", "?")
        away = match.get("away_team", "?")

        import asyncio
        from utils.embeds import get_flag
        from tasks.daily_post import post_partidos_hoy, close_predictions_for_match

        await interaction.followup.send(
            f"Iniciando test completo: **{home} vs {away}**\nSeguí los mensajes en los canales...",
            ephemeral=True,
        )

        # Paso 1 — Post diario
        await interaction.followup.send("📅 **1/4** — Posteando partidos del día...", ephemeral=True)
        await post_partidos_hoy(self.bot)
        await asyncio.sleep(2)

        # Paso 2 — Reminder
        await interaction.followup.send("⏰ **2/4** — Enviando reminder...", ephemeral=True)
        channel = self.bot.get_channel(config.CHANNEL_PARTIDOS_HOY)
        if channel:
            home_flag = get_flag(home)
            away_flag = get_flag(away)
            embed = discord.Embed(
                title="⏰ ¡Partido en 1 hora!",
                description=f"## {home_flag} {home}  vs  {away} {away_flag}\n\n"
                            f"¡Hace tu pronostico antes de que cierren! Usa `/pronostico` en #mundial-chat",
                color=0xFF6B35,
            )
            embed.set_footer(text="Los pronosticos cierran 10 minutos antes del partido · Mundial 2026")
            await channel.send(embed=embed)
        await asyncio.sleep(2)

        # Paso 3 — Cierre de pronosticos
        await interaction.followup.send("🔒 **3/4** — Cerrando pronosticos...", ephemeral=True)
        await close_predictions_for_match(self.bot, match)
        await asyncio.sleep(2)

        # Paso 4 — Resultado + puntos
        await interaction.followup.send("🏁 **4/4** — Procesando resultado y puntos...", ephemeral=True)
        await self.bot.db.matches.update_one(
            {"match_id": match_id},
            {"$set": {
                "status": "finished",
                "score.home": goles_local,
                "score.away": goles_visitante,
            }}
        )
        await _process_finished_match(self.bot, match_id)

        await interaction.followup.send(
            f"✅ **Test completado.** Revisá los canales:\n"
            f"• #partidos-de-hoy → post del día + reminder\n"
            f"• #pronosticos → embed cerrado\n"
            f"• #resultados → **{home} {goles_local}-{goles_visitante} {away}**\n"
            f"• #estadisticas → ranking actualizado",
            ephemeral=True,
        )

    @app_commands.command(name="admin_reset_partido", description="[ADMIN] Resetear un partido a estado inicial para re-testear")
    @app_commands.describe(
        match_id="ID del partido",
        minutos="En cuantos minutos empieza (default: 60)",
    )
    @only_admin()
    async def admin_reset_partido(self, interaction: discord.Interaction, match_id: str, minutos: int = 60):
        await interaction.response.defer(ephemeral=True)

        match = await self.bot.db.matches.find_one({"match_id": match_id})
        if not match:
            await interaction.followup.send(f"No encontre el partido `{match_id}`.", ephemeral=True)
            return

        nueva_fecha = datetime.now(pytz.utc) + timedelta(minutes=minutos)

        await self.bot.db.matches.update_one(
            {"match_id": match_id},
            {"$set": {
                "status": "scheduled",
                "score.home": None,
                "score.away": None,
                "kickoff_utc": nueva_fecha,
            }}
        )

        await self.bot.db.predictions.update_many(
            {"match_id": match_id},
            {"$set": {"points_earned": None}}
        )

        existing = await self.bot.db.prediction_messages.find_one({"match_id": match_id})
        if existing:
            channel = self.bot.get_channel(config.CHANNEL_PRONOSTICOS)
            if channel:
                try:
                    msg = await channel.fetch_message(existing["message_id"])
                    await msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
            await self.bot.db.prediction_messages.delete_one({"match_id": match_id})

        home = match.get("home_team", "?")
        away = match.get("away_team", "?")

        await interaction.followup.send(
            f"Partido **{home} vs {away}** reseteado a `scheduled`.\n"
            f"Kickoff en **{minutos} minutos**.\n"
            f"Nota: los puntos de usuarios NO se revirtieron — usa `/admin_reset_usuario` si es necesario.",
            ephemeral=True,
        )


    @app_commands.command(name="admin_trivia", description="[ADMIN] Forzar una trivia sin cooldown")
    @only_admin()
    async def admin_trivia(self, interaction: discord.Interaction):
        trivia_cog = self.bot.get_cog("Trivia")
        if not trivia_cog:
            await interaction.response.send_message("Cog de trivia no encontrado.", ephemeral=True)
            return

        if trivia_cog._active_trivia:
            await interaction.response.send_message("Ya hay una trivia activa.", ephemeral=True)
            return

        await interaction.response.send_message("Generando trivia...", ephemeral=True)
        import asyncio
        asyncio.create_task(trivia_cog.post_trivia_question())

    @app_commands.command(name="admin_reset_trivia", description="[ADMIN] Resetear historial de preguntas y ranking de trivia")
    @app_commands.describe(
        que="Que resetear: 'todo', 'preguntas' o 'ranking'",
    )
    @only_admin()
    async def admin_reset_trivia(self, interaction: discord.Interaction, que: str = "todo"):
        await interaction.response.defer(ephemeral=True)

        que = que.lower()
        if que not in ("todo", "preguntas", "ranking"):
            await interaction.followup.send(
                "❌ Opción inválida. Usá: `todo`, `preguntas` o `ranking`.",
                ephemeral=True,
            )
            return

        msgs = []

        if que in ("todo", "preguntas"):
            result = await self.bot.db.trivia.delete_many({})
            msgs.append(f"🗑️ Historial de preguntas eliminado ({result.deleted_count} preguntas).")

            # Resetear cooldown en memoria
            trivia_cog = self.bot.get_cog("Trivia")
            if trivia_cog:
                trivia_cog._last_trivia_time = None

        if que in ("todo", "ranking"):
            result = await self.bot.db.trivia_ranking.delete_many({})
            msgs.append(f"🗑️ Ranking de trivia eliminado ({result.deleted_count} usuarios).")

        await interaction.followup.send("\n".join(msgs), ephemeral=True)


    @app_commands.command(name="admin_verificar_resultados", description="[ADMIN] Verifica si algún score cambió y recalcula puntos")
    @only_admin()
    async def admin_verificar_resultados(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        from utils.points import calculate_points
        from tasks.live_polling import _recalculate_points

        # Buscar partidos finalizados/completados con pronosticos ya puntuados
        cursor = self.bot.db.matches.find({
            "status": {"$in": ["finished", "completed", "ft", "aet", "pen"]}
        })
        matches = await cursor.to_list(length=None)

        corregidos = []

        for match in matches:
            match_id = match["match_id"]
            db_home = match.get("score", {}).get("home")
            db_away = match.get("score", {}).get("away")

            if db_home is None or db_away is None:
                continue

            # Tomar un pronostico de muestra que ya tenga puntos calculados
            pred_sample = await self.bot.db.predictions.find_one({
                "match_id": match_id,
                "points_earned": {"$ne": None},
            })
            if not pred_sample:
                continue

            # Recalcular con el score actual y comparar
            new_points, _ = calculate_points(
                predicted_home=pred_sample["predicted_home"],
                predicted_away=pred_sample["predicted_away"],
                actual_home=db_home,
                actual_away=db_away,
                stage=match.get("round", "group"),
                streak=0,
            )

            if new_points != (pred_sample.get("points_earned") or 0):
                home = match.get("home_team", "?")
                away = match.get("away_team", "?")
                corregidos.append(f"{home} vs {away} ({db_home}-{db_away})")
                await _recalculate_points(self.bot, match_id, db_home, db_away)

        if corregidos:
            await interaction.followup.send(
                f"✅ Se corrigieron {len(corregidos)} partido(s):\n" + "\n".join(corregidos),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "✅ Todos los resultados están correctos, no hubo cambios.",
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(Admin(bot))
