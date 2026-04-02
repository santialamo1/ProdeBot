import os
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════
#           DISCORD
# ══════════════════════════════════════
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

# ══════════════════════════════════════
#           MONGODB
# ══════════════════════════════════════
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "worldcup_bot")

# ══════════════════════════════════════
#           APIs
# ══════════════════════════════════════
WC2026_API_KEY = os.getenv("WC2026_API_KEY")
WC2026_BASE_URL = "https://api.wc2026api.com"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ══════════════════════════════════════
#           CANALES
# ══════════════════════════════════════
CHANNEL_PARTIDOS_HOY = int(os.getenv("CHANNEL_PARTIDOS_HOY"))
CHANNEL_PRONOSTICOS = int(os.getenv("CHANNEL_PRONOSTICOS"))
CHANNEL_RESULTADOS = int(os.getenv("CHANNEL_RESULTADOS"))
CHANNEL_ESTADISTICAS = int(os.getenv("CHANNEL_ESTADISTICAS"))
CHANNEL_TRIVIA = int(os.getenv("CHANNEL_TRIVIA"))
CHANNEL_CHAT = int(os.getenv("CHANNEL_CHAT"))

# ══════════════════════════════════════
#           CONFIGURACION
# ══════════════════════════════════════
TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Buenos_Aires")
TRIVIA_INTERVAL_HOURS = int(os.getenv("TRIVIA_INTERVAL_HOURS", 12))

# Minutos antes del partido para cerrar pronósticos
PREDICTION_CLOSE_MINUTES = 10

# Minutos antes del partido para enviar reminder
REMINDER_MINUTES = 60

# Sistema de puntos
POINTS_WINNER = 1       # Acertar ganador o empate
POINTS_DIFF = 2         # Acertar diferencia de goles
POINTS_EXACT = 3        # Acertar resultado exacto
POINTS_STREAK_BONUS = 1 # Bonus por racha de 3+
STREAK_MIN = 3          # Mínimo de aciertos para activar bonus de racha
POINTS_CHAMPION = 10    # Bonus por acertar campeón

# Multiplicador en fases eliminatorias avanzadas
MULTIPLIER_STAGES = ["quarter-final", "semi-final", "final"]
STAGE_MULTIPLIER = 2

# Quiniela de grupos
POINTS_QUINIELA_BOTH = 5   # Acertar ambos clasificados
POINTS_QUINIELA_ONE = 2    # Acertar uno de los dos

# Sync con API
FIXTURE_SYNC_HOURS = 6      # Cada cuántas horas sincronizar el fixture
LIVE_POLL_SECONDS = 120     # Cada cuántos segundos hacer polling durante partidos live