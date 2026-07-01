import asyncio
import io
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors


# ── Shared ticket-creation logic ──────────────────────────────────────────────

async def _open_ticket(bot: commands.Bot, interaction: discord.Interaction, category: str = None):
    guild = interaction.guild
    user = interaction.user

    async def reply(msg: str = None, **kwargs):
        if interaction.response.is_done():
            await interaction.followup.send(msg, **kwargs)
        else:
            await interaction.response.send_message(msg, **kwargs)

    existing = await bot.db.get_user_open_ticket(guild.id, user.id)
    if existing:
        ch = guild.get_channel(existing["channel_id"])
        if ch:
            return await reply(f"❌ Tu as déjà un ticket ouvert : {ch.mention}", ephemeral=True)

    config = await bot.db.get_ticket_config(guild.id)
    if not config.get("staff_role_id"):
        return await reply("❌ Le système de tickets n'est pas encore configuré.", ephemeral=True)

    ticket_cat   = guild.get_channel(config["category_id"])  if config.get("category_id")  else None
    staff_role   = guild.get_role(config["staff_role_id"])   if config.get("staff_role_id") else None
    ticket_num   = await bot.db.increment_ticket_counter(guild.id)
    slug         = category.lower().replace(" ", "-") if category else "ticket"
    channel_name = f"{slug}-{ticket_num:04d}"

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
        return await reply("❌ Je n'ai pas la permission de créer un salon.", ephemeral=True)

    await bot.db.create_ticket(guild.id, channel.id, user.id, ticket_num, category)

    # ── Build welcome embed ──────────────────────────────────────────────────
    color = discord.Color(config.get("embed_color") or Colors.INFO.value)
    template = config.get("welcome_message") or (
        "Bienvenue {mention} !\n\n"
        "Décris ton problème ou ta demande et notre équipe te répondra dès que possible.\n"
        "Clique sur **🔒 Fermer** quand ton problème est résolu."
    )
    welcome = (
        template
        .replace("{mention}", user.mention)
        .replace("{name}", user.display_name)
        .replace("{ticket_number}", f"{ticket_num:04d}")
        .replace("{category}", category or "Général")
    )

    title = f"🎫 Ticket #{ticket_num:04d}"
    if category:
        title += f" — {category}"

    embed = discord.Embed(title=title, description=welcome, color=color)
    if staff_role:
        embed.add_field(name="👥 Support", value=staff_role.mention, inline=True)
    if category:
        embed.add_field(name="🏷️ Catégorie", value=category, inline=True)
    embed.add_field(name="🙋 Réclamé par", value="*Non réclamé*", inline=True)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"ID membre : {user.id}")

    await channel.send(embed=embed, view=TicketCloseView(bot))
    await channel.send(user.mention, delete_after=1)
    await reply(f"✅ Ticket créé : {channel.mention}", ephemeral=True)

    if logs := bot.get_cog("Logs"):
        log_embed = discord.Embed(title="🎫 Ticket ouvert", color=Colors.SUCCESS)
        log_embed.add_field(name="Membre", value=f"{user.mention} (`{user.id}`)", inline=True)
        log_embed.add_field(name="Salon", value=channel.mention, inline=True)
        log_embed.add_field(name="Numéro", value=f"#{ticket_num:04d}", inline=True)
        if category:
            log_embed.add_field(name="Catégorie", value=category, inline=True)
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
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="📩 Ouvrir un ticket",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_open_persistent"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        categories = [c for c in (config.get("categories") or []) if c]

        if categories:
            await interaction.response.send_message(
                "📂 Choisis une catégorie pour ton ticket :",
                view=TicketCategoryView(self.bot, categories),
                ephemeral=True
            )
        else:
            await _open_ticket(self.bot, interaction)


class TicketCloseView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="🔒 Fermer le ticket",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close_persistent"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)

        config      = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_id    = config.get("staff_role_id")
        is_owner    = ticket["user_id"] == interaction.user.id
        is_staff    = (
            interaction.user.guild_permissions.manage_channels
            or (staff_id and any(r.id == staff_id for r in interaction.user.roles))
        )

        if not (is_owner or is_staff):
            return await interaction.response.send_message(
                "❌ Seul le créateur ou un membre du staff peut fermer ce ticket.", ephemeral=True
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                description="⚠️ Es-tu sûr de vouloir fermer ce ticket ?",
                color=Colors.WARNING
            ),
            view=TicketCloseConfirmView(self.bot, ticket, config),
            ephemeral=True
        )


