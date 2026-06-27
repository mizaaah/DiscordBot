import discord
import random
from discord import app_commands
from discord.ext import commands
from utils.helpers import xp_for_level, total_xp_for_level


XP_COOLDOWNS: dict[tuple[int, int], float] = {}
XP_COOLDOWN_SECONDS = 60
XP_MIN = 15
XP_MAX = 25


class XP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        import time
        key = (message.guild.id, message.author.id)
        now = time.time()

        if now - XP_COOLDOWNS.get(key, 0) < XP_COOLDOWN_SECONDS:
            return
        XP_COOLDOWNS[key] = now

        xp_gain = random.randint(XP_MIN, XP_MAX)
        data = await self.bot.db.add_xp(message.guild.id, message.author.id, xp_gain)

        current_xp = data["xp"]
        current_level = data["level"]
        needed = xp_for_level(current_level)

        if current_xp >= total_xp_for_level(current_level + 1):
            new_level = current_level + 1
            await self.bot.db.set_xp(message.guild.id, message.author.id, current_xp, new_level)

            embed = discord.Embed(
                title="🎉 Niveau supérieur !",
                description=f"Félicitations {message.author.mention}, tu passes au niveau **{new_level}** !",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            await message.channel.send(embed=embed, delete_after=10)

    # ── /rank ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="rank", description="Affiche ton rang et ton XP")
    @app_commands.describe(membre="Le membre dont voir le rang (toi-même si vide)")
    async def rank(self, interaction: discord.Interaction, membre: discord.Member = None):
        member = membre or interaction.user
        data = await self.bot.db.get_xp(interaction.guild.id, member.id)
        rank_pos = await self.bot.db.get_rank(interaction.guild.id, member.id)

        level = data["level"]
        current_xp = data["xp"]
        xp_at_current = total_xp_for_level(level)
        xp_at_next = total_xp_for_level(level + 1)
        xp_in_level = current_xp - xp_at_current
        xp_needed = xp_at_next - xp_at_current

        bar_length = 20
        filled = int(bar_length * xp_in_level / xp_needed) if xp_needed > 0 else 0
        bar = "█" * filled + "░" * (bar_length - filled)

        embed = discord.Embed(
            title=f"⭐ Rang de {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.gold()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Rang", value=f"#{rank_pos}", inline=True)
        embed.add_field(name="Niveau", value=str(level), inline=True)
        embed.add_field(name="Messages", value=str(data["messages"]), inline=True)
        embed.add_field(
            name="XP",
            value=f"`{bar}` {xp_in_level}/{xp_needed} XP",
            inline=False
        )
        embed.add_field(name="XP total", value=str(current_xp), inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @app_commands.command(name="leaderboard", description="Classement XP du serveur")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await self.bot.db.get_leaderboard(interaction.guild.id, 10)
        embed = discord.Embed(
            title=f"🏆 Classement de {interaction.guild.name}",
            color=discord.Color.gold()
        )
        if not rows:
            embed.description = "Aucun membre dans le classement pour l'instant."
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, row in enumerate(rows):
                member = interaction.guild.get_member(row["user_id"])
                name = member.display_name if member else f"Utilisateur #{row['user_id']}"
                medal = medals[i] if i < 3 else f"`#{i + 1}`"
                lines.append(f"{medal} **{name}** — Niv. {row['level']} | {row['xp']} XP")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)

    # ── Admin XP commands ─────────────────────────────────────────────────────

    @app_commands.command(name="setxp", description="Définit l'XP d'un membre")
    @app_commands.describe(membre="Le membre", montant="Le montant d'XP")
    @app_commands.default_permissions(manage_guild=True)
    async def setxp(self, interaction: discord.Interaction, membre: discord.Member, montant: app_commands.Range[int, 0]):
        level = 0
        while total_xp_for_level(level + 1) <= montant:
            level += 1
        await self.bot.db.set_xp(interaction.guild.id, membre.id, montant, level)
        await interaction.response.send_message(
            f"✅ XP de {membre.mention} défini à **{montant}** (Niveau **{level}**)."
        )

    @app_commands.command(name="addxp", description="Ajoute de l'XP à un membre")
    @app_commands.describe(membre="Le membre", montant="Le montant d'XP à ajouter")
    @app_commands.default_permissions(manage_guild=True)
    async def addxp(self, interaction: discord.Interaction, membre: discord.Member, montant: app_commands.Range[int, 1]):
        data = await self.bot.db.add_xp(interaction.guild.id, membre.id, montant)
        level = data["level"]
        new_total = data["xp"]
        next_level_xp = total_xp_for_level(level + 1)
        if new_total >= next_level_xp:
            new_level = level + 1
            await self.bot.db.set_xp(interaction.guild.id, membre.id, new_total, new_level)
            level = new_level
        await interaction.response.send_message(
            f"✅ +**{montant}** XP ajouté à {membre.mention}. Total : **{new_total}** XP (Niveau **{level}**)."
        )

    @app_commands.command(name="resetxp", description="Réinitialise l'XP d'un membre")
    @app_commands.describe(membre="Le membre dont réinitialiser l'XP")
    @app_commands.default_permissions(manage_guild=True)
    async def resetxp(self, interaction: discord.Interaction, membre: discord.Member):
        await self.bot.db.reset_xp(interaction.guild.id, membre.id)
        await interaction.response.send_message(f"✅ XP de {membre.mention} réinitialisé.")


async def setup(bot: commands.Bot):
    await bot.add_cog(XP(bot))
