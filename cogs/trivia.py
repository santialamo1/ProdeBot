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

# Emojis para las opciones
OPTION_EMOJIS = ["🇦", "🇧", "🇨", "🇩"]
OPTION_LETTERS = ["A", "B", "C", "D"]

# Tiempo en segundos para responder
TRIVIA_TIMEOUT = 300  # 5 minutos

TRIVIA_SYSTEM_PROMPT = """Sos un experto en historia y datos del fútbol mundial y la Copa del Mundo FIFA.
Tu tarea es generar preguntas de trivia interesantes, variadas y precisas sobre el Mundial de fútbol.

Generá UNA pregunta de trivia en el siguiente formato JSON exacto, sin texto adicional, sin markdown:
{
  "pregunta": "texto de la pregunta",
  "opciones": ["opcion A", "opcion B", "opcion C", "opcion D"],
  "respuesta_correcta": 0,
  "explicacion": "breve explicación de por qué es correcta (máximo 2 oraciones)"
}

Donde "respuesta_correcta" es el índice (0-3) de la opción correcta en el array "opciones".

Reglas:
- Las preguntas deben ser sobre historia del Mundial FIFA (1930-2022)
- Variá los temas: goleadores, campeones, estadios, jugadores históricos, récords, curiosidades
- Las opciones incorrectas deben ser plausibles pero claramente incorrectas para alguien que sabe
- La dificultad debe ser media: ni muy obvia ni muy oscura
- Escribí todo en español"""


class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.openai_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self._active_trivia = False  # Evita que se lancen dos trivias simultáneas

    async def _generate_question(self) -> dict | None:
        """Genera una pregunta de trivia usando Claude."""
        try:
            # Obtener preguntas ya usadas para evitar repetición
            cursor = self.bot.db.trivia.find({}).sort("posted_at", -1).limit(20)
            recent = await cursor.to_list(length=None)
            recent_questions = [r.get("pregunta", "") for r in recent]

            user_prompt = "Generá una nueva pregunta de trivia sobre el Mundial de fútbol."
            if recent_questions:
                avoid = "\n- ".join(recent_questions[:10])
                user_prompt += f"\n\nEvitá preguntas similares a estas ya usadas:\n- {avoid}"

            message = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=500,
                messages=[
                    {"role": "system", "content": TRIVIA_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )

            raw = message.choices[0].message.content.strip()
            # Limpiar posibles backticks de markdown
            raw = raw.replace("```json", "").replace("```", "").strip()
            question = json.loads(raw)

            # Validar estructura
            assert "pregunta" in question
            assert "opciones" in question and len(question["opciones"]) == 4
            assert "respuesta_correcta" in question
            assert 0 <= question["respuesta_correcta"] <= 3
            assert "explicacion" in question

            return question

        except (json.JSONDecodeError, AssertionError, KeyError) as e:
            log.error(f"Error parseando pregunta de trivia: {e}")
            return None
        except Exception as e:
            log.error(f"Error generando trivia con OpenAI: {e}")
            return None

    async def post_trivia_question(self):
        """
        Genera y postea una pregunta de trivia en el canal correspondiente.
        Espera 5 minutos, luego revela la respuesta.
        """
        if self._active_trivia:
            log.info("Trivia ya activa, saltando esta ejecución")
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

        try:
            # Construir el embed de la pregunta
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
            embed.set_footer(text="Mundial 2026 · Trivia — Solo por diversión, sin puntos")

            msg = await channel.send(embed=embed)

            # Guardar en DB
            await self.bot.db.trivia.insert_one({
                "message_id": str(msg.id),
                "pregunta": question["pregunta"],
                "opciones": question["opciones"],
                "respuesta_correcta": question["respuesta_correcta"],
                "explicacion": question["explicacion"],
                "posted_at": datetime.now(pytz.utc),
                "respondieron": [],
            })

            # Agregar reacciones de opciones
            for emoji in OPTION_EMOJIS[:len(question["opciones"])]:
                await msg.add_reaction(emoji)

            log.info(f"Trivia posteada: {question['pregunta'][:50]}...")

            # Esperar el tiempo de respuesta
            await asyncio.sleep(TRIVIA_TIMEOUT)

            # Revelar respuesta
            await self._reveal_answer(channel, msg, question)

        finally:
            self._active_trivia = False

    async def _reveal_answer(self, channel, original_msg: discord.Message, question: dict):
        """Revela la respuesta correcta y menciona a quienes acertaron."""
        try:
            # Refrescar el mensaje para ver las reacciones
            msg = await channel.fetch_message(original_msg.id)
        except discord.NotFound:
            return

        correct_idx = question["respuesta_correcta"]
        correct_emoji = OPTION_EMOJIS[correct_idx]
        correct_option = question["opciones"][correct_idx]

        # Obtener quienes reaccionaron correctamente
        winners = []
        for reaction in msg.reactions:
            if str(reaction.emoji) == correct_emoji:
                async for user in reaction.users():
                    if not user.bot:
                        winners.append(user.mention)

        # Construir embed de respuesta
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
        embed.add_field(
            name="💡 Explicación",
            value=question["explicacion"],
            inline=False,
        )

        if winners:
            embed.add_field(
                name=f"🎉 Acertaron ({len(winners)})",
                value=" ".join(winners[:20]),  # Máximo 20 menciones
                inline=False,
            )
        else:
            embed.add_field(
                name="😔 Nadie acertó",
                value="¡Difícil esta! Ya viene otra.",
                inline=False,
            )

        embed.set_footer(text="Mundial 2026 · Trivia — Solo por diversión, sin puntos")
        await channel.send(embed=embed)

        log.info(f"Trivia resuelta: {len(winners)} ganadores")

    # ──────────────────────────────────────────────────────────
    #   /trivia (comando manual con cooldown global)
    # ──────────────────────────────────────────────────────────
    @app_commands.command(name="trivia", description="Lanzar una pregunta de trivia ahora")
    async def trivia_manual(self, interaction: discord.Interaction):
        # Solo en el canal de trivia
        if interaction.channel_id != config.CHANNEL_TRIVIA:
            await interaction.response.send_message(
                f"Este comando solo se puede usar en <#{config.CHANNEL_TRIVIA}>",
                ephemeral=True,
            )
            return

        # Verificar trivia activa
        if self._active_trivia:
            await interaction.response.send_message(
                "Ya hay una trivia activa en este momento. Espera que termine!",
                ephemeral=True,
            )
            return

        # Verificar cooldown global
        last = await self.bot.db.trivia.find_one({}, sort=[("posted_at", -1)])
        if last:
            from utils.time_helpers import now_utc
            posted_at = last["posted_at"]
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=pytz.utc)
            elapsed = (now_utc() - posted_at).total_seconds() / 3600
            cooldown_hours = config.TRIVIA_INTERVAL_HOURS
            remaining = cooldown_hours - elapsed
            if remaining > 0:
                mins = int(remaining * 60)
                await interaction.response.send_message(
                    f"La proxima trivia estara disponible en **{mins} minutos**.",
                    ephemeral=True,
                )
                return

        await interaction.response.send_message(
            "Generando pregunta de trivia...",
            ephemeral=True,
        )

        asyncio.create_task(self.post_trivia_question())


async def setup(bot):
    await bot.add_cog(Trivia(bot))