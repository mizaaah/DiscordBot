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


async def build_ticket_container(bot, guild, channel_id, lang):
    ticket = await bot.db.get_ticket(channel_id)
    if not ticket:
        return None
        
    config = await bot.db.get_ticket_config(guild.id)
    
    user_id = ticket["user_id"]
    user = guild.get_member(user_id)
    user_mention = user.mention if user else f"<@{user_id}>"
    user_avatar = user.avatar.url if user and user.avatar else (user.default_avatar.url if user else None)
    
    category = ticket.get("category")
    ticket_num = ticket.get("ticket_number")
    claimed_by = ticket.get("claimed_by")
    
    color = discord.Color(config.get("embed_color") or Colors.INFO.value)
    
    if category and "partenariat" in category.lower():
        welcome = f"Salut {user_mention} ! Merci de l'intérêt que tu portes à notre serveur.\nPrécise-nous ta demande de partenariat avec d'autres serveurs et un membre du staff te répondra vite."
    elif category and "staff" in category.lower():
        welcome = f"Salut {user_mention} ! Tu souhaites rejoindre notre équipe ?\nPrésente-toi et explique tes motivations pour recruter des gens / rejoindre le staff."
    else:
        template = config.get("welcome_message") or t(lang, "ticket.default_welcome")
        user_name = user.display_name if user else "Membre"
        welcome = (
            template
            .replace("{mention}", user_mention)
            .replace("{name}", user_name)
            .replace("{ticket_number}", f"{ticket_num:04d}")
            .replace("{category}", category or t(lang, "ticket.default_category"))
        )
        
    title = t(lang, "ticket.title_num", num=f"{ticket_num:04d}")
    if category:
        title += f" — {category}"
        
    cont = discord.ui.Container(accent_color=color.value)
    
    staff_id = config.get("staff_role_id")
    staff_role = guild.get_role(staff_id) if staff_id else None
    staff_str = staff_role.mention if staff_role else "`Non défini`"
    
    claimer_str = t(lang, 'ticket.not_claimed')
    if claimed_by:
        claimer = guild.get_member(claimed_by)
        if claimer: claimer_str = claimer.mention
        
    cat_str = f"\n**Catégorie :** `{category}`" if category else ""
    info_text = (
        f"**Informations du ticket**\n"
        f"**Support :** {staff_str}"
        f"{cat_str}\n"
        f"**Pris en charge :** {claimer_str}\n"
        f"**Membre :** {user_mention}"
    )
    
    thumb = discord.ui.Thumbnail(media=user_avatar) if user_avatar else None
    
    if thumb:
        cont.add_item(discord.ui.Section(
            discord.ui.TextDisplay(f"# {title}\n> {welcome.replace('\n', '\n> ')}"),
            accessory=thumb
        ))
    else:
        cont.add_item(discord.ui.TextDisplay(f"# {title}\n> {welcome.replace('\n', '\n> ')}"))
        
    cont.add_item(discord.ui.Separator())
    cont.add_item(discord.ui.TextDisplay(info_text))
    
    return cont
    
