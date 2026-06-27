import discord
from discord import app_commands
from discord.ext import commands


class Config(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /config ───────────────────────────────────────────────────────────────

    @app_commands.command(name="config", description="Affiche la configuration actuelle du bot")
    @app_commands.default_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)

        def channel_str(cid):
            if not cid:
                return "❌ Non configuré"
            ch = interaction.guild.get_channel(cid)
            return ch.mention if ch else f"⚠️ Salon introuvable (`{cid}`)"

        def role_str(rid):
            if not rid:
                return "❌ Non configuré"
            r = interaction.guild.get_role(rid)
            return r.mention if r else f"⚠️ Rôle introuvable (`{rid}`)"

        embed = discord.Embed(
            title=f"⚙️ Configuration de {interaction.guild.name}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="📋 Salon de logs", value=channel_str(settings.get("log_channel_id")), inline=True)
        embed.add_field(name="👋 Salon de bienvenue", value=channel_str(settings.get("welcome_channel_id")), inline=True)
        embed.add_field(name="👋 Salon d'au revoir", value=channel_str(settings.get("goodbye_channel_id")), inline=True)
        embed.add_field(name="🎭 Rôle automatique", value=role_str(settings.get("autorole_id")), inline=True)
        embed.add_field(
            name="💬 Message de bienvenue",
            value=f"`{settings.get('welcome_message', 'Non configuré')}`",
            inline=False
        )
        embed.add_field(
            name="💬 Message d'au revoir",
            value=f"`{settings.get('goodbye_message', 'Non configuré')}`",
            inline=False
        )
        embed.set_footer(text="Utilisez /setlogs, /setwelcome, /setgoodbye, /setautorole pour configurer.")
        await interaction.response.send_message(embed=embed)

    # ── /setlogs ──────────────────────────────────────────────────────────────

    @app_commands.command(name="setlogs", description="Définit le salon de logs de modération")
    @app_commands.describe(salon="Le salon où envoyer les logs")
    @app_commands.default_permissions(manage_guild=True)
    async def setlogs(self, interaction: discord.Interaction, salon: discord.TextChannel):
        await self.bot.db.update_guild_setting(interaction.guild.id, "log_channel_id", salon.id)
        await interaction.response.send_message(f"✅ Salon de logs défini sur {salon.mention}.")

    # ── /setwelcome ───────────────────────────────────────────────────────────

    @app_commands.command(name="setwelcome", description="Définit le salon et le message de bienvenue")
    @app_commands.describe(
        salon="Le salon de bienvenue",
        message="Le message (variables: {mention}, {name}, {server}, {count})"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setwelcome(self, interaction: discord.Interaction, salon: discord.TextChannel, message: str = None):
        await self.bot.db.update_guild_setting(interaction.guild.id, "welcome_channel_id", salon.id)
        if message:
            await self.bot.db.update_guild_setting(interaction.guild.id, "welcome_message", message)
        await interaction.response.send_message(
            f"✅ Salon de bienvenue défini sur {salon.mention}."
            + (f"\n💬 Message : `{message}`" if message else "")
        )

    # ── /setgoodbye ───────────────────────────────────────────────────────────

    @app_commands.command(name="setgoodbye", description="Définit le salon et le message d'au revoir")
    @app_commands.describe(
        salon="Le salon d'au revoir",
        message="Le message (variables: {name}, {server})"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setgoodbye(self, interaction: discord.Interaction, salon: discord.TextChannel, message: str = None):
        await self.bot.db.update_guild_setting(interaction.guild.id, "goodbye_channel_id", salon.id)
        if message:
            await self.bot.db.update_guild_setting(interaction.guild.id, "goodbye_message", message)
        await interaction.response.send_message(
            f"✅ Salon d'au revoir défini sur {salon.mention}."
            + (f"\n💬 Message : `{message}`" if message else "")
        )

    # ── /setautorole ──────────────────────────────────────────────────────────

    @app_commands.command(name="setautorole", description="Définit le rôle automatique donné aux nouveaux membres")
    @app_commands.describe(role="Le rôle à attribuer automatiquement")
    @app_commands.default_permissions(manage_guild=True)
    async def setautorole(self, interaction: discord.Interaction, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Ce rôle est supérieur ou égal au rôle du bot. Je ne peux pas l'attribuer.",
                ephemeral=True
            )
        await self.bot.db.update_guild_setting(interaction.guild.id, "autorole_id", role.id)
        await interaction.response.send_message(f"✅ Rôle automatique défini sur {role.mention}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Config(bot))
