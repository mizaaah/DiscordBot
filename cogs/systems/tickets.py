import asyncio
import io
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.embeds import error_embed, info_embed, success_embed
from utils.i18n import t


# ── Shared ticket-creation logic ──────────────────────────────────────────────

async def _open_ticket(bot: commands.Bot, interaction: discord.Interaction, category: str = None):
    guild = interaction.guild
    user = interaction.user
    lang = await bot.db.get_guild_lang(guild.id)

    async def reply(msg: str = None, **kwargs):
        if interaction.response.is_done():
            await interaction.followup.send(msg, **kwargs)
        else:
            await interaction.response.send_message(msg, **kwargs)

    existing = await bot.db.get_user_open_ticket(guild.id, user.id)
    if existing:
        ch = guild.get_channel(existing["channel_id"])
        if ch:
            return await reply(embed=error_embed(t(lang, "ticket.already_open", channel=ch.mention)), ephemeral=True)

    config = await bot.db.get_ticket_config(guild.id)
    if not config.get("staff_role_id"):
        return await reply(embed=error_embed(t(lang, "ticket.not_configured")), ephemeral=True)

    ticket_cat   = guild.get_channel(config["category_id"])  if config.get("category_id")  else None
    staff_role   = guild.get_role(config["staff_role_id"])   if config.get("staff_role_id") else None
    ticket_num   = await bot.db.increment_ticket_counter(guild.id)
    name_format  = config.get("channel_name_format") or "{category}-{number}"
    channel_name = (
        name_format
        .replace("{category}", category.lower().replace(" ", "-") if category else "ticket")
        .replace("{number}", f"{ticket_num:04d}")
        .replace("{user}", user.display_name[:20])
        .lower().replace(" ", "-")
    )[:100]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, attach_files=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True,
            manage_messages=True, read_message_history=True, embed_links=True
        ),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True,
            read_message_history=True, manage_messages=True, attach_files=True
        )

    try:
        channel = await guild.create_text_channel(
            name=channel_name, category=ticket_cat,
            overwrites=overwrites, reason=f"Ticket ouvert par {user}"
        )
    except discord.Forbidden:
        return await reply(embed=error_embed(t(lang, "ticket.cant_create_channel")), ephemeral=True)

    await bot.db.create_ticket(guild.id, channel.id, user.id, ticket_num, category)

    # ── Build welcome embed ──────────────────────────────────────────────────
    color = discord.Color(config.get("embed_color") or Colors.INFO.value)
    template = config.get("welcome_message") or t(lang, "ticket.default_welcome")
    welcome = (
        template
        .replace("{mention}", user.mention)
        .replace("{name}", user.display_name)
        .replace("{ticket_number}", f"{ticket_num:04d}")
        .replace("{category}", category or t(lang, "ticket.default_category"))
    )

    title = t(lang, "ticket.title_num", num=f"{ticket_num:04d}")
    if category:
        title += f" — {category}"

    embed = discord.Embed(title=title, description=welcome, color=color)
    if staff_role:
        embed.add_field(name=t(lang, "ticket.support_field"), value=staff_role.mention, inline=True)
    if category:
        embed.add_field(name=t(lang, "ticket.category_field"), value=category, inline=True)
    embed.add_field(name=t(lang, "ticket.claimed_by_field"), value=t(lang, "ticket.not_claimed"), inline=True)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=t(lang, "ticket.member_id_footer", id=user.id))

    await channel.send(embed=embed, view=TicketCloseView(bot, config.get("close_button_label"), config.get("close_button_emoji")))
    await channel.send(user.mention, delete_after=1)
    await reply(embed=success_embed(t(lang, "ticket.created", channel=channel.mention)), ephemeral=True)

    if logs := bot.get_cog("Logs"):
        log_embed = discord.Embed(title=t(lang, "ticket.log_opened_title"), color=Colors.SUCCESS)
        log_embed.add_field(name=t(lang, "ticket.log_member"), value=f"{user.mention} (`{user.id}`)", inline=True)
        log_embed.add_field(name=t(lang, "ticket.log_channel"), value=channel.mention, inline=True)
        log_embed.add_field(name=t(lang, "ticket.log_number"), value=f"#{ticket_num:04d}", inline=True)
        if category:
            log_embed.add_field(name=t(lang, "ticket.category_field"), value=category, inline=True)
        await logs.send_log(guild, log_embed)


# ── Category select (ephemeral, non-persistent) ───────────────────────────────

class TicketCategorySelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, categories: list):
        self.bot = bot
        options = [discord.SelectOption(label=c, value=c, emoji="🏷️") for c in categories[:25]]
        super().__init__(placeholder="📂 Choisis une catégorie...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await _open_ticket(self.bot, interaction, self.values[0])


class TicketCategoryView(discord.ui.View):
    def __init__(self, bot: commands.Bot, categories: list):
        super().__init__(timeout=60)
        self.add_item(TicketCategorySelect(bot, categories))


# ── Persistent views ──────────────────────────────────────────────────────────

class TicketOpenView(discord.ui.View):
    def __init__(self, bot: commands.Bot, label: str = None, emoji: str = None):
        super().__init__(timeout=None)
        self.bot = bot
        if label:
            self.open_ticket.label = label
        if emoji:
            self.open_ticket.emoji = emoji

    @discord.ui.button(
        label="Ouvrir un ticket",
        emoji="📩",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_open_persistent"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        categories = [c for c in (config.get("categories") or []) if c]

        if categories:
            await interaction.response.send_message(
                embed=info_embed(t(lang, "ticket.pick_category")),
                view=TicketCategoryView(self.bot, categories),
                ephemeral=True
            )
        else:
            await _open_ticket(self.bot, interaction)


class TicketCloseView(discord.ui.View):
    def __init__(self, bot: commands.Bot, label: str = None, emoji: str = None):
        super().__init__(timeout=None)
        self.bot = bot
        if label:
            self.close_ticket.label = label
        if emoji:
            self.close_ticket.emoji = emoji

    @discord.ui.button(
        label="Fermer le ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close_persistent"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)

        config      = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_id    = config.get("staff_role_id")
        is_owner    = ticket["user_id"] == interaction.user.id
        is_staff    = (
            interaction.user.guild_permissions.manage_channels
            or (staff_id and any(r.id == staff_id for r in interaction.user.roles))
        )

        if not (is_owner or is_staff):
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "ticket.close_denied")), ephemeral=True
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                description=t(lang, "ticket.close_confirm_prompt"),
                color=Colors.WARNING
            ),
            view=TicketCloseConfirmView(self.bot, ticket, config, lang),
            ephemeral=True
        )


