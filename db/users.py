from datetime import datetime
import pytz


async def get_user(db, user_id: int) -> dict:
    """Retorna el perfil de un usuario, lo crea si no existe."""
    user = await db.users.find_one({"user_id": str(user_id)})
    return user


async def ensure_user(db, user_id: int, username: str) -> dict:
    """Crea el usuario si no existe y retorna su perfil."""
    await db.users.update_one(
        {"user_id": str(user_id)},
        {"$setOnInsert": {
            "user_id": str(user_id),
            "username": username,
            "total_points": 0,
            "champion_pick": None,
            "champion_points_earned": None,
            "streak": 0,
            "max_streak": 0,
            "correct_predictions": 0,
            "total_predictions": 0,
            "joined_at": datetime.now(pytz.utc),
        }},
        upsert=True,
    )
    return await db.users.find_one({"user_id": str(user_id)})


async def update_username(db, user_id: int, username: str):
    """Actualiza el username del usuario."""
    await db.users.update_one(
        {"user_id": str(user_id)},
        {"$set": {"username": username}}
    )


async def add_points(db, user_id: int, points: int):
    """Suma puntos al usuario."""
    await db.users.update_one(
        {"user_id": str(user_id)},
        {"$inc": {"total_points": points}}
    )


async def update_streak(db, user_id: int, correct: bool):
    """
    Actualiza la racha del usuario.
    'correct' debe ser True solo cuando el pronóstico fue RESULTADO EXACTO
    (no alcanza con acertar el ganador). Si no fue exacto, resetea a 0.
    Retorna la racha actual después de la actualización.
    """
    user = await db.users.find_one({"user_id": str(user_id)})
    if not user:
        return 0

    current_streak = user.get("streak", 0)
    max_streak = user.get("max_streak", 0)

    if correct:
        new_streak = current_streak + 1
        new_max = max(max_streak, new_streak)
        await db.users.update_one(
            {"user_id": str(user_id)},
            {"$set": {
                "streak": new_streak,
                "max_streak": new_max,
            },
            "$inc": {"correct_predictions": 1, "total_predictions": 1}}
        )
        return new_streak
    else:
        await db.users.update_one(
            {"user_id": str(user_id)},
            {"$set": {"streak": 0},
             "$inc": {"total_predictions": 1}}
        )
        return 0


async def set_champion_pick(db, user_id: int, team: str):
    """Guarda la predicción del campeón de un usuario."""
    await db.users.update_one(
        {"user_id": str(user_id)},
        {"$set": {
            "champion_pick": team,
            "champion_pick_date": datetime.now(pytz.utc),
        }}
    )


async def get_leaderboard(db, limit: int = 10) -> list:
    """Retorna el ranking general de usuarios por puntos."""
    cursor = db.users.find(
        {"total_points": {"$gt": 0}}
    ).sort("total_points", -1).limit(limit)
    return await cursor.to_list(length=None)


async def get_user_rank(db, user_id: int) -> tuple[int, int]:
    """
    Retorna la posición del usuario en el ranking y el total de participantes.
    """
    user = await db.users.find_one({"user_id": str(user_id)})
    if not user:
        return 0, 0

    user_points = user.get("total_points", 0)

    # Usuarios con más puntos que yo
    rank = await db.users.count_documents(
        {"total_points": {"$gt": user_points}}
    )
    total = await db.users.count_documents({"total_points": {"$gt": 0}})

    return rank + 1, total