async def _open_ticket(bot: commands.Bot, interaction: discord.Interaction, category: str = None):
    guild = interaction.guild
    user = interaction.user
    lang = await bot.db.get_guild_lang(guild.id)
    
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    async def reply(msg: str = None, **kwargs):
        if interaction.response.is_done():
            await interaction.followup.send(msg, **kwargs)
        else:
            await interaction.response.send_message(msg, **kwargs)

    existing = await bot.db.get_user_open_ticket(guild.id, user.id, category)
    if existing:
        ch = guild.get_channel(existing["channel_id"])
        if ch:
            return await reply(embed=error_embed(t(lang, "ticket.already_open", channel=ch.mention)), ephemeral=True)

    config = await bot.db.get_ticket_config(guild.id)
    if not config.get("staff_role_id"):
        return await reply(embed=error_embed(t(lang, "ticket.not_configured")), ephemeral=True)

    ticket_cat = None
    if category:
        cats = config.get("categories") or []
        for c in cats:
            if c["name"] == category and c.get("category_id"):
                ticket_cat = guild.get_channel(c["category_id"])
                break
                
    if not ticket_cat and config.get("category_id"):
        ticket_cat = guild.get_channel(config["category_id"])
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

    cont = await build_ticket_container(bot, guild, channel.id, lang)
    view = TicketCloseView(bot, cont, config.get("close_button_label"), config.get("close_button_emoji"))
    
    await channel.send(view=view)
    await channel.send(user.mention, delete_after=1)
    await reply(embed=success_embed(t(lang, "ticket.created", channel=channel.mention)), ephemeral=True)

    if logs := bot.get_cog("Logs"):
        log_embed = discord.Embed(title=t(lang, "ticket.log_opened_title"), color=Colors.SUCCESS)
        log_embed.add_field(name=t(lang, "ticket.log_member"), value=f"> {user.mention} (`{user.id}`)", inline=True)
        log_embed.add_field(name=t(lang, "ticket.log_channel"), value=f"> {channel.mention}", inline=True)
        log_embed.add_field(name=t(lang, "ticket.log_number"), value=f"> `#{ticket_num:04d}`", inline=True)
        if category:
            log_embed.add_field(name=t(lang, "ticket.category_field"), value=f"> `{category}`", inline=True)
        await logs.send_log(guild, log_embed)


# ── Category select (ephemeral, non-persistent) ───────────────────────────────

class TicketCategorySelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, categories: list):
        self.bot = bot
        options = []
        for c in categories[:25]:
            desc = "Ouvrir un ticket."
            if "partenariat" in c["name"].lower():
                desc = "Pour faire des partenariats avec d'autres serveurs."
            elif "staff" in c["name"].lower():
                desc = "Pour recruter des gens."
            elif "aide" in c["name"].lower() or "support" in c["name"].lower():
                desc = "Besoin d'aide ou question."
            options.append(discord.SelectOption(label=c["name"], value=c["name"], emoji="🏷️", description=desc))
        super().__init__(placeholder="📂 Choisis une catégorie...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await _open_ticket(self.bot, interaction, self.values[0])


class TicketCategoryView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, categories: list, lang: str):
        super().__init__(timeout=60)
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        cont.add_item(discord.ui.TextDisplay(f"# {t(lang, 'ticket.pick_category')}"))
        cont.add_item(discord.ui.ActionRow(TicketCategorySelect(bot, categories)))
        self.add_item(cont)


# ── Persistent views ──────────────────────────────────────────────────────────

class TicketOpenView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, cont=None, label: str = None, emoji: str = None):
        super().__init__(timeout=None)
        self.bot = bot
        
        btn = discord.ui.Button(
            label=label or "Ouvrir un ticket",
            emoji=emoji or "📩",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_open_persistent"
        )
        btn.callback = self.open_ticket
        
        if cont:
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay("# 📩 Support et Assistance\nBesoin d'aide ? Cliquez sur le bouton ci-contre pour ouvrir un ticket."),
                accessory=btn
            ))
            self.add_item(cont)
        else:
            self.add_item(discord.ui.ActionRow(btn))

    async def open_ticket(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        categories = [c for c in (config.get("categories") or []) if c]

        if categories:
            await interaction.response.send_message(
                view=TicketCategoryView(self.bot, categories, lang),
                ephemeral=True
            )
        else:
            await _open_ticket(self.bot, interaction)



class TicketAddUserSelect(discord.ui.UserSelect):
    def __init__(self, lang: str):
        super().__init__(placeholder="Sélectionnez un membre à ajouter...", min_values=1, max_values=1)
        self.lang = lang

    async def callback(self, interaction: discord.Interaction):
        lang = self.lang
        membre = self.values[0]
        if not await interaction.client.db.get_ticket(interaction.channel.id):
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)
        await interaction.channel.set_permissions(
            membre, view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True
        )
        embed = discord.Embed(description=t(lang, "ticket.member_added", member=membre.mention), color=Colors.SUCCESS)
        await interaction.response.send_message(embed=embed)


