import discord
import random
import time
from discord import app_commands
from discord.ext import commands
from utils.helpers import xp_for_level, total_xp_for_level
from utils.i18n import t


XP_COOLDOWNS: dict[tuple[int, int], float] = {}
XP_COOLDOWN_SECONDS = 60
XP_MIN = 15
XP_MAX = 25
XP_MIN_LENGTH = 5
LB_PAGE_SIZE = 10


class LevelUpView(discord.ui.View):
    def __init__(self, guild_id: int, lang: str):
        super().__init__(timeout=30)
        self.guild_id = guild_id
        self.lang     = lang
        self.children[0].label = t(lang, "xp.levelup_btn")

    @discord.ui.button(label="📊 Mon rang", style=discord.ButtonStyle.secondary)
    async def show_rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang     = await interaction.client.db.get_guild_lang(interaction.guild_id)
        data     = await interaction.client.db.get_xp(self.guild_id, interaction.user.id)
        rank_pos = await interaction.client.db.get_rank(self.guild_id, interaction.user.id)
        level    = data["level"]
        cur_xp   = data["xp"]
        xp_start = total_xp_for_level(level)
        xp_end   = total_xp_for_level(level + 1)
        progress = cur_xp - xp_start
        needed   = xp_end - xp_start
        filled   = int(16 * progress / needed) if needed > 0 else 0
        bar      = "█" * filled + "░" * (16 - filled)

        embed = discord.Embed(title=t(lang, "xp.rank_title", member=interaction.user.display_name), color=0xFFD700)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name=t(lang, "xp.rank_field"),  value=f"#{rank_pos}", inline=True)
        embed.add_field(name=t(lang, "xp.level_field"), value=str(level),     inline=True)
        embed.add_field(name=t(lang, "xp.xp_field"),    value=f"`{bar}` {progress}/{needed}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class LeaderboardView(discord.ui.View):
    def __init__(self, rows: list, guild: discord.Guild, lang: str, page: int = 0):
        super().__init__(timeout=120)
        self.all_rows = rows
        self.guild    = guild
        self.lang     = lang
        self.page     = page
        self.total    = max(1, (len(rows) + LB_PAGE_SIZE - 1) // LB_PAGE_SIZE)
        self._update_buttons()

    def _update_buttons(self):
        self.children[0].disabled = self.page == 0
        self.children[1].disabled = self.page >= self.total - 1

    def _build_embed(self) -> discord.Embed:
        lang  = self.lang
        start = self.page * LB_PAGE_SIZE
        slice_ = self.all_rows[start:start + LB_PAGE_SIZE]
        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, row in enumerate(slice_):
            pos    = start + i + 1
            member = self.guild.get_member(row["user_id"])
            name   = member.display_name if member else f"#{row['user_id']}"
            medal  = medals[pos - 1] if pos <= 3 else f"`#{pos}`"
            lines.append(t(lang, "xp.lb_entry", pos=pos, name=name, level=row["level"], xp=row["xp"]).replace(f"#{pos}", medal, 1))

        embed = discord.Embed(
            title=t(lang, "xp.lb_title", server=self.guild.name),
            description="\n".join(lines) if lines else t(lang, "xp.lb_empty"),
            color=discord.Color.gold()
        )
        embed.set_footer(text=t(lang, "xp.lb_page", page=self.page + 1, total=self.total))
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class XP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if len(message.content.strip()) < XP_MIN_LENGTH and not message.attachments:
            return

        key = (message.guild.id, message.author.id)
        now = time.time()
        if now - XP_COOLDOWNS.get(key, 0) < XP_COOLDOWN_SECONDS:
            return
        XP_COOLDOWNS[key] = now

        xp_gain = random.randint(XP_MIN, XP_MAX)
        data    = await self.bot.db.add_xp(message.guild.id, message.author.id, xp_gain)

        if data["xp"] >= total_xp_for_level(data["level"] + 1):
            new_level = data["level"] + 1
            await self.bot.db.set_xp(message.guild.id, message.author.id, data["xp"], new_level)
            lang = await self.bot.db.get_guild_lang(message.guild.id)

            embed = discord.Embed(
                title=t(lang, "xp.levelup_title"),
                description=t(lang, "xp.levelup_desc", member=message.author.mention, level=new_level),
                color=0xFFD700,
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            view = LevelUpView(message.guild.id, lang)
            await message.channel.send(embed=embed, view=view, delete_after=30)
            self.bot.dispatch("level_up", message.author, new_level)

    # ── /rank ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="rank", description="Affiche ton rang et ton XP")
    @app_commands.describe(membre="Le membre dont voir le rang (toi-même si vide)")
    async def rank(self, interaction: discord.Interaction, membre: discord.Member = None):
        lang   = await self.bot.db.get_guild_lang(interaction.guild_id)
        member = membre or interaction.user
        data   = await self.bot.db.get_xp(interaction.guild.id, member.id)
        rank_pos = await self.bot.db.get_rank(interaction.guild.id, member.id)

        level    = data["level"]
        cur_xp   = data["xp"]
        xp_start = total_xp_for_level(level)
        xp_end   = total_xp_for_level(level + 1)
        progress = cur_xp - xp_start
        needed   = xp_end - xp_start
        filled   = int(20 * progress / needed) if needed > 0 else 0
        bar      = "█" * filled + "░" * (20 - filled)

        color = member.color if member.color != discord.Color.default() else discord.Color.gold()
        embed = discord.Embed(title=t(lang, "xp.rank_title", member=member.display_name), color=color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name=t(lang, "xp.rank_field"),      value=f"#{rank_pos}",                      inline=True)
        embed.add_field(name=t(lang, "xp.level_field"),     value=str(level),                           inline=True)
        embed.add_field(name=t(lang, "xp.messages_label"),  value=str(data["messages"]),                inline=True)
        embed.add_field(name=t(lang, "xp.xp_field"),        value=f"`{bar}` {progress}/{needed} XP",   inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @app_commands.command(name="leaderboard", description="Classement XP du serveur (paginé)")
    async def leaderboard(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        rows = await self.bot.db.get_leaderboard(interaction.guild.id, 100)
        if not rows:
            return await interaction.response.send_message(t(lang, "xp.lb_empty"), ephemeral=True)

        view  = LeaderboardView(rows, interaction.guild, lang)
        embed = view._build_embed()
        await interaction.response.send_message(embed=embed, view=view)

    # ── Admin XP commands ─────────────────────────────────────────────────────

    @app_commands.command(name="setxp", description="Définit l'XP d'un membre")
    @app_commands.describe(membre="Le membre", montant="Le montant d'XP")
    @app_commands.default_permissions(manage_guild=True)
    async def setxp(self, interaction: discord.Interaction, membre: discord.Member, montant: app_commands.Range[int, 0]):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        level = 0
        while total_xp_for_level(level + 1) <= montant:
            level += 1
        await self.bot.db.set_xp(interaction.guild.id, membre.id, montant, level)
        await interaction.response.send_message(t(lang, "xp.set_success", member=membre.mention, xp=montant, level=level))

    @app_commands.command(name="addxp", description="Ajoute de l'XP à un membre")
    @app_commands.describe(membre="Le membre", montant="Le montant d'XP à ajouter")
    @app_commands.default_permissions(manage_guild=True)
    async def addxp(self, interaction: discord.Interaction, membre: discord.Member, montant: app_commands.Range[int, 1]):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        data = await self.bot.db.add_xp(interaction.guild.id, membre.id, montant)
        level = data["level"]
        if data["xp"] >= total_xp_for_level(level + 1):
            level += 1
            await self.bot.db.set_xp(interaction.guild.id, membre.id, data["xp"], level)
        await interaction.response.send_message(
            t(lang, "xp.set_success", member=membre.mention, xp=data["xp"], level=level)
        )

    @app_commands.command(name="resetxp", description="Réinitialise l'XP d'un membre")
    @app_commands.describe(membre="Le membre dont réinitialiser l'XP")
    @app_commands.default_permissions(manage_guild=True)
    async def resetxp(self, interaction: discord.Interaction, membre: discord.Member):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.reset_xp(interaction.guild.id, membre.id)
        await interaction.response.send_message(t(lang, "xp.reset_success", member=membre.mention))


async def setup(bot: commands.Bot):
    await bot.add_cog(XP(bot))
