import discord
from datetime import datetime
from utils.time_helpers import format_match_time, format_match_date, format_match_datetime, utc_to_local, to_discord_timestamp, to_discord_timestamp_tr
from utils.points import format_score

# Colores del bot
COLOR_PRIMARY = 0x1B4F72    # Azul oscuro (fondo principal)
COLOR_SUCCESS = 0x27AE60    # Verde
COLOR_WARNING = 0xF39C12    # Naranja
COLOR_DANGER = 0xE74C3C     # Rojo
COLOR_LIVE = 0xFF4136       # Rojo vivo para partidos en curso
COLOR_GOLD = 0xF1C40F       # Dorado para rankings

# Emojis de banderas por nombre completo en inglés (tal como los devuelve la API)
FLAG_EMOJIS = {
    # América del Sur
    "Argentina": "🇦🇷",
    "Brazil": "🇧🇷",
    "Uruguay": "🇺🇾",
    "Colombia": "🇨🇴",
    "Ecuador": "🇪🇨",
    "Venezuela": "🇻🇪",
    "Paraguay": "🇵🇾",
    "Bolivia": "🇧🇴",
    "Chile": "🇨🇱",
    "Peru": "🇵🇪",
    # América del Norte y Central
    "Mexico": "🇲🇽",
    "USA": "🇺🇸",
    "United States": "🇺🇸",
    "Canada": "🇨🇦",
    "Honduras": "🇭🇳",
    "Panama": "🇵🇦",
    "Costa Rica": "🇨🇷",
    "Jamaica": "🇯🇲",
    # Europa
    "France": "🇫🇷",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Spain": "🇪🇸",
    "Germany": "🇩🇪",
    "Italy": "🇮🇹",
    "Portugal": "🇵🇹",
    "Netherlands": "🇳🇱",
    "Belgium": "🇧🇪",
    "Croatia": "🇭🇷",
    "Serbia": "🇷🇸",
    "Switzerland": "🇨🇭",
    "Denmark": "🇩🇰",
    "Poland": "🇵🇱",
    "Austria": "🇦🇹",
    "Turkey": "🇹🇷",
    "Sweden": "🇸🇪",
    "Norway": "🇳🇴",
    "Slovakia": "🇸🇰",
    "Slovenia": "🇸🇮",
    "Czechia": "🇨🇿",
    "Czech Republic": "🇨🇿",
    "Greece": "🇬🇷",
    "Bosnia-Herzegovina": "🇧🇦",
    "Bosnia and Herzegovina": "🇧🇦",
    "Ukraine": "🇺🇦",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "Hungary": "🇭🇺",
    "Romania": "🇷🇴",
    "Albania": "🇦🇱",
    "Georgia": "🇬🇪",
    # África
    "Morocco": "🇲🇦",
    "Senegal": "🇸🇳",
    "Cameroon": "🇨🇲",
    "Ghana": "🇬🇭",
    "Nigeria": "🇳🇬",
    "Ivory Coast": "🇨🇮",
    "Egypt": "🇪🇬",
    "Tunisia": "🇹🇳",
    "Algeria": "🇩🇿",
    "South Africa": "🇿🇦",
    "DR Congo": "🇨🇩",
    "Congo DR": "🇨🇩",
    "Mali": "🇲🇱",
    "Burkina Faso": "🇧🇫",
    "Cape Verde": "🇨🇻",
    "Tanzania": "🇹🇿",
    "Uganda": "🇺🇬",
    "Zimbabwe": "🇿🇼",
    # Asia y Oceanía
    "Japan": "🇯🇵",
    "Korea Republic": "🇰🇷",
    "South Korea": "🇰🇷",
    "Saudi Arabia": "🇸🇦",
    "Iran": "🇮🇷",
    "Qatar": "🇶🇦",
    "Iraq": "🇮🇶",
    "Australia": "🇦🇺",
    "China": "🇨🇳",
    "Uzbekistan": "🇺🇿",
    "Jordan": "🇯🇴",
    "Indonesia": "🇮🇩",
    "New Zealand": "🇳🇿",
    "Oman": "🇴🇲",
    "Bahrain": "🇧🇭",
    "UAE": "🇦🇪",
    "United Arab Emirates": "🇦🇪",
    # Nombres exactos de la API que difieren
    "IR Iran": "🇮🇷",
    "Cabo Verde": "🇨🇻",
    "Curaçao": "🇨🇼",
    "Côte d'Ivoire": "🇨🇮",
    "Haiti": "🇭🇹",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
}

