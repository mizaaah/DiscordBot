import asyncio
import io
import json
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
            discord.ui.TextDisplay(f"# {title}\n> {welcome.replace(chr(10), chr(10) + '> ')}"),
            accessory=thumb
        ))
    else:
        cont.add_item(discord.ui.TextDisplay(f"# {title}\n> {welcome.replace(chr(10), chr(10) + '> ')}"))
        
    cont.add_item(discord.ui.Separator())
    cont.add_item(discord.ui.TextDisplay(info_text))
    
    # ── Afficher les réponses du formulaire ────────────────────────────────
    form_responses_raw = ticket.get("form_responses")
    if form_responses_raw:
        try:
            responses = json.loads(form_responses_raw) if isinstance(form_responses_raw, str) else form_responses_raw
        except (json.JSONDecodeError, TypeError):
            responses = None
        if responses:
            cont.add_item(discord.ui.Separator())
            resp_text = "**📋 Réponses du formulaire**\n"
            for question, answer in responses.items():
                resp_text += f"> **{question}**\n> {answer}\n"
            cont.add_item(discord.ui.TextDisplay(resp_text))
    
    return cont
    

# ── Ticket Form Modal ─────────────────────────────────────────────────────────

class TicketFormModal(discord.ui.Modal):
    """Dynamic modal with up to 5 questions for opening a ticket."""
    
    def __init__(self, bot: commands.Bot, questions: list[dict], category: str = None):
        super().__init__(title="📋 Formulaire de ticket")
        self.bot = bot
        self.category = category
        self.question_inputs = []
        
        for q in questions[:5]:
            text_input = discord.ui.TextInput(
                label=q.get("label", "Question")[:45],
                placeholder=q.get("placeholder", "")[:100],
                style=discord.TextStyle.long if q.get("long", False) else discord.TextStyle.short,
                required=q.get("required", True),
                max_length=q.get("max_length", 1024),
            )
            self.add_item(text_input)
            self.question_inputs.append((q.get("label", "Question"), text_input))
    
    async def on_submit(self, interaction: discord.Interaction):
        responses = {}
        for label, text_input in self.question_inputs:
            responses[label] = text_input.value
        
        await _open_ticket(self.bot, interaction, self.category, form_responses=responses)


async def _open_ticket(bot: commands.Bot, interaction: discord.Interaction, category: str = None, form_responses: dict = None):
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

    await bot.db.create_ticket(guild.id, channel.id, user.id, ticket_num, category, form_responses)

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
        category = self.values[0]
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        questions = config.get("questions") or {}
        
        # Check if this category has questions defined
        cat_questions = questions.get(category)
        if cat_questions:
            modal = TicketFormModal(self.bot, cat_questions, category)
            await interaction.response.send_modal(modal)
        else:
            await _open_ticket(self.bot, interaction, category)


class TicketCategoryView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, categories: list, lang: str):
        super().__init__(timeout=60)
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        cont.add_item(discord.ui.TextDisplay(f"# {t(lang, 'ticket.pick_category')}"))
        cont.add_item(discord.ui.ActionRow(TicketCategorySelect(bot, categories)))
        self.add_item(cont)


# ── Persistent views ──────────────────────────────────────────────────────────