class TicketCloseConfirmView(discord.ui.View):
    def __init__(self, bot: commands.Bot, ticket: dict, config: dict, lang: str):
        super().__init__(timeout=30)
        self.bot    = bot
        self.ticket = ticket
        self.config = config
        self.lang   = lang

    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = self.lang
        self.stop()
        await interaction.response.defer()

        channel = interaction.channel
        guild   = interaction.guild

        # ── Générer la transcription ──────────────────────────────────────
        lines = []
        async for msg in channel.history(limit=500, oldest_first=True):
            ts      = msg.created_at.strftime("%d/%m/%Y %H:%M")
            content = msg.content or (
                "[embed]"          if msg.embeds      else
                f"[{len(msg.attachments)} fichier(s)]" if msg.attachments else ""
            )
            lines.append(f"[{ts}] {msg.author.display_name}: {content}")

        owner      = guild.get_member(self.ticket["user_id"])
        close_time = datetime.now(timezone.utc)
        open_time  = self.ticket.get("created_at")
        duration   = ""
        if open_time:
            mins     = int((close_time - open_time).total_seconds() // 60)
            duration = f"{mins // 60}h {mins % 60}min" if mins >= 60 else f"{mins} min"

        cat_line = f" — {self.ticket['category']}" if self.ticket.get("category") else ""
        sep      = "═" * 52
        header   = (
            f"{sep}\n"
            f"  TICKET #{self.ticket['ticket_number']:04d}{cat_line}\n"
            f"  Ouvert par  : {owner or self.ticket['user_id']}\n"
            f"  Fermé par   : {interaction.user}\n"
            f"  Date        : {close_time.strftime('%d/%m/%Y %H:%M')} UTC\n"
            f"  Durée       : {duration or 'inconnue'}\n"
            f"{sep}\n\n"
        )
        txt_content = header + "\n".join(lines)

        # ── Envoyer dans le salon de logs ─────────────────────────────────
        log_ch_id = self.config.get("log_channel_id")
        if not log_ch_id:
            settings  = await self.bot.db.get_guild_settings(guild.id)
            log_ch_id = settings.get("log_channel_id")

        if log_ch_id:
            log_ch = guild.get_channel(log_ch_id)
            if log_ch:
                embed = discord.Embed(
                    title=t(lang, "ticket.log_closed_title", num=f"{self.ticket['ticket_number']:04d}"),
                    color=Colors.ERROR
                )
                embed.add_field(
                    name=t(lang, "ticket.opened_by"),
                    value=owner.mention if owner else str(self.ticket["user_id"]),
                    inline=True
                )
                embed.add_field(name=t(lang, "ticket.closed_by"), value=interaction.user.mention, inline=True)
                if self.ticket.get("category"):
                    embed.add_field(name=t(lang, "ticket.category_field"), value=self.ticket["category"], inline=True)
                if duration:
                    embed.add_field(name=t(lang, "ticket.duration_field"), value=duration, inline=True)
                if self.ticket.get("claimed_by"):
                    claimer = guild.get_member(self.ticket["claimed_by"])
                    embed.add_field(
                        name=t(lang, "ticket.claimed_by_field"),
                        value=claimer.mention if claimer else str(self.ticket["claimed_by"]),
                        inline=True
                    )
                file = discord.File(
                    io.BytesIO(txt_content.encode("utf-8")),
                    filename=f"ticket-{self.ticket['ticket_number']:04d}.txt"
                )
                try:
                    await log_ch.send(embed=embed, file=file)
                except discord.Forbidden:
                    pass

        await self.bot.db.close_ticket(channel.id, interaction.user.id)

        try:
            close_embed = discord.Embed(
                description=t(lang, "ticket.closing_message"),
                color=Colors.ERROR
            )
            await channel.send(embed=close_embed)
        except discord.Forbidden:
            pass

        await asyncio.sleep(5)

        try:
            await channel.delete(reason=f"Ticket fermé par {interaction.user}")
        except discord.Forbidden:
            pass

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message(embed=info_embed(t(self.lang, "ticket.close_cancelled")), ephemeral=True)


# ── Cog ───────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketOpenView(self.bot))
        self.bot.add_view(TicketCloseView(self.bot))

    # ── /ticket (groupe) ──────────────────────────────────────────────────────

    ticket_group = app_commands.Group(name="ticket", description="Gestion du système de tickets")

    @ticket_group.command(name="setup", description="Configure le système et envoie le panel d'ouverture")
    @app_commands.describe(
        salon="Salon où envoyer le panel",
        role_staff="Rôle de l'équipe de support",
        categorie="Catégorie Discord pour les tickets (optionnel)",
        salon_logs="Salon de logs dédié aux tickets (optionnel)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        salon: discord.TextChannel,
        role_staff: discord.Role,
        categorie: discord.CategoryChannel = None,
        salon_logs: discord.TextChannel = None
    ):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        db  = self.bot.db
        gid = interaction.guild.id
        await db.update_ticket_config(gid, "staff_role_id", role_staff.id)
        if categorie:
            await db.update_ticket_config(gid, "category_id", categorie.id)
        if salon_logs:
            await db.update_ticket_config(gid, "log_channel_id", salon_logs.id)

        config = await db.get_ticket_config(gid)
        color  = discord.Color(config.get("embed_color") or Colors.INFO.value)

        embed = discord.Embed(
            title=t(lang, "ticket.panel_title"),
            description=t(lang, "ticket.panel_desc"),
            color=color
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text=interaction.guild.name)

        view  = TicketOpenView(self.bot, config.get("open_button_label"), config.get("open_button_emoji"))
        panel = await salon.send(embed=embed, view=view)

        await db.update_ticket_config(gid, "panel_message_id", panel.id)
        await db.update_ticket_config(gid, "panel_channel_id", salon.id)

        await interaction.response.send_message(
            embed=success_embed(t(lang, "ticket.setup_success", channel=salon.mention)), ephemeral=True
        )

    @ticket_group.command(name="categories", description="Définit les catégories de tickets (menu déroulant à l'ouverture)")
    @app_commands.describe(categories="Catégories séparées par des virgules — laisser vide pour désactiver")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_categories(self, interaction: discord.Interaction, categories: str = ""):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        cats = [c.strip() for c in categories.split(",") if c.strip()][:10]
        await self.bot.db.update_ticket_config(interaction.guild.id, "categories", cats)

        if cats:
            embed = discord.Embed(
                title=t(lang, "ticket.categories_updated_title"),
                description="\n".join(f"🏷️ **{c}**" for c in cats),
                color=Colors.SUCCESS
            )
            embed.set_footer(text=t(lang, "ticket.categories_footer"))
        else:
            embed = discord.Embed(
                description=t(lang, "ticket.categories_disabled"),
                color=Colors.SUCCESS
            )
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="customize", description="Personnalise le nom des salons et les boutons d'ouverture/fermeture")
    @app_commands.describe(
        format_salon="Format du nom du salon (variables : {category} {number} {user})",
        bouton_ouvrir_texte="Texte du bouton d'ouverture",
        bouton_ouvrir_emoji="Emoji du bouton d'ouverture",
        bouton_fermer_texte="Texte du bouton de fermeture",
        bouton_fermer_emoji="Emoji du bouton de fermeture",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_customize(
        self,
        interaction: discord.Interaction,
        format_salon: str = None,
        bouton_ouvrir_texte: str = None,
        bouton_ouvrir_emoji: str = None,
        bouton_fermer_texte: str = None,
        bouton_fermer_emoji: str = None,
    ):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        updates = {
            "channel_name_format": format_salon,
            "open_button_label":   bouton_ouvrir_texte,
            "open_button_emoji":   bouton_ouvrir_emoji,
            "close_button_label":  bouton_fermer_texte,
            "close_button_emoji":  bouton_fermer_emoji,
        }
        provided = {k: v for k, v in updates.items() if v is not None}
        if not provided:
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.customize_no_params")), ephemeral=True)

        db  = self.bot.db
        gid = interaction.guild.id
        for setting, value in provided.items():
            await db.update_ticket_config(gid, setting, value)

        config = await db.get_ticket_config(gid)

        # Re-render the open panel if one already exists
        if config.get("panel_channel_id") and config.get("panel_message_id"):
            panel_ch = interaction.guild.get_channel(config["panel_channel_id"])
            if panel_ch:
                try:
                    panel_msg = await panel_ch.fetch_message(config["panel_message_id"])
                    new_view  = TicketOpenView(self.bot, config.get("open_button_label"), config.get("open_button_emoji"))
                    await panel_msg.edit(view=new_view)
                    self.bot.add_view(new_view, message_id=panel_msg.id)
                except (discord.NotFound, discord.Forbidden):
                    pass

        embed = discord.Embed(title=t(lang, "ticket.customize_updated_title"), color=Colors.SUCCESS)
        embed.add_field(name=t(lang, "ticket.channel_name_format_field"), value=f"`{config.get('channel_name_format')}`", inline=False)
        embed.add_field(name=t(lang, "ticket.open_button_field"), value=f"{config.get('open_button_emoji') or ''} {config.get('open_button_label')}".strip(), inline=True)
        embed.add_field(name=t(lang, "ticket.close_button_field"), value=f"{config.get('close_button_emoji') or ''} {config.get('close_button_label')}".strip(), inline=True)
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="couleur", description="Change la couleur des embeds de tickets")
    @app_commands.describe(couleur="Code hexadécimal (ex: FF0000 ou #FF0000)")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_couleur(self, interaction: discord.Interaction, couleur: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        try:
            color_int = int(couleur.lstrip("#"), 16)
            if not 0 <= color_int <= 0xFFFFFF:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "ticket.invalid_color")), ephemeral=True
            )
        await self.bot.db.update_ticket_config(interaction.guild.id, "embed_color", color_int)
        embed = discord.Embed(
            description=t(lang, "ticket.color_updated"),
            color=discord.Color(color_int)
        )
        embed.add_field(name=t(lang, "ticket.color_code_field"), value=f"`#{color_int:06X}`")
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="message", description="Personnalise le message d'accueil dans les tickets")
    @app_commands.describe(message="Variables dispo : {mention} {name} {ticket_number} {category}")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_message(self, interaction: discord.Interaction, message: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.update_ticket_config(interaction.guild.id, "welcome_message", message)
        preview = (
            message
            .replace("{mention}", interaction.user.mention)
            .replace("{name}", interaction.user.display_name)
            .replace("{ticket_number}", "0001")
            .replace("{category}", "Support")
        )
        embed = discord.Embed(
            title=t(lang, "ticket.welcome_msg_updated"),
            color=Colors.SUCCESS
        )
        embed.add_field(name=t(lang, "ticket.preview_field"), value=preview, inline=False)
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="config", description="Affiche la configuration actuelle des tickets")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_config(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        color  = discord.Color(config.get("embed_color") or Colors.INFO.value)

        staff_role  = interaction.guild.get_role(config["staff_role_id"])    if config.get("staff_role_id")    else None
        category_ch = interaction.guild.get_channel(config["category_id"])   if config.get("category_id")      else None
        log_ch      = interaction.guild.get_channel(config["log_channel_id"]) if config.get("log_channel_id")  else None

        embed = discord.Embed(title=t(lang, "ticket.config_title"), color=color)
        embed.add_field(name=t(lang, "ticket.staff_role_field"), value=staff_role.mention    if staff_role   else t(lang, "ticket.not_configured_f"),  inline=True)
        embed.add_field(name=t(lang, "ticket.discord_category_field"), value=category_ch.mention  if category_ch  else t(lang, "ticket.not_configured_f"), inline=True)
        embed.add_field(name=t(lang, "ticket.log_channel_field"), value=log_ch.mention       if log_ch       else t(lang, "ticket.not_configured_f"),  inline=True)
        embed.add_field(name=t(lang, "ticket.color_field"), value=f"`#{config.get('embed_color', Colors.INFO.value):06X}`", inline=True)
        embed.add_field(name=t(lang, "ticket.opened_count_field"), value=str(config.get("ticket_counter", 0)), inline=True)
        embed.add_field(name=t(lang, "ticket.channel_name_format_field"), value=f"`{config.get('channel_name_format') or '{category}-{number}'}`", inline=True)
        embed.add_field(name=t(lang, "ticket.open_button_field"), value=f"{config.get('open_button_emoji') or ''} {config.get('open_button_label') or 'Ouvrir un ticket'}".strip(), inline=True)
        embed.add_field(name=t(lang, "ticket.close_button_field"), value=f"{config.get('close_button_emoji') or ''} {config.get('close_button_label') or 'Fermer le ticket'}".strip(), inline=True)

        cats = [c for c in (config.get("categories") or []) if c]
        embed.add_field(
            name=t(lang, "ticket.categories_field", count=len(cats)),
            value="\n".join(f"🏷️ {c}" for c in cats) or t(lang, "ticket.no_categories"),
            inline=False
        )
        welcome = config.get("welcome_message")
        embed.add_field(
            name=t(lang, "ticket.welcome_msg_field"),
            value=f"`{welcome[:80]}...`" if welcome and len(welcome) > 80 else (f"`{welcome}`" if welcome else t(lang, "ticket.default_message")),
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /tadd /tremove ────────────────────────────────────────────────────────

    @app_commands.command(name="tadd", description="Ajoute un membre à ce ticket")
    @app_commands.describe(membre="Le membre à ajouter")
    @app_commands.default_permissions(manage_channels=True)
    async def tadd(self, interaction: discord.Interaction, membre: discord.Member):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if not await self.bot.db.get_ticket(interaction.channel.id):
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)
        await interaction.channel.set_permissions(
            membre, view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True
        )
        embed = discord.Embed(description=t(lang, "ticket.member_added", member=membre.mention), color=Colors.SUCCESS)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tremove", description="Retire un membre de ce ticket")
    @app_commands.describe(membre="Le membre à retirer")
    @app_commands.default_permissions(manage_channels=True)
    async def tremove(self, interaction: discord.Interaction, membre: discord.Member):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)
        if ticket["user_id"] == membre.id:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "ticket.cant_remove_creator")), ephemeral=True
            )
        await interaction.channel.set_permissions(membre, overwrite=None)
        embed = discord.Embed(description=t(lang, "ticket.member_removed", member=membre.mention), color=Colors.WARNING)
        await interaction.response.send_message(embed=embed)

    # ── /tclaim /tunclaim ─────────────────────────────────────────────────────

    @app_commands.command(name="tclaim", description="Réclame ce ticket — indique que tu t'en occupes")
    @app_commands.default_permissions(manage_channels=True)
    async def tclaim(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)
        if ticket.get("claimed_by"):
            claimer = interaction.guild.get_member(ticket["claimed_by"])
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "ticket.already_claimed", claimer=claimer.mention if claimer else t(lang, "ticket.unknown"))), ephemeral=True
            )
        await self.bot.db.claim_ticket(interaction.channel.id, interaction.user.id)
        embed = discord.Embed(
            description=t(lang, "ticket.claimed", member=interaction.user.mention),
            color=Colors.SUCCESS
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tunclaim", description="Libère la réclamation de ce ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def tunclaim(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)
        if not ticket.get("claimed_by"):
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_claimed_err")), ephemeral=True)
        await self.bot.db.unclaim_ticket(interaction.channel.id)
        embed = discord.Embed(
            description=t(lang, "ticket.unclaimed", member=interaction.user.mention),
            color=Colors.WARNING
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
