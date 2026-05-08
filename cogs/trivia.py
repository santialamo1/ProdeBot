import discord
from discord import app_commands
from discord.ext import commands
import openai
import json
import asyncio
import logging
from datetime import datetime
import pytz

import config

log = logging.getLogger("worldcup-bot.trivia")

OPTION_EMOJIS = ["🇦", "🇧", "🇨", "🇩"]
OPTION_LETTERS = ["A", "B", "C", "D"]

TRIVIA_TIMEOUT = 300  # 5 minutos
TRIVIA_USER_COOLDOWN_HOURS = 1  # Cooldown por usuario para /trivia

TRIVIA_SYSTEM_PROMPT = """Sos un generador de trivia sobre la Copa del Mundo FIFA (1930-2022).

Antes de generar la pregunta, seguí estos pasos internamente:

PASO 1 — Tirá un dado mental del 1 al 3 para la dificultad:
  1 = FÁCIL: dato que cualquier seguidor del fútbol conoce
      Ejemplos: campeón de un Mundial famoso, sede de un torneo, goleador histórico conocido
  2 = MEDIA: dato que sabe quien sigue el fútbol con atención
      Ejemplos: resultado de una final, máximo goleador de un torneo específico, jugador Balón de Oro mundialista
  3 = DIFÍCIL: dato muy específico que solo saben los fanáticos
      Ejemplos: cantidad de tarjetas en un partido, jugador expulsado en una final, récord obscuro, dato estadístico preciso

PASO 2 — Tirá un dado mental del 1 al 10 para el tema:
  1 = Campeones y finalistas
  2 = Goleadores (de torneos o históricos)
  3 = Resultados de partidos (finales, semis, goleadas)
  4 = Sedes y países organizadores
  5 = Jugadores icónicos y sus logros
  6 = Disciplina (tarjetas, expulsiones, penales)
  7 = Porteros y récords defensivos
  8 = Curiosidades y datos raros verificables
  9 = Premios individuales (Balón de Oro, Guante de Oro, Bota de Oro)
  10 = Selecciones (rachas, récords por país)

PASO 3 — Construí la pregunta según la combinación que salió. Si no estás seguro del dato exacto para esa combinación, tirá de nuevo mentalmente.

Devolvé ÚNICAMENTE este JSON sin texto adicional ni markdown:
{
  "pregunta": "la pregunta",
  "opciones": ["opcion A", "opcion B", "opcion C", "opcion D"],
  "respuesta_correcta": 0,
  "explicacion": "por qué es correcta con contexto preciso",
  "tema": "el tema que elegiste del paso 2 en 2-3 palabras"
}

REGLAS FINALES:
- La respuesta correcta debe ser 100% verificable y correcta
- Las opciones incorrectas deben ser del mismo tipo que la correcta (otros países, jugadores, números)
- Nunca mezcles datos de distintas ediciones del Mundial
- Todo en español"""


