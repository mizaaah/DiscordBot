import discord
from discord.ext import commands
from utils.i18n import t
from utils.colors import Colors


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _format_message(self, template: str, member: discord.Member) -> str:
        return (
            template
            .replace("{mention}", member.mention)
            .replace("{name}", str(member))
            .replace("{username}", member.name)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count))
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await self.bot.db.get_guild_settings(member.guild.id)
        lang     = settings.get("language") or "fr"

        # ── Auto-rôle ────────────────────────────────────────────────────
        autorole_id = settings.get("autorole_id")
        if autorole_id:
            role = member.guild.get_role(autorole_id)
            if role and member.guild.me.guild_permissions.manage_roles and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Rôle automatique à l'arrivée")
                except discord.Forbidden:
                    pass

        # ── Salon de bienvenue ────────────────────────────────────────────
        welcome_channel_id = settings.get("welcome_channel_id")
        if not welcome_channel_id:
            return
        channel = member.guild.get_channel(welcome_channel_id)
        if not channel or not channel.permissions_for(member.guild.me).send_messages:
            return

        template = settings.get("welcome_message") or t(lang, "welcome.join_default")
        message  = self._format_message(template, member)
        age      = (discord.utils.utcnow() - member.created_at).days

        # ── Couleur ───────────────────────────────────────────────────────
        welcome_color_str = settings.get("welcome_color")
        try:
            welcome_color = int(welcome_color_str.strip("#"), 16) if welcome_color_str else Colors.SUCCESS.value
        except Exception:
            welcome_color = Colors.SUCCESS.value

        # ── Construction du Container v2 ──────────────────────────────────
        view = discord.ui.LayoutView()
        cont = discord.ui.Container(accent_color=welcome_color)

        # Header avec avatar en thumbnail
        avatar_url = member.display_avatar.url
        thumb = discord.ui.Thumbnail(media=avatar_url)

        title = t(lang, "welcome.join_title", server=member.guild.name)
        cont.add_item(discord.ui.Section(
            discord.ui.TextDisplay(f"# {title}\n> {message}"),
            accessory=thumb
        ))

        cont.add_item(discord.ui.Separator())

        # Infos du membre
        created_dt = discord.utils.format_dt(member.created_at, 'D')
        joined_dt  = discord.utils.format_dt(member.joined_at, 'R') if member.joined_at else "—"
        member_count = member.guild.member_count

        info_text = (
            f"**{t(lang, 'welcome.account_created_field')}** {created_dt}\n"
            f"**{t(lang, 'welcome.members_field')}** `#{member_count}`\n"
        )

        # Alerte nouveau compte (< 7 jours)
        if age < 7:
            info_text += f"\n⚠️ *Compte créé il y a seulement **{age}** jour(s)*"

        cont.add_item(discord.ui.TextDisplay(info_text))

        # Image de bienvenue personnalisée
        welcome_image = settings.get("welcome_image")
        if welcome_image:
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.MediaGallery(discord.ui.MediaGalleryItem(media=welcome_image)))

        # Footer avec icône du serveur
        footer_text = t(lang, "welcome.footer_join", count=member_count, days=age)
        guild_icon = member.guild.icon.url if member.guild.icon else None
        if guild_icon:
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay(f"-# {footer_text}"),
                accessory=discord.ui.Thumbnail(media=guild_icon)
            ))
        else:
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.TextDisplay(f"-# {footer_text}"))

        view.add_item(cont)
        await channel.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
