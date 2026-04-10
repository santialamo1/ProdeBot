import discord
from discord.ext import commands
import motor.motor_asyncio
import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

import config

# ══════════════════════════════════════
#           LOGGING
# ══════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("worldcup-bot")

# ══════════════════════════════════════
#           BOT
# ══════════════════════════════════════
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class WorldCupBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",  # No se usa pero requerido por commands.Bot
            intents=intents,
            help_command=None,
        )
        self.db_client: motor.motor_asyncio.AsyncIOMotorClient = None
        self.db: motor.motor_asyncio.AsyncIOMotorDatabase = None
        self.scheduler: AsyncIOScheduler = None
        self.tz = pytz.timezone(config.TIMEZONE)

    async def setup_hook(self):
        """Se ejecuta antes de que el bot se conecte a Discord."""

        # ── MongoDB ──────────────────────────────────
        log.info("Conectando a MongoDB Atlas...")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGODB_URI)
        self.db = self.db_client[config.MONGODB_DB]
        log.info(f"Conectado a la base de datos: {config.MONGODB_DB}")

        # ── Índices ───────────────────────────────────
        await self._create_indexes()

        # ── Cogs ──────────────────────────────────────
        cogs = [
            "cogs.fixture",
            "cogs.predictions",
            "cogs.stats",
            "cogs.trivia",
            "cogs.admin",
        ]
        for cog in cogs:
            await self.load_extension(cog)
            log.info(f"Cog cargado: {cog}")

        # ── Slash commands ────────────────────────────
        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        log.info("Slash commands sincronizados")

        # ── Scheduler ─────────────────────────────────
        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self._setup_scheduler()
        self.scheduler.start()
        log.info("Scheduler iniciado")

    async def _create_indexes(self):
        """Crea índices en MongoDB para optimizar consultas."""
        # matches
        await self.db.matches.create_index("match_id", unique=True)
        await self.db.matches.create_index("kickoff_utc")
        await self.db.matches.create_index("status")
        await self.db.matches.create_index("group_name")

        # predictions
        await self.db.predictions.create_index(
            [("user_id", 1), ("match_id", 1)], unique=True
        )
        await self.db.predictions.create_index("match_id")

        # users
        await self.db.users.create_index("user_id", unique=True)

        # quiniela
        await self.db.quiniela.create_index(
            [("user_id", 1), ("group_name", 1)], unique=True
        )

        # trivia
        await self.db.trivia.create_index("posted_at")

        # trivia_ranking
        await self.db.trivia_ranking.create_index("user_id", unique=True)
        await self.db.trivia_ranking.create_index("aciertos")

        log.info("Índices de MongoDB creados")

    def _setup_scheduler(self):
        """Registra todas las tareas programadas."""
        from tasks.daily_post import post_partidos_hoy, send_reminders
        from tasks.sync_fixture import sync_fixture
        from tasks.live_polling import check_live_matches

        # Sync del fixture cada 6 horas
        self.scheduler.add_job(
            sync_fixture,
            IntervalTrigger(hours=config.FIXTURE_SYNC_HOURS),
            args=[self],
            id="sync_fixture",
            name="Sincronizar fixture con API",
            replace_existing=True,
        )

        # Post de partidos del día a las 9AM hora Argentina
        self.scheduler.add_job(
            post_partidos_hoy,
            CronTrigger(hour=9, minute=0, timezone=self.tz),
            args=[self],
            id="daily_post",
            name="Post partidos del día",
            replace_existing=True,
        )

        # Reminders cada minuto (la función internamente filtra los que tocan)
        self.scheduler.add_job(
            send_reminders,
            IntervalTrigger(minutes=1),
            args=[self],
            id="reminders",
            name="Reminders pre-partido",
            replace_existing=True,
        )

        # Polling de partidos en vivo cada 2 minutos
        self.scheduler.add_job(
            check_live_matches,
            IntervalTrigger(seconds=config.LIVE_POLL_SECONDS),
            args=[self],
            id="live_polling",
            name="Polling partidos en vivo",
            replace_existing=True,
        )

        # Trivia cada X horas
        self.scheduler.add_job(
            self._post_trivia,
            IntervalTrigger(hours=config.TRIVIA_INTERVAL_HOURS),
            id="trivia",
            name="Post trivia",
            replace_existing=True,
        )

    async def _post_trivia(self):
        """Wrapper para llamar al cog de trivia desde el scheduler."""
        trivia_cog = self.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog.post_trivia_question()

    async def on_ready(self):
        log.info(f"Bot conectado como {self.user} (ID: {self.user.id})")
        log.info("══════════════════════════════════════")
        log.info("   ⚽  Mundial 2026 Bot - Online")
        log.info("══════════════════════════════════════")

        # Sync inicial del fixture si MongoDB está vacío
        match_count = await self.db.matches.count_documents({})
        if match_count == 0:
            log.info("Base de datos vacía — iniciando sync completo del fixture...")
            from tasks.sync_fixture import sync_fixture
            await sync_fixture(self)
        else:
            log.info(f"Fixture ya en DB: {match_count} partidos cargados")

    async def on_app_command_error(self, interaction: discord.Interaction, error):
        """Manejo global de errores en slash commands."""
        if isinstance(error, discord.app_commands.errors.CheckFailure):
            return  # Ya manejado en el check
        log.error(f"Error en comando: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Ocurrió un error inesperado. Intentá de nuevo.",
                ephemeral=True
            )

    async def close(self):
        """Limpieza al cerrar el bot."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            log.info("Scheduler detenido")
        if self.db_client:
            self.db_client.close()
            log.info("Conexión a MongoDB cerrada")
        await super().close()


# ══════════════════════════════════════
#           ENTRY POINT
# ══════════════════════════════════════
async def main():
    bot = WorldCupBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())