class TicketRemoveUserSelect(discord.ui.UserSelect):
    def __init__(self, lang: str):
        super().__init__(placeholder="Sélectionnez un membre à retirer...", min_values=1, max_values=1)
        self.lang = lang

    async def callback(self, interaction: discord.Interaction):
        lang = self.lang
        membre = self.values[0]
        ticket = await interaction.client.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)
        if ticket["user_id"] == membre.id:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "ticket.cant_remove_creator")), ephemeral=True
            )
        await interaction.channel.set_permissions(membre, overwrite=None)
        embed = discord.Embed(description=t(lang, "ticket.member_removed", member=membre.mention), color=Colors.WARNING)
        await interaction.response.send_message(embed=embed)

class TicketCloseView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, cont=None, label: str = None, emoji: str = None):
        super().__init__(timeout=None)
        self.bot = bot
        
        btn_close = discord.ui.Button(
            label=label or "Fermer",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_close_persistent"
        )
        btn_close.callback = self.close_ticket
        
        btn_claim = discord.ui.Button(label="Prendre en charge", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
        btn_claim.callback = self.claim_ticket
        
        btn_unclaim = discord.ui.Button(label="Se retirer", style=discord.ButtonStyle.secondary, custom_id="ticket_unclaim")
        btn_unclaim.callback = self.unclaim_ticket
        
        btn_add = discord.ui.Button(label="Ajouter", style=discord.ButtonStyle.secondary, custom_id="ticket_add")
        btn_add.callback = self.add_member
        
        btn_remove = discord.ui.Button(label="Retirer", style=discord.ButtonStyle.secondary, custom_id="ticket_remove")
        btn_remove.callback = self.remove_member
        
        if cont:
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay("✋ **Prise en charge**\nS'assigner ce ticket pour le gérer."),
                accessory=btn_claim
            ))
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay("👋 **Se retirer**\nNe plus gérer ce ticket."),
                accessory=btn_unclaim
            ))
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay("➕ **Ajouter un membre**\nDonner l'accès au ticket à un utilisateur."),
                accessory=btn_add
            ))
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay("➖ **Retirer un membre**\nEnlever l'accès au ticket."),
                accessory=btn_remove
            ))
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay("🔒 **Fermeture**\nArchiver et clôturer le ticket."),
                accessory=btn_close
            ))
            self.add_item(cont)
        else:
            # Fallback for cog_load persistent view registration
            self.add_item(discord.ui.ActionRow(btn_claim, btn_unclaim, btn_add, btn_remove, btn_close))

    async def manage_action(self, interaction: discord.Interaction):
        pass

    async def unclaim_ticket(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)
            
        if ticket.get("claimed_by") != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("Vous n'êtes pas en charge de ce ticket !"), ephemeral=True)
            
        await self.bot.db.unclaim_ticket(interaction.channel.id)
        embed = discord.Embed(description=t(lang, "ticket.unclaimed", member=interaction.user.mention), color=Colors.WARNING)
        await interaction.response.send_message(embed=embed)
        
        # Rebuild view
        cont = await build_ticket_container(self.bot, interaction.guild, interaction.channel.id, lang)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        new_view = TicketCloseView(self.bot, cont, config.get("close_button_label"), config.get("close_button_emoji"))
        if interaction.message:
            await interaction.message.edit(view=new_view)
                
    async def claim_ticket(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)
            
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_id = config.get("staff_role_id")
        is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))
        if not is_staff:
            return await interaction.response.send_message(embed=error_embed("Seul le staff peut prendre en charge un ticket."), ephemeral=True)

        if ticket.get("claimed_by"):
            claimer = interaction.guild.get_member(ticket["claimed_by"])
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "ticket.already_claimed", claimer=claimer.mention if claimer else t(lang, "ticket.unknown"))), ephemeral=True
            )
                
        # Claim
        await self.bot.db.claim_ticket(interaction.channel.id, interaction.user.id)
        embed = discord.Embed(description=t(lang, "ticket.claimed", member=interaction.user.mention), color=Colors.SUCCESS)
        await interaction.response.send_message(embed=embed)
        
        # Rebuild view
        cont = await build_ticket_container(self.bot, interaction.guild, interaction.channel.id, lang)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        new_view = TicketCloseView(self.bot, cont, config.get("close_button_label"), config.get("close_button_emoji"))
        if interaction.message:
            await interaction.message.edit(view=new_view)

    async def add_member(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_id = config.get("staff_role_id")
        is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))
        if not is_staff:
            return await interaction.response.send_message(embed=error_embed("Seul le staff peut ajouter des membres."), ephemeral=True)
            
        view = discord.ui.View(timeout=30)
        view.add_item(TicketAddUserSelect(lang))
        await interaction.response.send_message(embed=info_embed("Sélectionnez le membre à ajouter au ticket :"), view=view, ephemeral=True)

    async def remove_member(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_id = config.get("staff_role_id")
        is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))
        if not is_staff:
            return await interaction.response.send_message(embed=error_embed("Seul le staff peut retirer des membres."), ephemeral=True)
            
        view = discord.ui.View(timeout=30)
        view.add_item(TicketRemoveUserSelect(lang))
        await interaction.response.send_message(embed=info_embed("Sélectionnez le membre à retirer du ticket :"), view=view, ephemeral=True)

    async def close_ticket(self, interaction: discord.Interaction):
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

        cont = discord.ui.Container(accent_color=Colors.WARNING.value)
        cont.add_item(discord.ui.TextDisplay(f"# Confirmation\n{t(lang, 'ticket.close_confirm_prompt')}"))
        
        await interaction.response.send_message(
            view=TicketCloseConfirmView(self.bot, ticket, config, lang, cont),
            ephemeral=True
        )


