import re
import discord
from discord import app_commands
from discord.ext import commands
from utils.i18n import t
from utils.colors import Colors
from utils.media import resolve_media_url


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _format_message(self, template: str, member: discord.Member) -> str:
        def _replace_channel(m):
            ch_name = m.group(1).lower().strip()
            for ch in member.guild.text_channels:
                if ch.name.lower() == ch_name:
                    return ch.mention
            return m.group(0)

        formatted = re.sub(r'\{#([^}]+)\}', _replace_channel, template)
        return (
            formatted
            .replace("{mention}", member.mention)
            .replace("{user}", member.mention)
            .replace("{member}", member.mention)
            .replace("{name}", member.display_name)
            .replace("{username}", member.name)
            .replace("{server}", member.guild.name)
            .replace("{server.name}", member.guild.name)
            .replace("{server.member_count}", str(member.guild.member_count))
            .replace("{count}", str(member.guild.member_count))
        )

    async def _build_welcome_view(self, member: discord.Member, settings: dict, lang: str) -> discord.ui.LayoutView:
        template = settings.get("welcome_message") or t(lang, "welcome.join_default")
        message  = self._format_message(template, member)

        # Titre personnalisable
        raw_title = settings.get("welcome_title") or t(lang, "welcome.join_title", server=member.guild.name)
        title     = self._format_message(raw_title, member)

        # Couleur
        welcome_color_str = settings.get("welcome_color")
        try:
            welcome_color = int(welcome_color_str.strip("#"), 16) if welcome_color_str else Colors.SUCCESS.value
        except Exception:
            welcome_color = Colors.SUCCESS.value

        # Construction du Container v2
        view = discord.ui.LayoutView()
        cont = discord.ui.Container(accent_color=welcome_color)

        # Header avec avatar en thumbnail
        avatar_url = member.display_avatar.url
        thumb = discord.ui.Thumbnail(media=avatar_url)

        cont.add_item(discord.ui.Section(
            discord.ui.TextDisplay(f"# {title}\n> {message}"),
            accessory=thumb
        ))

        # Image de bienvenue personnalisée (PNG/GIF/Klipy/Tenor)
        welcome_image = settings.get("welcome_image")
        if welcome_image:
            resolved_image = await resolve_media_url(welcome_image)
            if resolved_image:
                try:
                    cont.add_item(discord.ui.Separator())
                    cont.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(media=resolved_image)))
                except Exception:
                    try:
                        cont.add_item(discord.ui.Thumbnail(media=resolved_image))
                    except Exception:
                        pass

        view.add_item(cont)
        return view

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await self.bot.db.get_guild_settings(member.guild.id)
        lang     = settings.get("language") or "fr"

        # ── Auto-rôle (Humains vs Bots) ──────────────────────────────────
        target_role_id = settings.get("autorole_bots_id") if member.bot else settings.get("autorole_id")
        if target_role_id:
            role = member.guild.get_role(target_role_id)
            if role and member.guild.me.guild_permissions.manage_roles and role < member.guild.me.top_role:
                try:
                    reason = "Auto-rôle bot à l'arrivée" if member.bot else "Auto-rôle membre à l'arrivée"
                    await member.add_roles(role, reason=reason)
                except discord.Forbidden:
                    pass

        # ── Salon de bienvenue ────────────────────────────────────────────
        welcome_channel_id = settings.get("welcome_channel_id")
        if not welcome_channel_id:
            return
        channel = member.guild.get_channel(welcome_channel_id)
        if not channel or not channel.permissions_for(member.guild.me).send_messages:
            return

        view = await self._build_welcome_view(member, settings, lang)
        await channel.send(view=view)

    @app_commands.command(name="welcometest", description="Simule et teste l'envoi du message de bienvenue")
    @app_commands.default_permissions(manage_guild=True)
    async def welcometest(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        lang     = settings.get("language") or "fr"

        view = await self._build_welcome_view(interaction.user, settings, lang)
        await interaction.response.send_message(
            content="ℹ️ **Aperçu du message de bienvenue (visible uniquement par vous) :**",
            view=view,
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