class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.openai_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self._active_trivia = False
        self._last_trivia_time = None  # Cooldown global para /trivia

    async def _generate_question(self) -> dict | None:
        """Genera una pregunta de trivia usando OpenAI."""
        try:
            cursor = self.bot.db.trivia.find({}).sort("posted_at", -1).limit(20)
            recent = await cursor.to_list(length=None)
            recent_questions = [r.get("pregunta", "") for r in recent]

            # Ultimas 20 preguntas con su respuesta correcta
            cursor_prev = self.bot.db.trivia.find(
                {}, {"pregunta": 1, "opciones": 1, "respuesta_correcta": 1}
            ).sort("posted_at", -1).limit(20)
            prev_docs = await cursor_prev.to_list(length=None)

            user_prompt = "Genera una nueva pregunta de trivia sobre el Mundial de futbol."

            if prev_docs:
                prev_preguntas = []
                prev_temas = []
                for doc in prev_docs:
                    pregunta = doc.get("pregunta", "")
                    tema = doc.get("tema", "")
                    if pregunta:
                        prev_preguntas.append(f"- {pregunta}")
                    if tema:
                        prev_temas.append(tema)

                if prev_preguntas:
                    preguntas_str = "\n".join(prev_preguntas[:15])
                    user_prompt += f"""

Estas son las preguntas ya realizadas — NO las reformules ni hagas preguntas sobre el mismo hecho aunque estén redactadas diferente:
{preguntas_str}

Elige un hecho o dato del Mundial completamente distinto a los de la lista."""

                if prev_temas:
                    temas_str = ", ".join(list(dict.fromkeys(prev_temas))[:15])
                    user_prompt += f"""

Temas ya cubiertos recientemente (elegí uno diferente): {temas_str}"""

            message = await self.openai_client.chat.completions.create(
                model="gpt-4o",
                max_tokens=500,
                messages=[
                    {"role": "system", "content": TRIVIA_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )

            raw = message.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            question = json.loads(raw)

            assert "pregunta" in question
            assert "opciones" in question and len(question["opciones"]) == 4
            assert "respuesta_correcta" in question
            assert 0 <= question["respuesta_correcta"] <= 3
            assert "explicacion" in question
            # tema es opcional pero lo usamos si viene
            if "tema" not in question:
                question["tema"] = ""

            return question

        except (json.JSONDecodeError, AssertionError, KeyError) as e:
            log.error(f"Error parseando pregunta de trivia: {e}")
            return None
        except Exception as e:
            log.error(f"Error generando trivia con OpenAI: {e}")
            return None

    async def post_trivia_question(self):
        """Genera y postea una pregunta. Espera 5 min y revela la respuesta."""
        if self._active_trivia:
            log.info("Trivia ya activa, saltando")
            return

        channel = self.bot.get_channel(config.CHANNEL_TRIVIA)
        if not channel:
            log.error(f"Canal de trivia no encontrado (ID: {config.CHANNEL_TRIVIA})")
            return

        log.info("Generando pregunta de trivia...")
        question = await self._generate_question()
        if not question:
            log.error("No se pudo generar la pregunta de trivia")
            return

        self._active_trivia = True
        self._last_trivia_time = datetime.now(pytz.utc)

        try:
            embed = discord.Embed(
                title="🧠 ¡Trivia Mundial!",
                description=f"**{question['pregunta']}**",
                color=0x9B59B6,
            )

            options_text = ""
            for i, (emoji, option) in enumerate(zip(OPTION_EMOJIS, question["opciones"])):
                options_text += f"{emoji} **{OPTION_LETTERS[i]}.** {option}\n"

            embed.add_field(name="Opciones", value=options_text, inline=False)
            embed.add_field(
                name="⏳ Tiempo",
                value=f"Tenés **{TRIVIA_TIMEOUT // 60} minutos** para responder reaccionando con el emoji de tu opción.",
                inline=False,
            )
            embed.set_footer(text="Mundial 2026 · Trivia — Solo por diversión, sin puntos de prode")

            msg = await channel.send(embed=embed)

            # Guardar en DB
            await self.bot.db.trivia.insert_one({
                "message_id": str(msg.id),
                "pregunta": question["pregunta"],
                "opciones": question["opciones"],
                "respuesta_correcta": question["respuesta_correcta"],
                "explicacion": question["explicacion"],
                "tema": question.get("tema", ""),
                "posted_at": datetime.now(pytz.utc),
                "ganadores": [],
            })

            for emoji in OPTION_EMOJIS[:len(question["opciones"])]:
                await msg.add_reaction(emoji)

            log.info(f"Trivia posteada: {question['pregunta'][:50]}...")
            await asyncio.sleep(TRIVIA_TIMEOUT)
            await self._reveal_answer(channel, msg, question)

        finally:
            self._active_trivia = False

    async def _reveal_answer(self, channel, original_msg: discord.Message, question: dict):
        """Revela la respuesta y actualiza los aciertos en DB."""
        try:
            msg = await channel.fetch_message(original_msg.id)
        except discord.NotFound:
            return
        except discord.HTTPException as e:
            log.error(f"Error al obtener mensaje de trivia: {e} — reseteando cooldown para reintento")
            self._last_trivia_time = None
            return

        correct_idx = question["respuesta_correcta"]
        correct_emoji = OPTION_EMOJIS[correct_idx]

        # Mapear todos los emojis usados por cada usuario con delay para evitar rate limit
        user_reactions: dict[str, set] = {}
        all_reactors = set()

        for reaction in msg.reactions:
            emoji = str(reaction.emoji)
            if emoji not in OPTION_EMOJIS:
                continue
            try:
                await asyncio.sleep(0.5)  # Delay entre reacciones para evitar rate limit
                async for user in reaction.users():
                    if user.bot:
                        continue
                    uid = str(user.id)
                    all_reactors.add(uid)
                    if uid not in user_reactions:
                        user_reactions[uid] = set()
                    user_reactions[uid].add(emoji)
            except discord.HTTPException as e:
                log.warning(f"Rate limit al leer reacciones: {e} — continuando")
                self._last_trivia_time = None
                continue

        # Ganadores: solo reaccionaron con el emoji correcto
        winners = []
        for uid, emojis in user_reactions.items():
            if emojis == {correct_emoji}:
                member = msg.guild.get_member(int(uid)) if msg.guild else None
                username = member.display_name if member else uid
                winners.append({"user_id": uid, "username": username})

        # Actualizar DB
        for winner in winners:
            await self.bot.db.trivia_ranking.update_one(
                {"user_id": winner["user_id"]},
                {"$inc": {"aciertos": 1},
                 "$set": {"username": winner["username"]},
                 "$setOnInsert": {"participaciones": 0}},
                upsert=True,
            )

        for user_id in all_reactors:
            await self.bot.db.trivia_ranking.update_one(
                {"user_id": user_id},
                {"$inc": {"participaciones": 1}},
                upsert=True,
            )

        # Guardar ganadores en el documento de trivia
        await self.bot.db.trivia.update_one(
            {"message_id": str(original_msg.id)},
            {"$set": {"ganadores": [w["username"] for w in winners]}}
        )

        # Embed de respuesta
        embed = discord.Embed(
            title="✅ ¡Tiempo! — Respuesta revelada",
            description=f"**{question['pregunta']}**",
            color=0x27AE60,
        )

        options_text = ""
        for i, (emoji, option) in enumerate(zip(OPTION_EMOJIS, question["opciones"])):
            if i == correct_idx:
                options_text += f"✅ {emoji} **{OPTION_LETTERS[i]}.** {option} ← Correcta\n"
            else:
                options_text += f"❌ {emoji} {OPTION_LETTERS[i]}. ~~{option}~~\n"

        embed.add_field(name="Opciones", value=options_text, inline=False)
        embed.add_field(name="💡 Explicación", value=question["explicacion"], inline=False)

        if winners:
            embed.add_field(
                name=f"🎉 Acertaron ({len(winners)})",
                value=" ".join([w["username"] for w in winners[:20]]),
                inline=False,
            )
        else:
            embed.add_field(
                name="😔 Nadie acertó",
                value="¡Difícil esta! Ya viene otra.",
                inline=False,
            )

        embed.set_footer(text="Mundial 2026 · Trivia — Usá /trivia_ranking para ver la tabla")
        await channel.send(embed=embed)
        log.info(f"Trivia resuelta: {len(winners)} ganadores")

    # ──────────────────────────────────────────────────────────
    #   /trivia — cooldown de 1 hora global
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="trivia", description="Lanzar una pregunta de trivia")
    async def trivia_manual(self, interaction: discord.Interaction):
        # Solo en canal de trivia
        if interaction.channel_id != config.CHANNEL_TRIVIA:
            await interaction.response.send_message(
                f"Este comando solo se puede usar en <#{config.CHANNEL_TRIVIA}>",
                ephemeral=True,
            )
            return

        # Trivia ya activa
        if self._active_trivia:
            await interaction.response.send_message(
                "⚠️ Ya hay una trivia activa, esperá que termine.",
                ephemeral=True,
            )
            return

        # Cooldown global de 1 hora
        if self._last_trivia_time:
            elapsed = (datetime.now(pytz.utc) - self._last_trivia_time).total_seconds() / 3600
            remaining = TRIVIA_USER_COOLDOWN_HOURS - elapsed
            if remaining > 0:
                mins = int(remaining * 60)
                await interaction.response.send_message(
                    f"⏳ La próxima trivia estará disponible en **{mins} minutos**.",
                    ephemeral=True,
                )
                return

        await interaction.response.send_message(
            "🧠 Generando pregunta de trivia...",
            ephemeral=True,
        )
        asyncio.create_task(self.post_trivia_question())

    # ──────────────────────────────────────────────────────────
    #   /trivia_ranking
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="trivia_ranking", description="Ver el ranking de aciertos de trivia")
    async def trivia_ranking(self, interaction: discord.Interaction):
        await interaction.response.defer()

        cursor = self.bot.db.trivia_ranking.find().sort("aciertos", -1).limit(15)
        users = await cursor.to_list(length=None)

        if not users:
            await interaction.followup.send(
                "📭 Todavía no hay aciertos registrados en la trivia.",
            )
            return

        embed = discord.Embed(
            title="🧠 Ranking de Trivia — Mundial 2026",
            color=0x9B59B6,
        )

        medals = ["🥇", "🥈", "🥉"]
        lines = []

        for i, user in enumerate(users):
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            username = user.get("username", "Usuario")
            aciertos = user.get("aciertos", 0)
            participaciones = user.get("participaciones", 0)
            pct = f"{int(aciertos / participaciones * 100)}%" if participaciones > 0 else "0%"
            lines.append(f"{medal} **{username}** — {aciertos} aciertos | {pct} ({participaciones} respondidas)")

        embed.description = "\n".join(lines)
        embed.set_footer(text="Mundial 2026 · Trivia — Solo por diversión")
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Trivia(bot))