STADIUM_DATA = {
    "MetLife Stadium": {
        "city": "East Rutherford, NJ",
        "capacity": "82,500",
        "fact": "Uno de los estadios más grandes de la NFL, sede de la Final del Mundial.",
    },
    "AT&T Stadium": {
        "city": "Arlington, TX",
        "capacity": "80,000",
        "fact": "Conocido como 'Jerry World', tiene la pantalla de video más grande del mundo en un estadio.",
    },
    "SoFi Stadium": {
        "city": "Inglewood, CA",
        "capacity": "70,240",
        "fact": "El estadio más caro jamás construido, con un costo de $5.5 mil millones.",
    },
    "Levi's Stadium": {
        "city": "Santa Clara, CA",
        "capacity": "68,500",
        "fact": "Tiene más de 400 paneles solares en el techo que generan energía renovable.",
    },
    "Arrowhead Stadium": {
        "city": "Kansas City, MO",
        "capacity": "76,416",
        "fact": "Considerado el estadio más ruidoso de la NFL, con récord Guinness de 142.2 decibeles.",
    },
    "Mercedes-Benz Stadium": {
        "city": "Atlanta, GA",
        "capacity": "71,000",
        "fact": "Tiene un techo retráctil en forma de ojo y 360 grados de pantallas de video.",
    },
    "Gillette Stadium": {
        "city": "Foxborough, MA",
        "capacity": "65,878",
        "fact": "Casa de los New England Patriots, uno de los equipos más exitosos de la NFL.",
    },
    "Lincoln Financial Field": {
        "city": "Philadelphia, PA",
        "capacity": "69,796",
        "fact": "Filadelfia fue sede de la firma de la Declaración de Independencia de EE.UU.",
    },
    "Estadio Azteca": {
        "city": "Ciudad de México, México",
        "capacity": "87,523",
        "fact": "El único estadio en albergar dos finales de Copa del Mundo (1970 y 1986). Maradona marcó el 'Gol del Siglo' aquí.",
    },
    "Estadio Akron": {
        "city": "Guadalajara, México",
        "capacity": "49,850",
        "fact": "Inaugurado en 2010, es el estadio moderno más importante del occidente de México.",
    },
    "BC Place": {
        "city": "Vancouver, Canadá",
        "capacity": "54,500",
        "fact": "Primer estadio con techo retráctil de Canadá, sede de los Juegos Olímpicos de Invierno 2010.",
    },
    "BMO Field": {
        "city": "Toronto, Canadá",
        "capacity": "45,000",
        "fact": "Casa del Toronto FC, uno de los clubes más populares de la MLS.",
    },
}


def get_flag(team_name: str) -> str:
    """Retorna el emoji de bandera para un equipo."""
    if not team_name:
        return "🏳️"
    # Lookup exacto primero
    if team_name in FLAG_EMOJIS:
        return FLAG_EMOJIS[team_name]
    # Fallback: búsqueda case-insensitive
    team_lower = team_name.lower()
    for name, emoji in FLAG_EMOJIS.items():
        if name.lower() == team_lower:
            return emoji
    return "🏳️"


def get_round_label(round_str: str) -> str:
    """Convierte el round de la API a texto legible."""
    labels = {
        "group": "Fase de Grupos",
        "round-of-32": "Ronda de 32",
        "round-of-16": "Octavos de Final",
        "quarter-final": "Cuartos de Final",
        "semi-final": "Semifinal",
        "third-place": "Tercer Puesto",
        "final": "⭐ FINAL",
    }
    return labels.get(round_str, round_str.title())


