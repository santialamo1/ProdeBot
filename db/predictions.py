from datetime import datetime
import pytz


async def get_prediction(db, user_id: int, match_id: str):
    """Retorna el pronóstico de un usuario para un partido."""
    return await db.predictions.find_one({
        "user_id": str(user_id),
        "match_id": match_id,
    })


async def get_predictions_for_match(db, match_id: str) -> list:
    """Retorna todos los pronósticos para un partido."""
    cursor = db.predictions.find({"match_id": match_id})
    return await cursor.to_list(length=None)


async def upsert_prediction(db, user_id: int, match_id: str, home: int, away: int, penalties: str = None):
    """Inserta o actualiza el pronóstico de un usuario para un partido."""
    await db.predictions.update_one(
        {"user_id": str(user_id), "match_id": match_id},
        {"$set": {
            "user_id": str(user_id),
            "match_id": match_id,
            "predicted_home": home,
            "predicted_away": away,
            "predicted_penalties": penalties,
            "submitted_at": datetime.now(pytz.utc),
            "points_earned": None,
        }},
        upsert=True,
    )


async def set_prediction_points(db, user_id: int, match_id: str, points: int, actual_home: int = None, actual_away: int = None):
    """Asigna los puntos ganados a un pronóstico y guarda el score usado."""
    update = {"points_earned": points}
    if actual_home is not None and actual_away is not None:
        update["score_usado"] = {"home": actual_home, "away": actual_away}
    await db.predictions.update_one(
        {"user_id": str(user_id), "match_id": match_id},
        {"$set": update}
    )


async def get_user_predictions(db, user_id: int) -> list:
    """Retorna todos los pronósticos de un usuario con info del partido."""
    pipeline = [
        {"$match": {"user_id": str(user_id)}},
        {"$lookup": {
            "from": "matches",
            "localField": "match_id",
            "foreignField": "match_id",
            "as": "match",
        }},
        {"$unwind": "$match"},
        {"$sort": {"match.kickoff_utc": -1}},
    ]
    cursor = db.predictions.aggregate(pipeline)
    return await cursor.to_list(length=None)


async def get_quiniela(db, user_id: int, group_name: str):
    """Retorna la quiniela de un usuario para un grupo."""
    return await db.quiniela.find_one({
        "user_id": str(user_id),
        "group_name": group_name.upper(),
    })


async def get_user_quiniela(db, user_id: int) -> list:
    """Retorna todas las quinielas de un usuario."""
    cursor = db.quiniela.find({"user_id": str(user_id)}).sort("group_name", 1)
    return await cursor.to_list(length=None)


async def save_quiniela(db, user_id: int, group_name: str, team1: str, team2: str):
    """Guarda la predicción de clasificados de un grupo."""
    await db.quiniela.update_one(
        {"user_id": str(user_id), "group_name": group_name.upper()},
        {"$set": {
            "user_id": str(user_id),
            "group_name": group_name.upper(),
            "team1": team1,
            "team2": team2,
            "submitted_at": datetime.now(pytz.utc),
            "points_earned": None,
            "resolved": False,
        }},
        upsert=True,
    )


async def resolve_quiniela(db, group_name: str, actual_team1: str, actual_team2: str):
    """
    Resuelve la quiniela de un grupo al finalizar la fase de grupos.
    Calcula y asigna puntos a cada usuario.
    """
    import config

    cursor = db.quiniela.find({
        "group_name": group_name.upper(),
        "resolved": False,
    })
    quinielas = await cursor.to_list(length=None)

    actual_set = {actual_team1.lower(), actual_team2.lower()}

    for q in quinielas:
        predicted_set = {q["team1"].lower(), q["team2"].lower()}
        matches = len(predicted_set & actual_set)

        if matches == 2:
            points = config.POINTS_QUINIELA_BOTH
        elif matches == 1:
            points = config.POINTS_QUINIELA_ONE
        else:
            points = 0

        await db.quiniela.update_one(
            {"_id": q["_id"]},
            {"$set": {"points_earned": points, "resolved": True}}
        )

        if points > 0:
            await db.users.update_one(
                {"user_id": q["user_id"]},
                {"$inc": {"total_points": points}},
                upsert=True,
            )
