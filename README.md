# ⚽ ProdeBot — Mundial 2026

Bot de Discord para pronósticos deportivos del Mundial FIFA 2026. Gestiona fixtures, pronósticos, puntos, rankings y trivia de forma completamente automática.

---

## ✨ Funcionalidades

### 📅 Fixture & Partidos
- Sync automático con la API de WC2026 cada 6 horas
- Post diario en `#partidos-de-hoy` a las 9AM (hora Argentina)
- Reminder automático 1 hora antes de cada partido
- Consulta por equipo, grupo o fecha

### 🎯 Pronósticos
- Pronósticos por partido con cierre automático 10 minutos antes del inicio
- Embed en `#pronosticos` que se actualiza en tiempo real con cada pronóstico
- Historial personal por usuario

### 🏅 Sistema de Puntos
| Acierto | Puntos |
|---|---|
| Ganador o empate | +1 pt |
| Diferencia de goles | +2 pts |
| Resultado exacto | +3 pts |
| Racha de 3+ aciertos | +1 pt bonus |
| Cuartos / Semis / Final | x2 puntos |
| Campeón del Mundial | +10 pts bonus |

### 📊 Estadísticas
- Ranking general en `#estadisticas` que se edita automáticamente
- Tabla de posiciones de grupos calculada desde MongoDB
- Estadísticas personales: puntos, racha, % de aciertos

### 🎰 Quiniela de Grupos
- Predicción de clasificados por grupo antes del torneo
- +5 pts por ambos correctos, +2 pts por uno correcto

### 🧠 Trivia
- Preguntas automáticas generadas con IA (OpenAI GPT-4o-mini) cada 4 horas
- Respuesta por reacciones de Discord
- Revela respuesta y menciona a quienes acertaron

---

## 🛠️ Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Discord | discord.py 2.3 + slash commands |
| Base de datos | MongoDB Atlas + motor (async) |
| Scheduler | APScheduler |
| API de datos | WC2026API |
| Trivia | OpenAI GPT-4o |
| Hosting | Railway |

---

## 📁 Estructura del Proyecto

```
worldcup-bot/
├── bot.py                  # Entry point
├── config.py               # Variables de entorno centralizadas
├── requirements.txt
├── Procfile                # Configuración Railway
│
├── cogs/                   # Comandos de Discord
│   ├── fixture.py          # /fixture, /partido
│   ├── predictions.py      # /pronostico, /mispronosticos, /campeon, /quiniela
│   ├── stats.py            # /puntos, /tabla, /ranking
│   ├── trivia.py           # Trivia automática
│   └── admin.py            # Comandos de administración
│
├── tasks/                  # Tareas programadas
│   ├── sync_fixture.py     # Sync con API cada 6hs
│   ├── daily_post.py       # Post diario + reminders
│   └── live_polling.py     # Polling en vivo + cálculo de puntos
│
├── db/                     # Capa de acceso a MongoDB
│   ├── matches.py
│   ├── predictions.py
│   └── users.py
│
└── utils/
    ├── embeds.py           # Todos los Discord embeds
    ├── points.py           # Lógica de cálculo de puntos
    └── time_helpers.py     # Helpers de timezone (ART)
```

---

## ⚙️ Configuración

### 1. Clonar el repositorio

```bash
[git clone https://github.com/santialamo1/ProdeBot.git
cd ProdeBot
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Creá un archivo `.env` en la raíz del proyecto:

```env
# Discord
DISCORD_TOKEN=
GUILD_ID=

# MongoDB
MONGODB_URI=
MONGODB_DB=worldcup_bot

# APIs
WC2026_API_KEY=
OPENAI_API_KEY=

# Canales de Discord (IDs)
CHANNEL_PARTIDOS_HOY=
CHANNEL_PRONOSTICOS=
CHANNEL_RESULTADOS=
CHANNEL_ESTADISTICAS=
CHANNEL_TRIVIA=
CHANNEL_CHAT=

# Configuración
TRIVIA_INTERVAL_HOURS=4
TIMEZONE=America/Argentina/Buenos_Aires
```

### 4. Crear los canales en Discord

Crear una categoría **MUNDIAL 2026** con estos canales:

```
📁 MUNDIAL 2026
├── 📢 partidos-de-hoy
├── 🎯 pronosticos
├── 🏆 resultados
├── 📊 estadisticas
├── 🧠 trivia
└── 💬 mundial-chat
```

Copiar los IDs de cada canal (click derecho → Copiar ID) y pegarlos en el `.env`.

### 5. Permisos del bot en Discord Developer Portal

**Scopes:** `bot` + `applications.commands`

**Permisos:**
- Read Messages / View Channels
- Send Messages
- Manage Messages
- Embed Links
- Add Reactions
- Read Message History

### 6. Correr el bot

```bash
python bot.py
```

---

## 🚀 Deploy en Railway

1. Subir el proyecto a un repositorio de GitHub
2. Crear un nuevo proyecto en [Railway](https://railway.app)
3. Conectar el repositorio de GitHub
4. Cargar todas las variables del `.env` en **Variables** del panel de Railway
5. Railway detecta el `Procfile` y hace el deploy automáticamente

> El `Procfile` contiene: `worker: python bot.py`

---

## 🎮 Comandos

| Comando | Descripción | Visible para |
|---|---|---|
| `/fixture [filtro]` | Ver fixture. Filtros: `hoy`, nombre de equipo, letra de grupo | Todos |
| `/partido [equipo]` | Detalle de un partido con forma reciente | Todos |
| `/pronostico` | Pronosticar resultado de un partido de hoy | Solo vos |
| `/mispronosticos` | Ver tu historial de pronósticos | Solo vos |
| `/campeon` | Elegir campeón del Mundial (una sola vez) | Todos |
| `/quiniela` | Predecir clasificados de un grupo | Solo vos |
| `/miquiniela` | Ver tus predicciones de quiniela | Solo vos |
| `/puntos` | Ver tus puntos y estadísticas | Solo vos |
| `/tabla [grupo]` | Tabla de posiciones de un grupo | Todos |
| `/ranking` | Ranking general del servidor | Todos |

### Comandos de administración

| Comando | Descripción |
|---|---|
| `/admin_resultado` | Forzar resultado de un partido y calcular puntos |
| `/admin_sync` | Forzar sync del fixture con la API |
| `/admin_partido_hoy` | Forzar el post de partidos del día |
| `/admin_match_id` | Ver los match_id de los partidos de hoy |
| `/trivia` | Lanzar una pregunta de trivia manualmente |

---

## 🗄️ Colecciones de MongoDB

| Colección | Contenido |
|---|---|
| `matches` | Fixture completo con scores y estados |
| `predictions` | Pronósticos de usuarios por partido |
| `users` | Puntos, rachas y estadísticas por usuario |
| `quiniela` | Predicciones de clasificados por grupo |
| `trivia` | Historial de preguntas de trivia |
| `prediction_messages` | IDs de mensajes de embeds en #pronosticos |
| `bot_messages` | IDs de mensajes fijos del bot (leaderboard) |

---

## 📡 API de datos

El bot usa [WC2026API](https://www.wc2026api.com) con un plan gratuito de 100 requests/día.

Gracias al sistema de cache en MongoDB, el consumo real es muy bajo:

- Días sin partidos: ~4 requests (sync cada 6hs)
- Días con partidos: ~4 sync + ~60 polling en vivo

---

## 📝 Licencia

Proyecto privado. Todos los derechos reservados.