class TicketOpenView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, cont=None, label: str = None, emoji: str = None, title: str = None, desc: str = None):
        super().__init__(timeout=None)
        self.bot = bot
        
        btn = discord.ui.Button(
            label=label or "Ouvrir un ticket",
            emoji=emoji or "📩",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_open_persistent"
        )
        btn.callback = self.open_ticket
        
        if cont:
            title_text = title if title else "Support et Assistance"
            desc_text = desc if desc else "Besoin d'aide ? Cliquez sur le bouton ci-dessous pour ouvrir un ticket."
            cont.add_item(discord.ui.TextDisplay(f"# {title_text}\n> {desc_text.replace(chr(10), chr(10) + '> ')}"))
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.ActionRow(btn))
            self.add_item(cont)
        else:
            self.add_item(discord.ui.ActionRow(btn))

    async def open_ticket(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        categories = [c for c in (config.get("categories") or []) if c]
        questions = config.get("questions") or {}

        if categories:
            await interaction.response.send_message(
                view=TicketCategoryView(self.bot, categories, lang),
                ephemeral=True
            )
        else:
            # No categories — check if global questions exist
            global_questions = questions.get("__global__")
            if global_questions:
                modal = TicketFormModal(self.bot, global_questions)
                await interaction.response.send_modal(modal)
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
    def __init__(self, bot: commands.Bot, cont=None, label: str = None, emoji: str = None, is_claimed: bool = False):
        super().__init__(timeout=None)
        self.bot = bot
        
        btn_close = discord.ui.Button(
            label=label or "Fermer",
            emoji=emoji or "🔒",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_close_persistent"
        )
        btn_close.callback = self.close_ticket
        
        btn_claim = discord.ui.Button(
            label="Prendre en charge",
            emoji="✋",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_claim"
        )
        btn_claim.callback = self.claim_ticket
        
        btn_unclaim = discord.ui.Button(
            label="Se retirer",
            emoji="👋",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_unclaim"
        )
        btn_unclaim.callback = self.unclaim_ticket
        
        btn_add = discord.ui.Button(
            label="Ajouter",
            emoji="➕",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_add"
        )
        btn_add.callback = self.add_member
        
        btn_remove = discord.ui.Button(
            label="Retirer",
            emoji="➖",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_remove"
        )
        btn_remove.callback = self.remove_member
        
        if cont:
            cont.add_item(discord.ui.Separator())
            claim_btn = btn_unclaim if is_claimed else btn_claim
            cont.add_item(discord.ui.ActionRow(claim_btn, btn_add, btn_remove, btn_close))
            self.add_item(cont)
        else:
            # Fallback for cog_load persistent view registration:
            # all persistent buttons registered so interactions dispatch properly
            self.add_item(discord.ui.ActionRow(btn_claim, btn_unclaim, btn_add, btn_remove, btn_close))

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
        new_view = TicketCloseView(self.bot, cont, config.get("close_button_label"), config.get("close_button_emoji"), is_claimed=False)
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
        new_view = TicketCloseView(self.bot, cont, config.get("close_button_label"), config.get("close_button_emoji"), is_claimed=True)
        if interaction.message:
            await interaction.message.edit(view=new_view)

    async def add_member(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_id = config.get("staff_role_id")
        is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))
        if not is_staff:
            return await interaction.response.send_message(embed=error_embed("Seul le staff peut ajouter des membres."), ephemeral=True)
            
        view = discord.ui.LayoutView(timeout=60)
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        cont.add_item(discord.ui.TextDisplay("### ➕ Ajouter un membre\n> Sélectionnez un membre pour lui donner accès au ticket."))
        cont.add_item(discord.ui.Separator())
        cont.add_item(discord.ui.ActionRow(TicketAddUserSelect(lang)))
        view.add_item(cont)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def remove_member(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_id = config.get("staff_role_id")
        is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))
        if not is_staff:
            return await interaction.response.send_message(embed=error_embed("Seul le staff peut retirer des membres."), ephemeral=True)
            
        view = discord.ui.LayoutView(timeout=60)
        cont = discord.ui.Container(accent_color=Colors.WARNING.value)
        cont.add_item(discord.ui.TextDisplay("### ➖ Retirer un membre\n> Sélectionnez un membre pour lui retirer l'accès au ticket."))
        cont.add_item(discord.ui.Separator())
        cont.add_item(discord.ui.ActionRow(TicketRemoveUserSelect(lang)))
        view.add_item(cont)
        await interaction.response.send_message(view=view, ephemeral=True)

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

        cont = discord.ui.Container(accent_color=Colors.ERROR.value)
        cont.add_item(discord.ui.TextDisplay(f"# 🔒 Confirmation de fermeture\n> {t(lang, 'ticket.close_confirm_prompt')}"))
        
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

        btn_confirm = discord.ui.Button(label="Fermer le ticket", emoji="🔒", style=discord.ButtonStyle.danger)
        btn_confirm.callback = self.confirm
        
        btn_cancel = discord.ui.Button(label="Annuler", emoji="✖️", style=discord.ButtonStyle.secondary)
        btn_cancel.callback = self.cancel

        if cont:
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.ActionRow(btn_confirm, btn_cancel))
            self.add_item(cont)
        else:
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
        
        # Include form responses in transcript
        form_resp_raw = self.ticket.get("form_responses")
        form_section = ""
        if form_resp_raw:
            try:
                responses = json.loads(form_resp_raw) if isinstance(form_resp_raw, str) else form_resp_raw
                if responses:
                    form_section = "── Réponses au formulaire ──\n"
                    for q, a in responses.items():
                        form_section += f"  {q}: {a}\n"
                    form_section += "\n"
            except (json.JSONDecodeError, TypeError):
                pass
        
        txt_content = header + form_section + "\n".join(lines)

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
        
        title = config.get("panel_title") or t(lang, 'ticket.panel_title')
        desc = config.get("panel_desc") or t(lang, 'ticket.panel_desc').replace('\n', ' ')
        
        t_view = TicketOpenView(view.bot, cont, config.get("open_button_label"), config.get("open_button_emoji"), title, desc)
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

