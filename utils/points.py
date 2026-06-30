import config


def calculate_points(
    predicted_home: int,
    predicted_away: int,
    actual_home: int,
    actual_away: int,
    stage: str,
    streak: int,
    predicted_penalties: str = None,
    actual_penalty_winner: str = None,
) -> tuple[int, str, bool]:
    """
    Calcula los puntos ganados por un pronóstico.

    Retorna una tupla (puntos, descripción, fue_exacto).
    fue_exacto se usa para actualizar la racha — la racha solo cuenta
    aciertos de resultado exacto, no solo acertar el ganador.

    Niveles:
    - Resultado exacto: 3pts
    - Ganador correcto: 1pt
    - Ganador de penales acertado (cuando el resultado real fue empate y
      el partido se definió por penales, sin acertar ganador en los 90min): 1pt
    - Sin acierto: 0pts

    Bonuses:
    - Fase avanzada (cuartos, semis, final): x2
    - Racha de 3+ resultados exactos consecutivos: +1pt

    El pronóstico de penales es independiente del resultado pronosticado:
    el usuario puede haber predicho cualquier marcador (ej. 2-1) y aun así
    elegir un ganador de penales por si el partido real termina empatado.
    """
    import logging
    log = logging.getLogger("worldcup-bot.points")

    base_points = 0
    description_parts = []

    # Determinar ganador real
    if actual_home > actual_away:
        actual_winner = "home"
    elif actual_away > actual_home:
        actual_winner = "away"
    else:
        actual_winner = "draw"

    # Determinar ganador pronosticado
    if predicted_home > predicted_away:
        predicted_winner = "home"
    elif predicted_away > predicted_home:
        predicted_winner = "away"
    else:
        predicted_winner = "draw"

    correct_winner = predicted_winner == actual_winner

    # Caso especial: partido fue a penales (empate en 90min)
    went_to_penalties = actual_penalty_winner is not None

    if not correct_winner:
        # El usuario no acertó el resultado/ganador en los 90 minutos.
        # Si el partido real terminó empatado y se definió por penales,
        # y el usuario había elegido un ganador de penales que coincide
        # con el resultado real, le damos +1pt. Esto es independiente
        # de qué marcador haya pronosticado.
        if went_to_penalties and predicted_penalties and actual_penalty_winner:
            if predicted_penalties.lower() == actual_penalty_winner.lower():
                log.info(
                    f"[POINTS] pred={predicted_home}-{predicted_away} real={actual_home}-{actual_away} "
                    f"-> empate real, usuario acertó ganador de penales ({predicted_penalties}), +1pt"
                )
                return 1, "✅ Ganador por penales (+1pt)", False

        log.info(f"[POINTS] pred={predicted_home}-{predicted_away} real={actual_home}-{actual_away} -> sin acierto, streak ignorado")
        return 0, "❌ Sin acierto", False

    # Acertó el ganador/empate
    base_points = config.POINTS_WINNER
    description_parts.append(f"✅ Ganador (+{config.POINTS_WINNER}pt)")

    # Verificar resultado exacto
    exacto = predicted_home == actual_home and predicted_away == actual_away
    if exacto:
        base_points = config.POINTS_EXACT
        description_parts = [f"🎯 Resultado exacto (+{config.POINTS_EXACT}pts)"]

        # Si fue a penales y el usuario predijo correctamente quién gana → ya tiene 3pts (no bonus extra)
        if went_to_penalties and predicted_penalties:
            if predicted_penalties.lower() == actual_penalty_winner.lower():
                description_parts.append("🎯 Penales acertados (incluido en los 3pts)")
            else:
                description_parts.append("❌ Penales errados")

    # Multiplicador de fase
    multiplier = 1
    if stage and any(s in stage.lower() for s in config.MULTIPLIER_STAGES):
        multiplier = config.STAGE_MULTIPLIER
        description_parts.append(f"x{multiplier} fase eliminatoria")

    total = base_points * multiplier

    # Bonus de racha — solo aplica si el usuario viene de 3+ resultados EXACTOS consecutivos
    streak_bonus = 0
    if streak >= config.STREAK_MIN:
        streak_bonus = config.POINTS_STREAK_BONUS
        description_parts.append(f"🔥 Bonus racha (+{streak_bonus}pt)")

    total += streak_bonus

    description = " | ".join(description_parts)

    log.info(
        f"[POINTS] pred={predicted_home}-{predicted_away} real={actual_home}-{actual_away} "
        f"exacto={exacto} penales={went_to_penalties} base={base_points} multiplier={multiplier} "
        f"streak_usado={streak} streak_bonus={streak_bonus} TOTAL={total}"
    )

    return total, description, exacto


def get_winner(home_score: int, away_score: int) -> str:
    """Retorna 'home', 'away' o 'draw'."""
    if home_score > away_score:
        return "home"
    elif away_score > home_score:
        return "away"
    return "draw"


def format_score(home: int, away: int) -> str:
    """Formatea el marcador. Ej: '2 - 1'"""
    return f"{home} - {away}"