def build_match_embed(match: dict, show_form: bool = False, home_form: list = None, away_form: list = None) -> discord.Embed:
    """Construye el embed de un partido individual."""
    kickoff = match["kickoff_utc"]
    if isinstance(kickoff, str):
        kickoff = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))

    home = match.get("home_team", "TBD")
    away = match.get("away_team", "TBD")
    status = match.get("status", "scheduled")

    home_flag = get_flag(home)
    away_flag = get_flag(away)

    # Color según estado
    if status == "live":
        color = COLOR_LIVE
    elif status == "finished":
        color = COLOR_SUCCESS
    else:
        color = COLOR_PRIMARY

    # Título
    round_label = get_round_label(match.get("round", ""))
    group = match.get("group_name", "")
    title_suffix = f"Grupo {group}" if group else round_label

    embed = discord.Embed(
        title=f"⚽ {home_flag} {home}  vs  {away} {away_flag}",
        color=color,
    )

    embed.add_field(name="🏆 Fase", value=f"{round_label} — {title_suffix}" if group else round_label, inline=True)
    embed.add_field(name="🕐 Horario", value=to_discord_timestamp(kickoff, 'F'), inline=False)

    # Estadio
    stadium = match.get("stadium", "Por confirmar")
    stadium_info = STADIUM_DATA.get(stadium, {})
    stadium_city = stadium_info.get("city", "")
    stadium_text = f"{stadium}"
    if stadium_city:
        stadium_text += f"\n📍 {stadium_city}"
    if "capacity" in stadium_info:
        stadium_text += f" · 👥 {stadium_info['capacity']}"
    embed.add_field(name="🏟️ Estadio", value=stadium_text, inline=False)

    # Dato curioso del estadio
    if stadium in STADIUM_DATA and STADIUM_DATA[stadium].get("fact"):
        embed.add_field(
            name="💡 Dato del estadio",
            value=STADIUM_DATA[stadium]["fact"],
            inline=False
        )

    # Resultado si el partido finalizó o está en curso
    if status in ("live", "finished") and match.get("score"):
        score = match["score"]
        if score.get("home") is not None:
            status_text = "🔴 EN VIVO" if status == "live" else "✅ Finalizado"
            embed.add_field(
                name=f"Resultado — {status_text}",
                value=f"## {score['home']} - {score['away']}",
                inline=False,
            )

    # Forma reciente
    if show_form and home_form is not None and away_form is not None:
        home_form_str = " ".join(home_form) if home_form else "Sin historial"
        away_form_str = " ".join(away_form) if away_form else "Sin historial"
        embed.add_field(
            name=f"📈 Forma reciente",
            value=f"{home_flag} **{home}**: {home_form_str}\n{away_flag} **{away}**: {away_form_str}",
            inline=False,
        )

    embed.set_footer(text=f"Partido #{match.get('match_number', '?')} · Mundial 2026")
    return embed


def build_daily_matches_embed(matches: list, date_str: str) -> discord.Embed:
    """Construye el embed diario con todos los partidos del día."""
    embed = discord.Embed(
        title=f"⚽ Partidos de hoy — {date_str}",
        description="¡Usá `/pronostico` en #mundial-chat para hacer tus predicciones!",
        color=COLOR_PRIMARY,
    )

    if not matches:
        embed.description = "😴 No hay partidos programados para hoy."
        return embed

    for match in matches:
        kickoff = match["kickoff_utc"]
        if isinstance(kickoff, str):
            kickoff = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))

        home = match.get("home_team", "TBD")
        away = match.get("away_team", "TBD")
        home_flag = get_flag(home)
        away_flag = get_flag(away)

        round_label = get_round_label(match.get("round", ""))
        group = match.get("group_name", "")
        phase = f"Grupo {group}" if group else round_label

        embed.add_field(
            name=f"{home_flag} {home}  vs  {away} {away_flag}",
            value=f"🕐 {to_discord_timestamp_tr(kickoff)}  |  🏆 {phase}  |  🏟️ {match.get('stadium', '?')}",
            inline=False,
        )

    embed.set_footer(text="Mundial 2026 · Los horarios se muestran en tu zona horaria local")
    return embed


def build_predictions_embed(match: dict, predictions: list, guild) -> discord.Embed:
    """Construye el embed del canal #pronosticos con todos los pronósticos de un partido."""
    kickoff = match["kickoff_utc"]
    if isinstance(kickoff, str):
        kickoff = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))

    home = match.get("home_team", "TBD")
    away = match.get("away_team", "TBD")
    home_flag = get_flag(home)
    away_flag = get_flag(away)

    embed = discord.Embed(
        title=f"🎯 Pronósticos — {home_flag} {home} vs {away} {away_flag}",
        description=f"📅 {to_discord_timestamp(kickoff, 'F')}\n⏳ Cierre {to_discord_timestamp(kickoff, 'R')}",
        color=COLOR_WARNING,
    )

    if not predictions:
        embed.add_field(name="Sin pronósticos aún", value="¡Sé el primero! Usá `/pronostico` en #mundial-chat", inline=False)
    else:
        pred_lines = []
        for pred in predictions:
            username = pred.get("username", "Usuario")
            h = pred.get("predicted_home", "?")
            a = pred.get("predicted_away", "?")
            pred_lines.append(f"**{username}**: {home} {h} - {a} {away}")

        embed.add_field(
            name=f"📋 Pronósticos ({len(predictions)})",
            value="\n".join(pred_lines),
            inline=False,
        )

    embed.set_footer(text=f"Mundial 2026 · Partido #{match.get('match_number', '?')}")
    return embed