class TicketFormatModal(discord.ui.Modal):
    def __init__(self, view: "TicketSetupDashboardView", current_format: str, current_welcome: str):
        super().__init__(title="Format & Bienvenue")
        self._view = view
        
        self.name_format = discord.ui.TextInput(
            label="Format du nom du salon",
            style=discord.TextStyle.short,
            required=False,
            default=current_format,
            placeholder="{category}-{number}"
        )
        self.welcome_msg = discord.ui.TextInput(
            label="Message de bienvenue dans le ticket",
            style=discord.TextStyle.long,
            required=False,
            default=current_welcome,
            placeholder="Bienvenue {mention} dans le ticket {ticket_number}!"
        )
        self.add_item(self.name_format)
        self.add_item(self.welcome_msg)

    async def on_submit(self, interaction: discord.Interaction):
        db = interaction.client.db
        gid = interaction.guild.id
        if self.name_format.value.strip():
            await db.update_ticket_config(gid, "channel_name_format", self.name_format.value.strip())
        if self.welcome_msg.value.strip():
            await db.update_ticket_config(gid, "welcome_message", self.welcome_msg.value.strip())
        await self._view.refresh(interaction)

class TicketPanelModal(discord.ui.Modal):
    def __init__(self, view: "TicketSetupDashboardView", current_title: str, current_desc: str):
        super().__init__(title="Apparence du Panel")
        self._view = view
        
        self.panel_title = discord.ui.TextInput(
            label="Titre de l'embed",
            style=discord.TextStyle.short,
            required=False,
            default=current_title,
            placeholder="Support et Assistance"
        )
        self.panel_desc = discord.ui.TextInput(
            label="Description de l'embed",
            style=discord.TextStyle.long,
            required=False,
            default=current_desc,
            placeholder="Cliquez sur le bouton pour ouvrir un ticket."
        )
        self.add_item(self.panel_title)
        self.add_item(self.panel_desc)

    async def on_submit(self, interaction: discord.Interaction):
        db = interaction.client.db
        gid = interaction.guild.id
        if self.panel_title.value.strip():
            await db.update_ticket_config(gid, "panel_title", self.panel_title.value.strip())
        if self.panel_desc.value.strip():
            await db.update_ticket_config(gid, "panel_desc", self.panel_desc.value.strip())
        await self._view.refresh(interaction)


# ── Questions Setup Modal ──────────────────────────────────────────────────────