class TicketCloseConfirmView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, ticket: dict, config: dict, lang: str, cont=None):
        super().__init__(timeout=30)
        self.bot    = bot
        self.ticket = ticket
        self.config = config
        self.lang   = lang

        if cont:
            self.add_item(cont)

        btn_confirm = discord.ui.Button(label="✅ Confirmer", style=discord.ButtonStyle.danger)
        btn_confirm.callback = self.confirm
        
        btn_cancel = discord.ui.Button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
        btn_cancel.callback = self.cancel
        
        self.add_item(discord.ui.ActionRow(btn_confirm, btn_cancel))

    async def confirm(self, interaction: discord.Interaction):
        lang = self.lang
        for child in self.children:
            if isinstance(child, discord.ui.ActionRow):
                for btn in child.children:
                    btn.disabled = True
        await interaction.response.edit_message(view=self, embed=None)

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
        open_time_str = self.ticket.get("created_at")
        duration   = ""
        if open_time_str:
            try:
                open_time = datetime.fromisoformat(open_time_str)
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=timezone.utc)
                mins = int((close_time - open_time).total_seconds() // 60)
                duration = f"{mins // 60}h {mins % 60}min" if mins >= 60 else f"{mins} min"
            except (ValueError, TypeError):
                pass

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
                    value=f"> {owner.mention if owner else str(self.ticket['user_id'])}",
                    inline=True
                )
                embed.add_field(name=t(lang, "ticket.closed_by"), value=f"> {interaction.user.mention}", inline=True)
                if self.ticket.get("category"):
                    embed.add_field(name=t(lang, "ticket.category_field"), value=f"> `{self.ticket['category']}`", inline=True)
                if duration:
                    embed.add_field(name=t(lang, "ticket.duration_field"), value=f"> `{duration}`", inline=True)
                if self.ticket.get("claimed_by"):
                    claimer = guild.get_member(self.ticket["claimed_by"])
                    embed.add_field(
                        name=t(lang, "ticket.claimed_by_field"),
                        value=f"> {claimer.mention if claimer else str(self.ticket['claimed_by'])}",
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

    async def cancel(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.ActionRow):
                for btn in child.children:
                    btn.disabled = True
        await interaction.response.edit_message(view=self, embed=None)
        await interaction.followup.send(embed=info_embed(t(self.lang, "ticket.close_cancelled")), ephemeral=True)


# ── Cog ───────────────────────────────────────────────────────────────────────

# ── Setup Dashboard ────────────────────────────────────────────────────────────

class TicketSetupRoleSelect(discord.ui.RoleSelect):
    def __init__(self, lang: str):
        super().__init__(placeholder="Sélectionner le rôle Staff...")

    async def callback(self, interaction: discord.Interaction):
        view: "TicketSetupDashboardView" = self.view
        role = self.values[0]
        await interaction.client.db.update_ticket_config(interaction.guild.id, "staff_role_id", role.id)
        await view.refresh(interaction)

class TicketSetupCategorySelect(discord.ui.ChannelSelect):
    def __init__(self, lang: str):
        super().__init__(placeholder="Sélectionner une catégorie...", channel_types=[discord.ChannelType.category])

    async def callback(self, interaction: discord.Interaction):
        view: "TicketSetupDashboardView" = self.view
        channel = self.values[0]
        await interaction.client.db.update_ticket_config(interaction.guild.id, "category_id", channel.id)
        await view.refresh(interaction)

class TicketSetupLogsSelect(discord.ui.ChannelSelect):
    def __init__(self, lang: str):
        super().__init__(placeholder="Sélectionner un salon de logs...", channel_types=[discord.ChannelType.text])

    async def callback(self, interaction: discord.Interaction):
        view: "TicketSetupDashboardView" = self.view
        channel = self.values[0]
        await interaction.client.db.update_ticket_config(interaction.guild.id, "log_channel_id", channel.id)
        await view.refresh(interaction)

class TicketDeploySelect(discord.ui.ChannelSelect):
    def __init__(self, lang: str):
        super().__init__(placeholder="Où envoyer le panel ?", channel_types=[discord.ChannelType.text])

    async def callback(self, interaction: discord.Interaction):
        view: "TicketSetupDashboardView" = self.view
        salon = interaction.guild.get_channel(self.values[0].id)
        if not salon:
            return await interaction.response.send_message("Salon introuvable.", ephemeral=True)
        lang = view.lang
        db = interaction.client.db
        gid = interaction.guild.id
        config = await db.get_ticket_config(gid)
        
        color  = discord.Color(config.get("embed_color") or Colors.INFO.value)
        cont = discord.ui.Container(accent_color=color.value)
        cont.add_item(discord.ui.TextDisplay(f"# {t(lang, 'ticket.panel_title')}\n{t(lang, 'ticket.panel_desc').replace('\n', ' ')}"))
        cont.add_item(discord.ui.Separator())
        t_view = TicketOpenView(view.bot, cont, config.get("open_button_label"), config.get("open_button_emoji"))
        panel = await salon.send(view=t_view)

        await db.update_ticket_config(gid, "panel_message_id", panel.id)
        await db.update_ticket_config(gid, "panel_channel_id", salon.id)

        await view.refresh(interaction)
        await interaction.followup.send(embed=success_embed(f"Le panel a été déployé dans {salon.mention} !"), ephemeral=True)

class TicketCategoriesModal(discord.ui.Modal):
    def __init__(self, view: "TicketSetupDashboardView", current_cats: str):
        super().__init__(title="Choix de Catégories")
        self._view = view
        self.categories = discord.ui.TextInput(
            label="Catégories (séparées par des virgules)",
            style=discord.TextStyle.long,
            required=False,
            default=current_cats,
            placeholder="Ex: Support, Plainte (Laissez vide pour désactiver)"
        )
        self.add_item(self.categories)

    async def on_submit(self, interaction: discord.Interaction):
        cats_str = self.categories.value.strip()
        cat_names = [c.strip() for c in cats_str.split(",") if c.strip()][:10]
        
        db = interaction.client.db
        gid = interaction.guild.id
        old_config = await db.get_ticket_config(gid)
        old_cats = old_config.get("categories") or []
        
        new_cats = []
        for name in cat_names:
            cid = None
            for old in old_cats:
                if isinstance(old, dict) and old["name"] == name:
                    cid = old.get("category_id")
            new_cats.append({"name": name, "category_id": cid})
            
        await db.update_ticket_config(gid, "categories", new_cats)
        await self._view.refresh(interaction)

class TicketButtonsModal(discord.ui.Modal):
    open_label = discord.ui.TextInput(label="Texte bouton Ouvrir", required=False, placeholder="Ex: Ouvrir un ticket")
    open_emoji = discord.ui.TextInput(label="Emoji bouton Ouvrir", required=False, placeholder="Ex: 📩")
    close_label = discord.ui.TextInput(label="Texte bouton Fermer", required=False, placeholder="Ex: Fermer le ticket")
    close_emoji = discord.ui.TextInput(label="Emoji bouton Fermer", required=False, placeholder="Ex: 🔒")

    def __init__(self, view: "TicketSetupDashboardView"):
        super().__init__(title="Personnalisation des boutons")
        self._view = view

    async def on_submit(self, interaction: discord.Interaction):
        db = interaction.client.db
        gid = interaction.guild.id
        
        if self.open_label.value.strip():
            await db.update_ticket_config(gid, "open_button_label", self.open_label.value.strip())
        if self.open_emoji.value.strip():
            await db.update_ticket_config(gid, "open_button_emoji", self.open_emoji.value.strip())
        if self.close_label.value.strip():
            await db.update_ticket_config(gid, "close_button_label", self.close_label.value.strip())
        if self.close_emoji.value.strip():
            await db.update_ticket_config(gid, "close_button_emoji", self.close_emoji.value.strip())
            
        await self._view.refresh(interaction)

class TicketSetupDashboardView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, lang: str, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.lang = lang
        self.guild_id = guild_id
    async def execute_action(self, interaction: discord.Interaction, val: str):
        lang = self.lang
        
        if val == "categories_list":
            config = await interaction.client.db.get_ticket_config(interaction.guild.id)
            cats = config.get("categories") or []
            current_str = ", ".join(c["name"] for c in cats)
            return await interaction.response.send_modal(TicketCategoriesModal(self, current_str))
        elif val == "buttons":
            return await interaction.response.send_modal(TicketButtonsModal(self))
            
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        
        if val == "staff":
            cont.add_item(discord.ui.TextDisplay("👮 **Rôle du Staff**\n> Sélectionnez le rôle qui sera autorisé à gérer et répondre aux tickets."))
            cont.add_item(discord.ui.ActionRow(TicketSetupRoleSelect(lang)))
            
        elif val == "category":
            cont.add_item(discord.ui.TextDisplay("📁 **Catégorie Principale**\n> Sélectionnez la catégorie Discord (le dossier) où les nouveaux salons de tickets seront créés."))
            cont.add_item(discord.ui.ActionRow(TicketSetupCategorySelect(lang)))
            
        elif val == "logs":
            cont.add_item(discord.ui.TextDisplay("🪵 **Salon des Logs**\n> Sélectionnez le salon où envoyer la transcription complète (historique des messages) des tickets fermés."))
            cont.add_item(discord.ui.ActionRow(TicketSetupLogsSelect(lang)))
            
        elif val == "link_category":
            config = await interaction.client.db.get_ticket_config(interaction.guild.id)
            cats = config.get("categories") or []
            if not cats:
                return await interaction.response.send_message(embed=error_embed("Vous n'avez pas encore défini de choix de catégories."), ephemeral=True)
                
            cont.add_item(discord.ui.TextDisplay("🔗 **Lier un Type de Ticket**\n> Sélectionnez d'abord le choix de ticket que vous souhaitez lier à un dossier spécifique."))
            options = [discord.SelectOption(label=c["name"], value=c["name"]) for c in cats]
            
            class ChoiceSelect(discord.ui.Select):
                def __init__(self, dashboard_view):
                    self.dashboard_view = dashboard_view
                    super().__init__(placeholder="Choisissez un type de ticket...", options=options)
                    
                async def callback(self, inter: discord.Interaction):
                    choice_name = self.values[0]
                    cont2 = discord.ui.Container(accent_color=Colors.INFO.value)
                    cont2.add_item(discord.ui.TextDisplay(f"🔗 **Lier `{choice_name}`**\n> Sélectionnez la Catégorie Discord (dossier) où les tickets de type `{choice_name}` devront s'ouvrir."))
                    
                    class CatSelect(discord.ui.ChannelSelect):
                        def __init__(self, dashboard_view):
                            self.dashboard_view = dashboard_view
                            super().__init__(channel_types=[discord.ChannelType.category])
                            
                        async def callback(self, i2: discord.Interaction):
                            cat_id = self.values[0].id
                            db = i2.client.db
                            old_config = await db.get_ticket_config(i2.guild.id)
                            old_cats = old_config.get("categories") or []
                            for c in old_cats:
                                if c["name"] == choice_name:
                                    c["category_id"] = cat_id
                            await db.update_ticket_config(i2.guild.id, "categories", old_cats)
                            await self.dashboard_view.refresh(i2)
                            
                    cat_sel = CatSelect(self.dashboard_view)
                    cont2.add_item(discord.ui.ActionRow(cat_sel))
                    
                    async def back_callback2(i2: discord.Interaction):
                        await self.dashboard_view.refresh(i2)
                    btn_back2 = discord.ui.Button(label="Retour au Dashboard", style=discord.ButtonStyle.secondary)
                    btn_back2.callback = back_callback2
                    cont2.add_item(discord.ui.ActionRow(btn_back2))
                    
                    self.dashboard_view.clear_items()
                    self.dashboard_view.add_item(cont2)
                    await inter.response.edit_message(view=self.dashboard_view)
                    
            choice_sel = ChoiceSelect(self)
            cont.add_item(discord.ui.ActionRow(choice_sel))
            
        elif val == "deploy":
            cont = discord.ui.Container(accent_color=Colors.SUCCESS.value)
            cont.add_item(discord.ui.TextDisplay("🚀 **Déploiement du Panel**\n> Sélectionnez le salon où les membres pourront cliquer sur le bouton pour ouvrir un ticket."))
            cont.add_item(discord.ui.ActionRow(TicketDeploySelect(lang)))

        async def back_callback(inter: discord.Interaction):
            await self.refresh(inter)
            
        btn_back = discord.ui.Button(label="Retour au Dashboard", style=discord.ButtonStyle.secondary)
        btn_back.callback = back_callback
        cont.add_item(discord.ui.ActionRow(btn_back))
        
        self.clear_items()
        self.add_item(cont)
        await interaction.response.edit_message(view=self)

        
    async def build(self, guild: discord.Guild):
        self.clear_items()
        config = await self.bot.db.get_ticket_config(self.guild_id)
        
        def ch(cid):
            if not cid: return "Non défini"
            c = guild.get_channel(cid)
            return c.mention if c else "Introuvable"

        def role(rid):
            if not rid: return "Non défini"
            r = guild.get_role(rid)
            return r.mention if r else "Introuvable"

        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        cont.add_item(discord.ui.TextDisplay(f"# 🎫 Configuration des Tickets\n> Préparez le système de support de {guild.name} étape par étape.\n"))
        cont.add_item(discord.ui.Separator())

        def make_nav(action: str):
            async def nav_cb(inter: discord.Interaction):
                await self.execute_action(inter, action)
            return nav_cb

        # Staff
        staff_role = role(config.get("staff_role_id"))
        btn_staff = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_staff.callback = make_nav("staff")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"👮 **Rôle du Staff**\n> **Rôle actuel :** {staff_role}\n> Les membres avec ce rôle auront accès à tous les tickets."), accessory=btn_staff))
        cont.add_item(discord.ui.Separator())

        # Catégorie Mère
        category_ch = ch(config.get("category_id"))
        btn_cat = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_cat.callback = make_nav("category")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"📁 **Catégorie Principale**\n> **Dossier actuel :** {category_ch}\n> Dossier Discord où s'ouvriront les tickets par défaut."), accessory=btn_cat))
        cont.add_item(discord.ui.Separator())

        # Logs
        log_ch = ch(config.get("log_channel_id"))
        btn_logs = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_logs.callback = make_nav("logs")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🪵 **Transcriptions (Logs)**\n> **Salon actuel :** {log_ch}\n> Salon où envoyer l'historique complet des tickets fermés."), accessory=btn_logs))
        cont.add_item(discord.ui.Separator())

        # Choix et Liaisons
        cats = [c for c in (config.get("categories") or []) if c]
        cats_str = "Aucun"
        if cats:
            parts = []
            for c in cats:
                cat_id = c.get("category_id")
                discord_cat = guild.get_channel(cat_id) if cat_id else None
                if discord_cat:
                    parts.append(f"`{c['name']}` (📁 {discord_cat.name})")
                else:
                    parts.append(f"`{c['name']}`")
            cats_str = ", ".join(parts)
            
        btn_choices = discord.ui.Button(label="Modifier les types", style=discord.ButtonStyle.secondary)
        btn_choices.callback = make_nav("categories_list")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🏷️ **Types de Tickets**\n> **Actuels :** {cats_str}\n> Définissez les choix proposés aux membres (ex: Support, Plainte)."), accessory=btn_choices))
        cont.add_item(discord.ui.Separator())

        btn_link = discord.ui.Button(label="Lier une catégorie", style=discord.ButtonStyle.secondary)
        btn_link.callback = make_nav("link_category")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🔗 **Liaison des Dossiers**\n> Redirigez certains types de tickets dans des dossiers Discord spécifiques."), accessory=btn_link))
        cont.add_item(discord.ui.Separator())

        # Personnalisation
        open_btn = f"{config.get('open_button_emoji') or '📩'} {config.get('open_button_label') or 'Ouvrir un ticket'}".strip()
        close_btn = f"{config.get('close_button_emoji') or '🔒'} {config.get('close_button_label') or 'Fermer le ticket'}".strip()
        btn_cust = discord.ui.Button(label="Personnaliser", style=discord.ButtonStyle.secondary)
        btn_cust.callback = make_nav("buttons")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🎨 **Personnalisation des Boutons**\n> **Ouvrir :** `{open_btn}` | **Fermer :** `{close_btn}`"), accessory=btn_cust))
        cont.add_item(discord.ui.Separator())

        # Déploiement
        btn_deploy = discord.ui.Button(label="Déployer le Panel", style=discord.ButtonStyle.success)
        btn_deploy.callback = make_nav("deploy")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🚀 **Déploiement du Panel**\n> Envoyez le menu interactif final dans le salon de votre choix."), accessory=btn_deploy))

        self.add_item(cont)

    async def refresh(self, interaction: discord.Interaction):
        await self.build(interaction.guild)
        await interaction.response.edit_message(view=self, embed=None)


# ── Cog ───────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketOpenView(self.bot))
        self.bot.add_view(TicketCloseView(self.bot))

    ticket_group = app_commands.Group(name="ticket", description="Gestion du système de tickets")

    @ticket_group.command(name="setup", description="Ouvre le Dashboard de configuration des tickets")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_setup(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        view = TicketSetupDashboardView(self.bot, lang, interaction.guild.id)
        await view.build(interaction.guild)
        await interaction.response.send_message(view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