def build_result_embed(match: dict, predictions: list, points_map: dict) -> discord.Embed:
    """Construye el embed de resultado con quién acertó qué."""
    home = match.get("home_team", "TBD")
    away = match.get("away_team", "TBD")
    home_flag = get_flag(home)
    away_flag = get_flag(away)
    score = match.get("score", {})
    h_score = score.get("home", 0)
    a_score = score.get("away", 0)

    embed = discord.Embed(
        title=f"🏁 Resultado Final",
        description=f"## {home_flag} {home}  {h_score} - {a_score}  {away} {away_flag}",
        color=COLOR_SUCCESS,
    )

    if predictions:
        winners = []
        others = []
        for pred in predictions:
            username = pred.get("username", "Usuario")
            ph = pred.get("predicted_home", "?")
            pa = pred.get("predicted_away", "?")
            pts = points_map.get(pred["user_id"], 0)

            if pts > 0:
                winners.append(f"✅ **{username}**: pronosticó {ph}-{pa} → +{pts}pts")
            else:
                others.append(f"❌ **{username}**: pronosticó {ph}-{pa}")

        if winners:
            embed.add_field(name="🎉 Acertaron", value="\n".join(winners), inline=False)
        if others:
            embed.add_field(name="😔 No acertaron", value="\n".join(others), inline=False)
    else:
        embed.add_field(name="Sin pronósticos", value="Nadie pronosticó este partido.", inline=False)

    embed.set_footer(text="Mundial 2026")
    return embed


def build_leaderboard_embed(users: list) -> discord.Embed:
    """Construye el embed del ranking general."""
    embed = discord.Embed(
        title="🏆 Tabla de Puntos — Mundial 2026",
        color=COLOR_GOLD,
    )

    if not users:
        embed.description = "Aún no hay puntos registrados."
        return embed

    medals = ["🥇", "🥈", "🥉"]
    lines = []

    for i, user in enumerate(users):
        medal = medals[i] if i < 3 else f"`{i+1}.`"
        username = user.get("username", "Usuario")
        points = user.get("total_points", 0)
        streak = user.get("streak", 0)
        correct = user.get("correct_predictions", 0)
        total = user.get("total_predictions", 0)
        pct = f"{int(correct/total*100)}%" if total > 0 else "0%"
        streak_str = f" 🔥{streak}" if streak >= 3 else ""

        lines.append(f"{medal} **{username}** — {points}pts | {pct} aciertos{streak_str}")

    embed.description = "\n".join(lines)
    embed.set_footer(text=f"Mundial 2026 · Actualizado: {datetime.utcnow().strftime('%H:%M UTC')}")
    return embed


def build_standings_embed(standings: list, group_name: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 Tabla — Grupo {group_name.upper()}",
        color=COLOR_PRIMARY,
    )

    lines = ["Pos  Equipo             PJ  G  E  P  GF GA Pts"]
    lines.append("─" * 47)

    for i, team in enumerate(standings):
        name = team.get("team", "?")
        pj  = team.get("played", 0)
        g   = team.get("won", 0)
        e   = team.get("drawn", 0)
        p   = team.get("lost", 0)
        gf  = team.get("goals_for", 0)
        ga  = team.get("goals_against", 0)
        pts = team.get("points", 0)

        qualifier = "→" if i < 2 else "  "
        lines.append(
            f"{qualifier}{i+1}.  {name:<17}  {pj}   {g}  {e}  {p}   {gf}  {ga}   {pts}"
        )

    embed.description = "```\n" + "\n".join(lines) + "\n```"

    flag_list = []
    for i, team in enumerate(standings):
        name = team.get("team", "?")
        flag = get_flag(name)
        qualifier = "→" if i < 2 else "  "
        flag_list.append(f"{qualifier} {flag} {name}")

    embed.set_footer(text="→ Clasifican a la siguiente ronda · Mundial 2026")
    return embed