class TicketQuestionsModal(discord.ui.Modal):
    """Modal to configure questions for a specific category or globally."""
    
    def __init__(self, view: "TicketSetupDashboardView", target_category: str, current_questions: list):
        title_label = f"Questions — {target_category}" if target_category != "__global__" else "Questions globales"
        super().__init__(title=title_label[:45])
        self._view = view
        self._target = target_category
        
        # Combine current questions into a single text block for easy editing
        current_text = ""
        if current_questions:
            lines = []
            for q in current_questions:
                label = q.get("label", "")
                placeholder = q.get("placeholder", "")
                required_str = "oui" if q.get("required", True) else "non"
                long_str = "long" if q.get("long", False) else "court"
                lines.append(f"{label} | {placeholder} | {required_str} | {long_str}")
            current_text = "\n".join(lines)
        
        self.questions_input = discord.ui.TextInput(
            label="Questions (1 par ligne, max 5)",
            style=discord.TextStyle.long,
            required=False,
            default=current_text,
            placeholder="Question | Placeholder | oui/non | court/long\nEx: Ton pseudo IG | Entrez votre pseudo | oui | court"
        )
        self.add_item(self.questions_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        db = interaction.client.db
        gid = interaction.guild.id
        
        config = await db.get_ticket_config(gid)
        all_questions = config.get("questions") or {}
        if isinstance(all_questions, str):
            try:
                all_questions = json.loads(all_questions)
            except Exception:
                all_questions = {}
        if not isinstance(all_questions, dict):
            all_questions = {}
        
        raw = self.questions_input.value.strip()
        if not raw:
            # Remove questions for this category
            all_questions.pop(self._target, None)
        else:
            parsed = []
            for line in raw.strip().split("\n")[:5]:
                parts = [p.strip() for p in line.split("|")]
                label = parts[0] if len(parts) > 0 else "Question"
                placeholder = parts[1] if len(parts) > 1 else ""
                required = parts[2].lower() != "non" if len(parts) > 2 else True
                long_format = parts[3].lower() == "long" if len(parts) > 3 else False
                parsed.append({
                    "label": label[:45],
                    "placeholder": placeholder[:100],
                    "required": required,
                    "long": long_format,
                    "max_length": 1024
                })
            all_questions[self._target] = parsed
        
        await db.update_ticket_config(gid, "questions", all_questions)
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
            
        elif val == "appearance":
            cont.add_item(discord.ui.TextDisplay("📝 **Personnalisation de l'Apparence**\n> Modifiez les textes envoyés par le bot et le format des salons."))
            
            async def open_format_modal(inter: discord.Interaction):
                config = await inter.client.db.get_ticket_config(inter.guild.id)
                fmt = config.get("channel_name_format") or "{category}-{number}"
                welc = config.get("welcome_message") or ""
                await inter.response.send_modal(TicketFormatModal(self, fmt, welc))
                
            async def open_panel_modal(inter: discord.Interaction):
                config = await inter.client.db.get_ticket_config(inter.guild.id)
                title = config.get("panel_title") or ""
                desc = config.get("panel_desc") or ""
                await inter.response.send_modal(TicketPanelModal(self, title, desc))
                
            btn_format = discord.ui.Button(label="Format & Message", style=discord.ButtonStyle.secondary, emoji="💬")
            btn_format.callback = open_format_modal
            
            btn_panel = discord.ui.Button(label="Texte du Panel", style=discord.ButtonStyle.secondary, emoji="📋")
            btn_panel.callback = open_panel_modal
            
            cont.add_item(discord.ui.ActionRow(btn_format, btn_panel))
            
        elif val == "questions":
            config = await interaction.client.db.get_ticket_config(interaction.guild.id)
            cats = config.get("categories") or []
            questions = config.get("questions") or {}
            
            cont.add_item(discord.ui.TextDisplay("📋 **Formulaires de Tickets**\n> Configurez les questions posées aux membres avant l'ouverture d'un ticket.\n> Chaque type de ticket peut avoir ses propres questions (max 5)."))
            cont.add_item(discord.ui.Separator())
            
            # Global questions button
            global_qs = questions.get("__global__", [])
            global_status = f"`{len(global_qs)} question(s)`" if global_qs else "`Aucune`"
            
            async def open_global_questions(inter: discord.Interaction):
                cfg = await inter.client.db.get_ticket_config(inter.guild.id)
                qs = (cfg.get("questions") or {}).get("__global__", [])
                await inter.response.send_modal(TicketQuestionsModal(self, "__global__", qs))
            
            btn_global = discord.ui.Button(label="Modifier", style=discord.ButtonStyle.secondary)
            btn_global.callback = open_global_questions
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay(f"🌐 **Questions globales** (sans catégorie)\n> {global_status}"),
                accessory=btn_global
            ))
            
            # Per-category questions
            for cat in cats:
                cat_name = cat["name"]
                cat_qs = questions.get(cat_name, [])
                cat_status = f"`{len(cat_qs)} question(s)`" if cat_qs else "`Aucune`"
                
                def make_cat_callback(cname):
                    async def open_cat_questions(inter: discord.Interaction):
                        cfg = await inter.client.db.get_ticket_config(inter.guild.id)
                        qs = (cfg.get("questions") or {}).get(cname, [])
                        await inter.response.send_modal(TicketQuestionsModal(self, cname, qs))
                    return open_cat_questions
                
                btn_cat_q = discord.ui.Button(label="Modifier", style=discord.ButtonStyle.secondary)
                btn_cat_q.callback = make_cat_callback(cat_name)
                cont.add_item(discord.ui.Separator())
                cont.add_item(discord.ui.Section(
                    discord.ui.TextDisplay(f"🏷️ **{cat_name}**\n> {cat_status}"),
                    accessory=btn_cat_q
                ))
            
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

        # Formulaires/Questions
        questions = config.get("questions") or {}
        total_q = sum(len(v) for v in questions.values())
        q_status = f"`{total_q} question(s)` sur `{len(questions)}` formulaire(s)" if total_q else "`Aucun formulaire`"
        btn_questions = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_questions.callback = make_nav("questions")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"📋 **Formulaires**\n> **Actuels :** {q_status}\n> Questions posées aux membres avant l'ouverture d'un ticket."), accessory=btn_questions))
        cont.add_item(discord.ui.Separator())

        # Personnalisation
        open_btn = f"{config.get('open_button_emoji') or '📩'} {config.get('open_button_label') or 'Ouvrir un ticket'}".strip()
        close_btn = f"{config.get('close_button_emoji') or '🔒'} {config.get('close_button_label') or 'Fermer le ticket'}".strip()
        btn_cust = discord.ui.Button(label="Personnaliser", style=discord.ButtonStyle.secondary)
        btn_cust.callback = make_nav("buttons")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🎨 **Personnalisation des Boutons**\n> **Ouvrir :** `{open_btn}` | **Fermer :** `{close_btn}`"), accessory=btn_cust))
        cont.add_item(discord.ui.Separator())

        # Apparence
        btn_app = discord.ui.Button(label="Personnaliser les textes", style=discord.ButtonStyle.secondary)
        btn_app.callback = make_nav("appearance")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"📝 **Apparence (Textes & Noms)**\n> Titre du Panel, message de bienvenue, format des salons, etc."), accessory=btn_app))
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

    @ticket_group.command(name="close", description="Ferme et archive le ticket actuel")
    async def ticket_close(self, interaction: discord.Interaction):
        view = TicketCloseView(self.bot)
        await view.close_ticket(interaction)

    @ticket_group.command(name="claim", description="Prend en charge le ticket actuel")
    async def ticket_claim(self, interaction: discord.Interaction):
        view = TicketCloseView(self.bot)
        await view.claim_ticket(interaction)

    @ticket_group.command(name="unclaim", description="Se retire de la prise en charge du ticket actuel")
    async def ticket_unclaim(self, interaction: discord.Interaction):
        view = TicketCloseView(self.bot)
        await view.unclaim_ticket(interaction)

    @ticket_group.command(name="add", description="Ajoute un membre au ticket actuel")
    @app_commands.describe(membre="Membre à ajouter au ticket")
    async def ticket_cmd_add(self, interaction: discord.Interaction, membre: discord.Member):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_id = config.get("staff_role_id")
        is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))
        if not is_staff:
            return await interaction.response.send_message(embed=error_embed("Seul le staff peut ajouter des membres."), ephemeral=True)
        if not await self.bot.db.get_ticket(interaction.channel.id):
            return await interaction.response.send_message(embed=error_embed(t(lang, "ticket.not_a_ticket")), ephemeral=True)
        await interaction.channel.set_permissions(
            membre, view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True
        )
        embed = discord.Embed(description=t(lang, "ticket.member_added", member=membre.mention), color=Colors.SUCCESS)
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="remove", description="Retire un membre du ticket actuel")
    @app_commands.describe(membre="Membre à retirer du ticket")
    async def ticket_cmd_remove(self, interaction: discord.Interaction, membre: discord.Member):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_id = config.get("staff_role_id")
        is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))
        if not is_staff:
            return await interaction.response.send_message(embed=error_embed("Seul le staff peut retirer des membres."), ephemeral=True)
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))