class TicketCloseConfirmView(discord.ui.View):
    def __init__(self, bot: commands.Bot, ticket: dict, config: dict):
        super().__init__(timeout=30)
        self.bot    = bot
        self.ticket = ticket
        self.config = config

    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
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
                    title=f"🎫 Ticket #{self.ticket['ticket_number']:04d} — Fermé",
                    color=Colors.ERROR
                )
                embed.add_field(
                    name="Ouvert par",
                    value=owner.mention if owner else str(self.ticket["user_id"]),
                    inline=True
                )
                embed.add_field(name="Fermé par", value=interaction.user.mention, inline=True)
                if self.ticket.get("category"):
                    embed.add_field(name="Catégorie", value=self.ticket["category"], inline=True)
                if duration:
                    embed.add_field(name="Durée", value=duration, inline=True)
                if self.ticket.get("claimed_by"):
                    claimer = guild.get_member(self.ticket["claimed_by"])
                    embed.add_field(
                        name="Réclamé par",
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
                description="🔒 Ticket fermé. Suppression dans **5 secondes**...",
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
        await interaction.response.send_message("Fermeture annulée.", ephemeral=True)


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
            title="🎫 Support — Ouvrir un ticket",
            description=(
                "Clique sur le bouton ci-dessous pour ouvrir un ticket de support.\n"
                "Notre équipe te répondra dès que possible."
            ),
            color=color
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text=interaction.guild.name)

        view  = TicketOpenView(self.bot)
        panel = await salon.send(embed=embed, view=view)

        await db.update_ticket_config(gid, "panel_message_id", panel.id)
        await db.update_ticket_config(gid, "panel_channel_id", salon.id)

        await interaction.response.send_message(
            f"✅ Système de tickets configuré ! Panel envoyé dans {salon.mention}.", ephemeral=True
        )

    @ticket_group.command(name="categories", description="Définit les catégories de tickets (menu déroulant à l'ouverture)")
    @app_commands.describe(categories="Catégories séparées par des virgules — laisser vide pour désactiver")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_categories(self, interaction: discord.Interaction, categories: str = ""):
        cats = [c.strip() for c in categories.split(",") if c.strip()][:10]
        await self.bot.db.update_ticket_config(interaction.guild.id, "categories", cats)

        if cats:
            embed = discord.Embed(
                title="✅ Catégories mises à jour",
                description="\n".join(f"🏷️ **{c}**" for c in cats),
                color=Colors.SUCCESS
            )
            embed.set_footer(text="Un menu déroulant apparaîtra à l'ouverture du ticket.")
        else:
            embed = discord.Embed(
                description="✅ Catégories désactivées — les tickets s'ouvrent directement.",
                color=Colors.SUCCESS
            )
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="couleur", description="Change la couleur des embeds de tickets")
    @app_commands.describe(couleur="Code hexadécimal (ex: FF0000 ou #FF0000)")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_couleur(self, interaction: discord.Interaction, couleur: str):
        try:
            color_int = int(couleur.lstrip("#"), 16)
            if not 0 <= color_int <= 0xFFFFFF:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Couleur invalide. Exemple : `FF0000` ou `#FF0000`", ephemeral=True
            )
        await self.bot.db.update_ticket_config(interaction.guild.id, "embed_color", color_int)
        embed = discord.Embed(
            description=f"✅ Couleur des embeds de tickets mise à jour.",
            color=discord.Color(color_int)
        )
        embed.add_field(name="Code couleur", value=f"`#{color_int:06X}`")
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="message", description="Personnalise le message d'accueil dans les tickets")
    @app_commands.describe(message="Variables dispo : {mention} {name} {ticket_number} {category}")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_message(self, interaction: discord.Interaction, message: str):
        await self.bot.db.update_ticket_config(interaction.guild.id, "welcome_message", message)
        preview = (
            message
            .replace("{mention}", interaction.user.mention)
            .replace("{name}", interaction.user.display_name)
            .replace("{ticket_number}", "0001")
            .replace("{category}", "Support")
        )
        embed = discord.Embed(
            title="✅ Message d'accueil mis à jour",
            color=Colors.SUCCESS
        )
        embed.add_field(name="Aperçu", value=preview, inline=False)
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="config", description="Affiche la configuration actuelle des tickets")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_config(self, interaction: discord.Interaction):
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        color  = discord.Color(config.get("embed_color") or Colors.INFO.value)

        staff_role  = interaction.guild.get_role(config["staff_role_id"])    if config.get("staff_role_id")    else None
        category_ch = interaction.guild.get_channel(config["category_id"])   if config.get("category_id")      else None
        log_ch      = interaction.guild.get_channel(config["log_channel_id"]) if config.get("log_channel_id")  else None

        embed = discord.Embed(title="🎫 Configuration des tickets", color=color)
        embed.add_field(name="Rôle staff",       value=staff_role.mention    if staff_role   else "❌ Non configuré",  inline=True)
        embed.add_field(name="Catégorie Discord", value=category_ch.mention  if category_ch  else "❌ Non configurée", inline=True)
        embed.add_field(name="Salon de logs",     value=log_ch.mention       if log_ch       else "❌ Non configuré",  inline=True)
        embed.add_field(name="Couleur",           value=f"`#{config.get('embed_color', Colors.INFO.value):06X}`", inline=True)
        embed.add_field(name="Tickets ouverts",   value=str(config.get("ticket_counter", 0)), inline=True)

        cats = [c for c in (config.get("categories") or []) if c]
        embed.add_field(
            name=f"Catégories ({len(cats)})",
            value="\n".join(f"🏷️ {c}" for c in cats) or "*Aucune (ouverture directe)*",
            inline=False
        )
        welcome = config.get("welcome_message")
        embed.add_field(
            name="Message d'accueil",
            value=f"`{welcome[:80]}...`" if welcome and len(welcome) > 80 else (f"`{welcome}`" if welcome else "*Message par défaut*"),
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /tadd /tremove ────────────────────────────────────────────────────────

    @app_commands.command(name="tadd", description="Ajoute un membre à ce ticket")
    @app_commands.describe(membre="Le membre à ajouter")
    @app_commands.default_permissions(manage_channels=True)
    async def tadd(self, interaction: discord.Interaction, membre: discord.Member):
        if not await self.bot.db.get_ticket(interaction.channel.id):
            return await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        await interaction.channel.set_permissions(
            membre, view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True
        )
        embed = discord.Embed(description=f"✅ {membre.mention} a été ajouté au ticket.", color=Colors.SUCCESS)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tremove", description="Retire un membre de ce ticket")
    @app_commands.describe(membre="Le membre à retirer")
    @app_commands.default_permissions(manage_channels=True)
    async def tremove(self, interaction: discord.Interaction, membre: discord.Member):
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        if ticket["user_id"] == membre.id:
            return await interaction.response.send_message(
                "❌ Impossible de retirer le créateur du ticket.", ephemeral=True
            )
        await interaction.channel.set_permissions(membre, overwrite=None)
        embed = discord.Embed(description=f"✅ {membre.mention} a été retiré du ticket.", color=Colors.WARNING)
        await interaction.response.send_message(embed=embed)

    # ── /tclaim /tunclaim ─────────────────────────────────────────────────────

    @app_commands.command(name="tclaim", description="Réclame ce ticket — indique que tu t'en occupes")
    @app_commands.default_permissions(manage_channels=True)
    async def tclaim(self, interaction: discord.Interaction):
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        if ticket.get("claimed_by"):
            claimer = interaction.guild.get_member(ticket["claimed_by"])
            return await interaction.response.send_message(
                f"❌ Ce ticket est déjà réclamé par {claimer.mention if claimer else '`inconnu`'}.", ephemeral=True
            )
        await self.bot.db.claim_ticket(interaction.channel.id, interaction.user.id)
        embed = discord.Embed(
            description=f"🙋 {interaction.user.mention} a réclamé ce ticket et s'en occupe.",
            color=Colors.SUCCESS
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tunclaim", description="Libère la réclamation de ce ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def tunclaim(self, interaction: discord.Interaction):
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        if not ticket.get("claimed_by"):
            return await interaction.response.send_message("❌ Ce ticket n'est pas réclamé.", ephemeral=True)
        await self.bot.db.unclaim_ticket(interaction.channel.id)
        embed = discord.Embed(
            description=f"🔓 {interaction.user.mention} a libéré la réclamation de ce ticket.",
            color=Colors.WARNING
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
