import aiohttp
import logging
from datetime import datetime
import pytz

import config
from db.matches import upsert_match

log = logging.getLogger("worldcup-bot.sync")


def parse_match(raw: dict) -> dict:
    """
    Convierte la respuesta de la API al formato interno de MongoDB.
    """
    kickoff_str = raw.get("kickoff_utc", "")
    kickoff_dt = None
    if kickoff_str:
        try:
            kickoff_dt = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    return {
        "match_id": str(raw.get("id", "")),
        "match_number": raw.get("match_number"),
        "round": raw.get("round", "group"),
        "group_name": raw.get("group_name", ""),
        "home_team": raw.get("home_team", "TBD"),
        "away_team": raw.get("away_team", "TBD"),
        "stadium": raw.get("stadium", ""),
        "kickoff_utc": kickoff_dt,
        "status": raw.get("status", "scheduled"),
        "score": {
            "home": raw.get("home_score"),
            "away": raw.get("away_score"),
        },
        "last_updated": datetime.now(pytz.utc),
    }


async def fetch_all_matches() -> list:
    """Hace un GET /matches a la API y retorna la lista de partidos."""
    headers = {"Authorization": f"Bearer {config.WC2026_API_KEY}"}
    url = f"{config.WC2026_BASE_URL}/matches"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                log.error(f"API respondió con status {resp.status}")
                return []
            data = await resp.json()
            # La API puede retornar lista directa o dict con key "data"
            if isinstance(data, list):
                return data
            return data.get("data", data.get("matches", []))


async def fetch_live_scores() -> list:
    """Hace un GET /matches?status=live para obtener partidos en curso."""
    headers = {"Authorization": f"Bearer {config.WC2026_API_KEY}"}
    url = f"{config.WC2026_BASE_URL}/matches"
    params = {"status": "live"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                log.error(f"API live respondió con status {resp.status}")
                return []
            data = await resp.json()
            if isinstance(data, list):
                return data
            return data.get("data", data.get("matches", []))


async def sync_fixture(bot):
    """
    Tarea principal de sincronización.
    Compara los datos de la API con MongoDB y actualiza solo lo que cambió.
    """
    log.info("Iniciando sync del fixture con la API...")

    try:
        raw_matches = await fetch_all_matches()
    except Exception as e:
        log.error(f"Error al conectar con la API: {e}")
        return

    if not raw_matches:
        log.warning("La API no retornó partidos")
        return

    updated = 0
    for raw in raw_matches:
        match_data = parse_match(raw)
        if not match_data["match_id"]:
            continue

        # Comparar con lo que tenemos en DB
        existing = await bot.db.matches.find_one({"match_id": match_data["match_id"]})

        if existing is None:
            await upsert_match(bot.db, match_data)
            updated += 1
        else:
            # Solo actualizar si algo cambió (status o score)
            needs_update = (
                existing.get("status") != match_data["status"]
                or existing.get("score", {}).get("home") != match_data["score"]["home"]
                or existing.get("score", {}).get("away") != match_data["score"]["away"]
                or existing.get("home_team") != match_data["home_team"]
                or existing.get("away_team") != match_data["away_team"]
            )
            if needs_update:
                await upsert_match(bot.db, match_data)
                updated += 1

    log.info(f"Sync completado: {len(raw_matches)} partidos procesados, {updated} actualizados")