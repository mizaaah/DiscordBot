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


# ══════════════════════════════════════════════════════════════════════════════
#  Helper: Build the inside-ticket embed & controls
# ══════════════════════════════════════════════════════════════════════════════

async def build_ticket_embed(bot: commands.Bot, guild: discord.Guild, channel_id: int, lang: str):
    ticket = await bot.db.get_ticket(channel_id)
    if not ticket:
        return None, None

    config = await bot.db.get_ticket_config(guild.id)
    user_id = ticket["user_id"]
    user = guild.get_member(user_id)
    user_mention = user.mention if user else f"<@{user_id}>"
    user_avatar = user.display_avatar.url if user else None

    category = ticket.get("category") or "Général"
    ticket_num = ticket.get("ticket_number", 1)
    claimed_by = ticket.get("claimed_by")
    claimed_user = guild.get_member(claimed_by) if claimed_by else None

    color = discord.Color(config.get("embed_color") or Colors.INFO.value)

    # Welcome message template (fully customizable by the user)
    template = config.get("welcome_message")
    if not template:
        welcome = f"Bonjour {user_mention} !\nMerci d'avoir ouvert ce ticket auprès du support de **{guild.name}**.\nUn membre de notre équipe va prendre en charge ta demande très rapidement."
    else:
        user_name = user.display_name if user else "Membre"
        welcome = (
            template
            .replace("{mention}", user_mention)
            .replace("{name}", user_name)
            .replace("{user}", user_name)
            .replace("{ticket_number}", f"{ticket_num:04d}")
            .replace("{category}", category)
            .replace("{server}", guild.name)
        )

    embed = discord.Embed(
        title=f"🎫 Ticket #{ticket_num:04d} ➔ {category}",
        description=f"{welcome}\n",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

    if user_avatar:
        embed.set_thumbnail(url=user_avatar)

    # Banner inside the ticket if configured
    welcome_banner = config.get("welcome_banner")
    if welcome_banner:
        embed.set_image(url=welcome_banner)

    # Instructions / guide inside the ticket (customizable)
    guide = config.get("ticket_guide")
    if not guide:
        guide = (
            "1. Expliquez clairement et en détail la raison de votre demande.\n"
            "2. Joignez des captures d'écran ou des preuves si nécessaire.\n"
            "3. Veuillez patienter sans mentionner inutilement le staff."
        )
    embed.add_field(name="📋 Consignes & Démarche", value=f"```{guide}```", inline=False)

    staff_id = config.get("staff_role_id")
    staff_role = guild.get_role(staff_id) if staff_id else None
    staff_str = staff_role.mention if staff_role else "*Non défini*"

    status_str = f"✋ Pris en charge par {claimed_user.mention}" if claimed_user else "🟢 En attente d'un modérateur"

    embed.add_field(name="👤 Demandeur", value=f"{user_mention}\n`{user_id}`", inline=True)
    embed.add_field(name="🛡️ Équipe Support", value=staff_str, inline=True)
    embed.add_field(name="📌 Statut", value=status_str, inline=True)

    # Form responses
    form_raw = ticket.get("form_responses")
    if form_raw:
        try:
            responses = json.loads(form_raw) if isinstance(form_raw, str) else form_raw
            if responses and isinstance(responses, dict):
                resp_lines = []
                for q, a in responses.items():
                    resp_lines.append(f"❓ **{q}**\n```{a[:500]}```")
                embed.add_field(name="📋 Réponses au formulaire", value="\n".join(resp_lines)[:1024], inline=False)
        except Exception:
            pass

    embed.set_footer(text=f"Support • {guild.name}")
    return embed, bool(claimed_by)


# ══════════════════════════════════════════════════════════════════════════════
#  Ticket Creation Engine
# ══════════════════════════════════════════════════════════════════════════════

async def _open_ticket(bot: commands.Bot, interaction: discord.Interaction, category: str = None, form_responses: dict = None):
    guild = interaction.guild
    user = interaction.user
    lang = await bot.db.get_guild_lang(guild.id)

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    # Check for existing open ticket for this user in same category
    existing = await bot.db.get_user_open_ticket(guild.id, user.id, category)
    if existing:
        ch = guild.get_channel(existing["channel_id"])
        if ch:
            return await interaction.followup.send(
                embed=error_embed(f"❌ Tu as déjà un ticket ouvert dans {ch.mention}."),
                ephemeral=True
            )

    config = await bot.db.get_ticket_config(guild.id)
    if not config.get("staff_role_id"):
        return await interaction.followup.send(
            embed=error_embed("❌ Le système de tickets n'est pas encore configuré (rôle staff support manquant)."),
            ephemeral=True
        )

    # Determine category channel
    ticket_cat = None
    if category:
        cats = config.get("categories") or []
        for c in cats:
            if isinstance(c, dict) and c.get("name") == category and c.get("category_id"):
                ticket_cat = guild.get_channel(c["category_id"])
                break

    if not ticket_cat and config.get("category_id"):
        ticket_cat = guild.get_channel(config["category_id"])

    staff_role = guild.get_role(config["staff_role_id"]) if config.get("staff_role_id") else None
    ticket_num = await bot.db.increment_ticket_counter(guild.id)

    # Channel naming
    cat_clean = category.lower().replace(" ", "-") if category else "ticket"
    name_format = config.get("channel_name_format") or "{category}-{number}"
    channel_name = (
        name_format
        .replace("{category}", cat_clean)
        .replace("{number}", f"{ticket_num:04d}")
        .replace("{user}", user.name[:15].lower().replace(" ", "-"))
        .lower()
    )[:100]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            attach_files=True, embed_links=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True,
            manage_messages=True, read_message_history=True, embed_links=True,
            attach_files=True
        ),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            manage_messages=True, attach_files=True, embed_links=True
        )

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            category=ticket_cat,
            overwrites=overwrites,
            reason=f"Ticket #{ticket_num:04d} ouvert par {user}"
        )
    except discord.Forbidden:
        return await interaction.followup.send(
            embed=error_embed("❌ Je n'ai pas la permission de créer le salon de ticket. Vérifiez mes permissions Discord."),
            ephemeral=True
        )

    # Save to database
    await bot.db.create_ticket(guild.id, channel.id, user.id, ticket_num, category, form_responses)

    # Build and send control view inside the ticket
    embed, is_claimed = await build_ticket_embed(bot, guild, channel.id, lang)
    view = TicketControlView(bot, is_claimed=is_claimed)
    await channel.send(content=f"{user.mention} {staff_role.mention if staff_role else ''}", embed=embed, view=view)

    # Inform the user with direct link
    await interaction.followup.send(
        embed=success_embed(f"✅ Ton ticket a été créé avec succès dans {channel.mention} !"),
        ephemeral=True
    )

    # Log ticket opening
    if logs := bot.get_cog("Logs"):
        log_embed = discord.Embed(
            title="🎫 Ticket Ouvert",
            description=f"Le ticket **#{ticket_num:04d}** vient d'être créé.",
            color=Colors.SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="👤 Demandeur", value=f"{user.mention} (`{user.id}`)", inline=True)
        log_embed.add_field(name="📍 Salon", value=f"{channel.mention}", inline=True)
        log_embed.add_field(name="🏷️ Catégorie", value=f"`{category or 'Général'}`", inline=True)
        log_embed.set_thumbnail(url=user.display_avatar.url)
        log_embed.set_footer(text=f"Ticket #{ticket_num:04d} • Système de Logs")
        await logs.send_log(guild, log_embed, log_type="mod")


# ══════════════════════════════════════════════════════════════════════════════
#  Ticket Form Modal (Questions)
# ══════════════════════════════════════════════════════════════════════════════

class TicketFormModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot, questions: list[dict], category: str = None):
        super().__init__(title=f"📋 Questionnaire — {category[:25]}" if category else "📋 Formulaire de Ticket")
        self.bot = bot
        self.category = category
        self.inputs = []

        for q in questions[:5]:
            t_input = discord.ui.TextInput(
                label=q.get("label", "Question")[:45],
                placeholder=q.get("placeholder", "")[:100],
                style=discord.TextStyle.long if q.get("long", False) else discord.TextStyle.short,
                required=q.get("required", True),
                max_length=1000,
            )
            self.add_item(t_input)
            self.inputs.append((q.get("label", "Question"), t_input))

    async def on_submit(self, interaction: discord.Interaction):
        responses = {label: inp.value.strip() for label, inp in self.inputs if inp.value.strip()}
        await _open_ticket(self.bot, interaction, self.category, form_responses=responses)


# ══════════════════════════════════════════════════════════════════════════════
#  Ticket Open Panel View (Persistent)
# ══════════════════════════════════════════════════════════════════════════════

class TicketCategorySelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, categories: list):
        self.bot = bot
        options = []
        for c in categories[:25]:
            name = c["name"] if isinstance(c, dict) else str(c)
            emoji = "🎫"
            desc = "Ouvrir une demande dans cette section"
            nl = name.lower()
            if "aide" in nl or "support" in nl:
                emoji = "❓"
                desc = "Assistance générale, questions & aide"
            elif "plainte" in nl or "signal" in nl or "report" in nl:
                emoji = "🛡️"
                desc = "Signaler un abus ou comportement suspect"
            elif "partenariat" in nl:
                emoji = "🤝"
                desc = "Propositions de partenariats & alliances"
            elif "recrutement" in nl or "staff" in nl:
                emoji = "💼"
                desc = "Candidatures & rejoindre l'équipe"
            elif "vip" in nl or "boost" in nl or "grade" in nl:
                emoji = "💎"
                desc = "Questions sur les rôles VIP & avantages"

            options.append(discord.SelectOption(label=name[:100], value=name[:100], emoji=emoji, description=desc[:100]))

        super().__init__(
            placeholder="⚡ Choisis la catégorie de ton ticket...",
            options=options,
            custom_id="ticket_category_select_menu",
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        questions = config.get("questions") or {}
        if isinstance(questions, str):
            try:
                questions = json.loads(questions)
            except Exception:
                questions = {}

        cat_questions = questions.get(category)
        if cat_questions:
            await interaction.response.send_modal(TicketFormModal(self.bot, cat_questions, category))
        else:
            await _open_ticket(self.bot, interaction, category)


class TicketOpenView(discord.ui.View):
    def __init__(self, bot: commands.Bot, categories: list = None):
        super().__init__(timeout=None)
        self.bot = bot
        cats = [c for c in (categories or []) if c]
        if cats:
            self.add_item(TicketCategorySelect(bot, cats))

    @discord.ui.button(
        label="Ouvrir un ticket",
        emoji="📩",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_open_btn_persistent",
        row=1
    )
    async def open_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        cats = [c for c in (config.get("categories") or []) if c]
        questions = config.get("questions") or {}
        if isinstance(questions, str):
            try:
                questions = json.loads(questions)
            except Exception:
                questions = {}

        if cats:
            view = discord.ui.View(timeout=60)
            view.add_item(TicketCategorySelect(self.bot, cats))
            await interaction.response.send_message(
                "👇 **Choisis la catégorie de ton ticket dans le menu déroulant :**",
                view=view,
                ephemeral=True
            )
        else:
            global_qs = questions.get("__global__")
            if global_qs:
                await interaction.response.send_modal(TicketFormModal(self.bot, global_qs))
            else:
                await _open_ticket(self.bot, interaction)


# ══════════════════════════════════════════════════════════════════════════════
#  Inside Ticket Control View (Persistent)
# ══════════════════════════════════════════════════════════════════════════════

class TicketControlView(discord.ui.View):
    def __init__(self, bot: commands.Bot, is_claimed: bool = False):
        super().__init__(timeout=None)
        self.bot = bot

        # Update claim button label dynamically
        if is_claimed:
            self.btn_claim.label = "Se désister"
            self.btn_claim.emoji = "👋"
            self.btn_claim.style = discord.ButtonStyle.secondary
        else:
            self.btn_claim.label = "Prendre en charge"
            self.btn_claim.emoji = "✋"
            self.btn_claim.style = discord.ButtonStyle.primary

    @discord.ui.button(
        label="Prendre en charge",
        emoji="✋",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_claim_btn",
        row=0
    )
    async def btn_claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_ticket_claim(self.bot, interaction)

    @discord.ui.button(
        label="Fermer le ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close_btn",
        row=0
    )
    async def btn_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_ticket_close_prompt(self.bot, interaction)

    @discord.ui.button(
        label="Transcription",
        emoji="📄",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_transcript_btn",
        row=0
    )
    async def btn_transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_ticket_transcript(self.bot, interaction)

    @discord.ui.button(
        label="Gérer membres",
        emoji="👥",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_members_btn",
        row=0
    )
    async def btn_members(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_ticket_members_prompt(self.bot, interaction)


# ══════════════════════════════════════════════════════════════════════════════
#  Direct Actions Handlers (Shared by persistent buttons and on_interaction)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_ticket_claim(bot: commands.Bot, interaction: discord.Interaction):
    ticket = await bot.db.get_ticket(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message(embed=error_embed("❌ Ce salon n'est pas un ticket actif."), ephemeral=True)

    config = await bot.db.get_ticket_config(interaction.guild.id)
    staff_id = config.get("staff_role_id")
    is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))

    if not is_staff:
        return await interaction.response.send_message(embed=error_embed("❌ Seuls les membres du staff peuvent prendre en charge un ticket."), ephemeral=True)

    claimed_by = ticket.get("claimed_by")

    if claimed_by == interaction.user.id:
        # Unclaim
        await bot.db.unclaim_ticket(interaction.channel.id)
        embed, _ = await build_ticket_embed(bot, interaction.guild, interaction.channel.id, "fr")
        new_view = TicketControlView(bot, is_claimed=False)
        if interaction.message:
            await interaction.message.edit(embed=embed, view=new_view)
        await interaction.response.send_message("👋 Tu t'es retiré de la prise en charge de ce ticket.")
    elif claimed_by:
        claimer = interaction.guild.get_member(claimed_by)
        claimer_str = claimer.mention if claimer else f"<@{claimed_by}>"
        return await interaction.response.send_message(
            embed=error_embed(f"❌ Ce ticket est déjà pris en charge par {claimer_str}."),
            ephemeral=True
        )
    else:
        # Claim
        await bot.db.claim_ticket(interaction.channel.id, interaction.user.id)
        embed, _ = await build_ticket_embed(bot, interaction.guild, interaction.channel.id, "fr")
        new_view = TicketControlView(bot, is_claimed=True)
        if interaction.message:
            await interaction.message.edit(embed=embed, view=new_view)
        await interaction.response.send_message(f"✋ {interaction.user.mention} a pris en charge ce ticket !")


async def handle_ticket_transcript(bot: commands.Bot, interaction: discord.Interaction):
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    ticket = await bot.db.get_ticket(interaction.channel.id)
    if not ticket:
        return await interaction.followup.send(embed=error_embed("❌ Ce salon n'est pas un ticket actif."), ephemeral=True)

    txt_file = await create_transcript_file(interaction.channel, ticket, interaction.guild)
    await interaction.followup.send(
        content="📄 **Voici la transcription en direct de ce ticket :**",
        file=txt_file,
        ephemeral=True
    )


async def handle_ticket_members_prompt(bot: commands.Bot, interaction: discord.Interaction):
    ticket = await bot.db.get_ticket(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message(embed=error_embed("❌ Ce salon n'est pas un ticket actif."), ephemeral=True)

    config = await bot.db.get_ticket_config(interaction.guild.id)
    staff_id = config.get("staff_role_id")
    is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))

    if not is_staff and ticket["user_id"] != interaction.user.id:
        return await interaction.response.send_message(embed=error_embed("❌ Vous n'avez pas la permission de gérer les membres de ce ticket."), ephemeral=True)

    view = TicketMemberManagerView(bot)
    await interaction.response.send_message(
        "👥 **Gestion des membres du ticket**\nChoisissez ci-dessous d'ajouter ou de retirer un utilisateur :",
        view=view,
        ephemeral=True
    )


async def handle_ticket_close_prompt(bot: commands.Bot, interaction: discord.Interaction):
    ticket = await bot.db.get_ticket(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message(embed=error_embed("❌ Ce salon n'est pas un ticket actif."), ephemeral=True)

    config = await bot.db.get_ticket_config(interaction.guild.id)
    staff_id = config.get("staff_role_id")
    is_owner = ticket["user_id"] == interaction.user.id
    is_staff = interaction.user.guild_permissions.manage_channels or (staff_id and any(r.id == staff_id for r in interaction.user.roles))

    if not (is_owner or is_staff):
        return await interaction.response.send_message(embed=error_embed("❌ Seul le créateur du ticket ou le staff peut le fermer."), ephemeral=True)

    view = TicketCloseConfirmView(bot, ticket)
    await interaction.response.send_message(
        "⚠️ **Êtes-vous sûr de vouloir fermer et archiver ce ticket ?**\nUne transcription complète sera générée et envoyée en MP au créateur.",
        view=view,
        ephemeral=True
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Transcript Generator & Close Logic
# ══════════════════════════════════════════════════════════════════════════════

async def create_transcript_file(channel: discord.TextChannel, ticket: dict, guild: discord.Guild) -> discord.File:
    lines = []
    async for msg in channel.history(limit=1000, oldest_first=True):
        ts = msg.created_at.strftime("%d/%m/%Y %H:%M:%S")
        author = str(msg.author)
        content = msg.content or ""
        if msg.attachments:
            att_urls = " ".join(f"[{a.filename}: {a.url}]" for a in msg.attachments)
            content = f"{content} {att_urls}".strip()
        lines.append(f"[{ts}] {author}: {content}")

    open_user = guild.get_member(ticket["user_id"])
    open_user_str = f"{open_user} ({open_user.id})" if open_user else str(ticket["user_id"])

    sep = "═" * 65
    header = [
        sep,
        f"  TRANSCRIPTION OFFICIELLE DU TICKET #{ticket.get('ticket_number', 0):04d}",
        f"  Serveur     : {guild.name} ({guild.id})",
        f"  Catégorie   : {ticket.get('category') or 'Général'}",
        f"  Demandeur   : {open_user_str}",
        f"  Salon       : #{channel.name}",
        f"  Généré le   : {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S')} UTC",
        sep,
        ""
    ]

    # Include form responses
    form_raw = ticket.get("form_responses")
    if form_raw:
        try:
            resp = json.loads(form_raw) if isinstance(form_raw, str) else form_raw
            if resp and isinstance(resp, dict):
                header.append("── FORMULAIRE INITIAL ──")
                for q, a in resp.items():
                    header.append(f"Q: {q}\nR: {a}\n")
                header.append("────────────────────────\n")
        except Exception:
            pass

    full_text = "\n".join(header + lines)
    return discord.File(
        io.BytesIO(full_text.encode("utf-8")),
        filename=f"transcript-ticket-{ticket.get('ticket_number', 0):04d}.txt"
    )


class TicketCloseConfirmView(discord.ui.View):
    def __init__(self, bot: commands.Bot, ticket: dict):
        super().__init__(timeout=60)
        self.bot = bot
        self.ticket = ticket

    @discord.ui.button(label="Confirmer la fermeture", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_confirm_close_btn")
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="⏳ **Fermeture et archivage en cours...**", view=self)

        channel = interaction.channel
        guild = interaction.guild

        # Calculate duration
        close_time = datetime.now(timezone.utc)
        duration_str = "Inconnue"
        open_time_str = self.ticket.get("created_at")
        if open_time_str:
            try:
                open_time = datetime.fromisoformat(open_time_str)
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=timezone.utc)
                mins = int((close_time - open_time).total_seconds() // 60)
                duration_str = f"{mins // 60}h {mins % 60}min" if mins >= 60 else f"{mins} min"
            except Exception:
                pass

        # Generate transcript file
        transcript_file = await create_transcript_file(channel, self.ticket, guild)

        # 1. Send recap and transcript to creator in DM
        creator = guild.get_member(self.ticket["user_id"])
        if creator and not creator.bot:
            try:
                dm_embed = discord.Embed(
                    title=f"🎫 Ticket #{self.ticket.get('ticket_number', 0):04d} Fermé",
                    description=(
                        f"Ton ticket sur **{guild.name}** a été fermé.\n\n"
                        f"🏷️ **Catégorie :** `{self.ticket.get('category') or 'Général'}`\n"
                        f"⏱️ **Durée :** `{duration_str}`\n"
                        f"🛡️ **Fermé par :** {interaction.user.mention}\n\n"
                        f"> *Tu trouveras en pièce jointe la transcription complète des échanges.*"
                    ),
                    color=Colors.INFO,
                    timestamp=close_time
                )
                if guild.icon:
                    dm_embed.set_thumbnail(url=guild.icon.url)
                dm_file = await create_transcript_file(channel, self.ticket, guild)
                await creator.send(embed=dm_embed, file=dm_file)
            except discord.HTTPException:
                pass

        # 2. Send transcript to staff log channel
        config = await self.bot.db.get_ticket_config(guild.id)
        log_ch_id = config.get("log_channel_id")
        if not log_ch_id:
            settings = await self.bot.db.get_guild_settings(guild.id)
            log_ch_id = settings.get("log_mod_id") or settings.get("log_channel_id")

        if log_ch_id:
            log_ch = guild.get_channel(log_ch_id)
            if log_ch and log_ch.permissions_for(guild.me).send_messages:
                log_embed = discord.Embed(
                    title=f"📁 Ticket #{self.ticket.get('ticket_number', 0):04d} Archivé",
                    color=Colors.ERROR,
                    timestamp=close_time
                )
                log_embed.add_field(name="👤 Demandeur", value=creator.mention if creator else str(self.ticket["user_id"]), inline=True)
                log_embed.add_field(name="🛡️ Fermé par", value=interaction.user.mention, inline=True)
                log_embed.add_field(name="⏱️ Durée", value=f"`{duration_str}`", inline=True)
                if self.ticket.get("category"):
                    log_embed.add_field(name="🏷️ Catégorie", value=f"`{self.ticket['category']}`", inline=True)
                if self.ticket.get("claimed_by"):
                    claimer = guild.get_member(self.ticket["claimed_by"])
                    log_embed.add_field(name="✋ Support", value=claimer.mention if claimer else str(self.ticket["claimed_by"]), inline=True)
                try:
                    await log_ch.send(embed=log_embed, file=transcript_file)
                except discord.HTTPException:
                    pass

        # Update DB status
        await self.bot.db.close_ticket(channel.id, interaction.user.id)

        # Notify channel of deletion countdown
        try:
            delete_embed = discord.Embed(
                title="🔒 Ticket Fermé",
                description="Le ticket a été clôturé et archivé.\nCe salon sera supprimé automatiquement dans **5 secondes**...",
                color=Colors.ERROR
            )
            await channel.send(embed=delete_embed)
        except discord.HTTPException:
            pass

        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket fermé par {interaction.user}")
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Annuler", emoji="✖️", style=discord.ButtonStyle.secondary, custom_id="ticket_cancel_close_btn")
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ **Fermeture du ticket annulée.**", view=self)


# ══════════════════════════════════════════════════════════════════════════════
#  Member Management (Add / Remove)
# ══════════════════════════════════════════════════════════════════════════════

class TicketMemberManagerView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=60)
        self.bot = bot

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="➕ Sélectionner un membre à ajouter au ticket...", row=0)
    async def add_user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        member = select.values[0]
        await interaction.channel.set_permissions(
            member, view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True, embed_links=True
        )
        await interaction.response.send_message(f"✅ {member.mention} a été ajouté au ticket avec succès !")

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="➖ Sélectionner un membre à retirer du ticket...", row=1)
    async def remove_user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        member = select.values[0]
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if ticket and ticket["user_id"] == member.id:
            return await interaction.response.send_message("❌ Tu ne peux pas retirer le créateur du ticket !", ephemeral=True)

        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"✅ {member.mention} a été retiré du ticket.")


# ══════════════════════════════════════════════════════════════════════════════
#  Modals for Setup
# ══════════════════════════════════════════════════════════════════════════════

class TicketBannerModal(discord.ui.Modal):
    def __init__(self, dashboard: "TicketSetupDashboardView", current_panel: str, current_welcome: str):
        super().__init__(title="🖼️ Bannières du Système de Tickets")
        self.dashboard = dashboard

        self.panel_banner = discord.ui.TextInput(
            label="Bannière du Panel (Image ou GIF URL)",
            placeholder="https://example.com/banner.gif",
            default=current_panel or "",
            required=False,
            max_length=500
        )
        self.welcome_banner = discord.ui.TextInput(
            label="Bannière dans le Ticket (Image ou GIF URL)",
            placeholder="https://example.com/welcome-ticket.png",
            default=current_welcome or "",
            required=False,
            max_length=500
        )
        self.add_item(self.panel_banner)
        self.add_item(self.welcome_banner)

    async def on_submit(self, interaction: discord.Interaction):
        db = interaction.client.db
        gid = interaction.guild.id
        await db.update_ticket_config(gid, "panel_banner", self.panel_banner.value.strip() or None)
        await db.update_ticket_config(gid, "welcome_banner", self.welcome_banner.value.strip() or None)
        await self.dashboard.refresh(interaction)


class TicketPanelTextModal(discord.ui.Modal):
    def __init__(self, dashboard: "TicketSetupDashboardView", current_title: str, current_desc: str, current_btn: str):
        super().__init__(title="💬 Textes du Panneau Public")
        self.dashboard = dashboard

        self.title_input = discord.ui.TextInput(
            label="Titre du Panel",
            placeholder="Support & Assistance",
            default=current_title or "Support & Assistance",
            required=False,
            max_length=100
        )
        self.desc_input = discord.ui.TextInput(
            label="Description du Panel",
            style=discord.TextStyle.long,
            placeholder="Choisis une catégorie ci-dessous pour ouvrir un ticket avec notre équipe.",
            default=current_desc or "Besoin d'aide ? Choisis une catégorie dans le menu ci-dessous pour ouvrir un ticket.",
            required=False,
            max_length=1000
        )
        self.btn_input = discord.ui.TextInput(
            label="Texte du Bouton d'ouverture",
            placeholder="Ouvrir un ticket",
            default=current_btn or "Ouvrir un ticket",
            required=False,
            max_length=50
        )
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.btn_input)

    async def on_submit(self, interaction: discord.Interaction):
        db = interaction.client.db
        gid = interaction.guild.id
        await db.update_ticket_config(gid, "panel_title", self.title_input.value.strip() or None)
        await db.update_ticket_config(gid, "panel_desc", self.desc_input.value.strip() or None)
        await db.update_ticket_config(gid, "open_button_label", self.btn_input.value.strip() or "Ouvrir un ticket")
        await self.dashboard.refresh(interaction)


class TicketInsideTextModal(discord.ui.Modal):
    def __init__(self, dashboard: "TicketSetupDashboardView", current_welcome: str, current_guide: str):
        super().__init__(title="🎟️ Textes à l'Intérieur du Ticket")
        self.dashboard = dashboard

        self.welcome_input = discord.ui.TextInput(
            label="Message d'accueil dans le ticket",
            style=discord.TextStyle.long,
            placeholder="Variables: {mention}, {name}, {server}, {category}, {ticket_number}",
            default=current_welcome or "Bonjour {mention} !\nMerci d'avoir contacté le support de **{server}**.\nUn membre de l'équipe va te répondre sous peu.",
            required=False,
            max_length=1000
        )
        self.guide_input = discord.ui.TextInput(
            label="Consignes / Démarche dans le ticket",
            style=discord.TextStyle.long,
            placeholder="1. Expliquez votre problème\n2. Fournissez des preuves\n3. Patientez",
            default=current_guide or "1. Expliquez clairement votre demande.\n2. Joignez des captures d'écran si nécessaire.\n3. Patientez jusqu'à la réponse d'un modérateur.",
            required=False,
            max_length=1000
        )
        self.add_item(self.welcome_input)
        self.add_item(self.guide_input)

    async def on_submit(self, interaction: discord.Interaction):
        db = interaction.client.db
        gid = interaction.guild.id
        await db.update_ticket_config(gid, "welcome_message", self.welcome_input.value.strip() or None)
        await db.update_ticket_config(gid, "ticket_guide", self.guide_input.value.strip() or None)
        await self.dashboard.refresh(interaction)


class TicketCategoriesModal(discord.ui.Modal):
    def __init__(self, dashboard: "TicketSetupDashboardView", current_cats: str):
        super().__init__(title="🏷️ Catégories de Tickets")
        self.dashboard = dashboard

        self.cats_input = discord.ui.TextInput(
            label="Catégories (séparées par une virgule)",
            style=discord.TextStyle.long,
            placeholder="Ex: Support Général, Plainte, Partenariats, Recrutement Staff",
            default=current_cats or "Support Général, Plainte, Partenariats",
            required=False,
            max_length=500
        )
        self.add_item(self.cats_input)

    async def on_submit(self, interaction: discord.Interaction):
        db = interaction.client.db
        gid = interaction.guild.id
        raw = self.cats_input.value.strip()
        names = [n.strip() for n in raw.split(",") if n.strip()][:15]

        old_config = await db.get_ticket_config(gid)
        old_cats = old_config.get("categories") or []

        new_cats = []
        for name in names:
            cat_id = None
            for old in old_cats:
                if isinstance(old, dict) and old.get("name") == name:
                    cat_id = old.get("category_id")
            new_cats.append({"name": name, "category_id": cat_id})

        await db.update_ticket_config(gid, "categories", new_cats)
        await self.dashboard.refresh(interaction)


# ══════════════════════════════════════════════════════════════════════════════
#  Setup Dashboard (Components V2 LayoutView)
# ══════════════════════════════════════════════════════════════════════════════

class TicketSetupRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="👮 Sélectionner le rôle Staff Support...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        await interaction.client.db.update_ticket_config(interaction.guild.id, "staff_role_id", role.id)
        view: "TicketSetupDashboardView" = self.view
        await view.refresh(interaction)


class TicketSetupCategorySelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📁 Sélectionner la catégorie Discord d'accueil...", channel_types=[discord.ChannelType.category])

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        await interaction.client.db.update_ticket_config(interaction.guild.id, "category_id", cat.id)
        view: "TicketSetupDashboardView" = self.view
        await view.refresh(interaction)


class TicketSetupLogSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="🪵 Sélectionner le salon des transcriptions (logs)...", channel_types=[discord.ChannelType.text])

    async def callback(self, interaction: discord.Interaction):
        ch = self.values[0]
        await interaction.client.db.update_ticket_config(interaction.guild.id, "log_channel_id", ch.id)
        view: "TicketSetupDashboardView" = self.view
        await view.refresh(interaction)


class TicketDeploySelect(discord.ui.ChannelSelect):
    def __init__(self, dashboard: "TicketSetupDashboardView"):
        super().__init__(placeholder="🚀 Sélectionner le salon où poster le Panel...", channel_types=[discord.ChannelType.text])
        self.dashboard = dashboard

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.values[0].id)
        if not channel:
            return await interaction.response.send_message("❌ Salon introuvable.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        db = interaction.client.db
        config = await db.get_ticket_config(interaction.guild.id)

        title = config.get("panel_title") or f"Centre de Support • {interaction.guild.name}"
        desc = config.get("panel_desc") or "Besoin d'aide ? Choisis une catégorie dans le menu déroulant ci-dessous pour ouvrir un ticket privé avec notre équipe."
        color = discord.Color(config.get("embed_color") or Colors.INFO.value)

        cats = [c for c in (config.get("categories") or []) if c]
        if not cats:
            # Default rich categories if none set
            cats = [
                {"name": "Support Général"},
                {"name": "Plainte & Signalement"},
                {"name": "Partenariats"}
            ]

        # Build clean panel embed
        embed = discord.Embed(
            title=f"🎫 {title}",
            description=f"{desc}\n",
            color=color
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        panel_banner = config.get("panel_banner")
        if panel_banner:
            embed.set_image(url=panel_banner)

        cats_list = []
        for c in cats[:10]:
            name = c["name"] if isinstance(c, dict) else str(c)
            cats_list.append(f"➔ `{name}`")
        embed.add_field(name="📂 Types de Demandes Prises en Charge", value="\n".join(cats_list), inline=False)

        embed.set_footer(text=f"Support • {interaction.guild.name}")

        panel_view = TicketOpenView(self.dashboard.bot, cats)
        msg = await channel.send(embed=embed, view=panel_view)

        await db.update_ticket_config(interaction.guild.id, "panel_message_id", msg.id)
        await db.update_ticket_config(interaction.guild.id, "panel_channel_id", channel.id)

        await interaction.followup.send(
            embed=success_embed(f"🎉 Le panneau de tickets a été déployé avec succès dans {channel.mention} !"),
            ephemeral=True
        )


class TicketSetupDashboardView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, lang: str, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.lang = lang
        self.guild_id = guild_id

    async def build(self, guild: discord.Guild):
        self.clear_items()
        config = await self.bot.db.get_ticket_config(self.guild_id)

        def ch(cid):
            if not cid: return "*Non configuré*"
            c = guild.get_channel(cid)
            return c.mention if c else "*Introuvable*"

        def role(rid):
            if not rid: return "*Non configuré*"
            r = guild.get_role(rid)
            return r.mention if r else "*Introuvable*"

        staff_str = role(config.get("staff_role_id"))
        cat_str = ch(config.get("category_id"))
        log_str = ch(config.get("log_channel_id"))

        panel_b = "✅ Définie" if config.get("panel_banner") else "❌ Aucune (par défaut)"
        welcome_b = "✅ Définie" if config.get("welcome_banner") else "❌ Aucune (par défaut)"
        welc_msg_stat = "✅ Personnalisé" if config.get("welcome_message") else "Par défaut"
        guide_stat = "✅ Personnalisées" if config.get("ticket_guide") else "Par défaut"

        cats = [c for c in (config.get("categories") or []) if c]
        if cats:
            cats_str = ", ".join(f"`{c['name'] if isinstance(c, dict) else c}`" for c in cats)
        else:
            cats_str = "*Par défaut (Support, Plainte, Partenariat)*"

        cont = discord.ui.Container(accent_color=Colors.PRIMARY.value)
        cont.add_item(discord.ui.TextDisplay(
            f"# 🎫 Configuration Avancée des Tickets • {guild.name}\n"
            f"> Personnalisez l'intégralité des bannières, des textes et du fonctionnement de vos tickets.\n"
        ))
        cont.add_item(discord.ui.Separator())

        overview_text = (
            f"### 📊 État Global de la Configuration\n"
            f"> 👮 **Rôle Support Staff :** {staff_str}\n"
            f"> 📁 **Dossier Discord :** {cat_str}\n"
            f"> 🪵 **Salon Transcriptions :** {log_str}\n"
            f"> 🖼️ **Bannière Panel :** `{panel_b}`\n"
            f"> 🖼️ **Bannière dans le Ticket :** `{welcome_b}`\n"
            f"> 💬 **Message de bienvenue :** `{welc_msg_stat}`\n"
            f"> 📋 **Consignes dans le ticket :** `{guide_stat}`\n"
            f"> 🏷️ **Catégories actives :** {cats_str}\n"
        )
        cont.add_item(discord.ui.TextDisplay(overview_text))
        cont.add_item(discord.ui.Separator())

        # Buttons for quick config
        btn_banners = discord.ui.Button(label="Bannières Image/GIF", emoji="🖼️", style=discord.ButtonStyle.secondary)
        async def on_banners(i: discord.Interaction):
            cfg = await self.bot.db.get_ticket_config(self.guild_id)
            await i.response.send_modal(TicketBannerModal(self, cfg.get("panel_banner"), cfg.get("welcome_banner")))
        btn_banners.callback = on_banners

        btn_panel_texts = discord.ui.Button(label="Textes du Panel", emoji="💬", style=discord.ButtonStyle.secondary)
        async def on_panel_texts(i: discord.Interaction):
            cfg = await self.bot.db.get_ticket_config(self.guild_id)
            await i.response.send_modal(TicketPanelTextModal(self, cfg.get("panel_title"), cfg.get("panel_desc"), cfg.get("open_button_label")))
        btn_panel_texts.callback = on_panel_texts

        btn_inside_texts = discord.ui.Button(label="Textes dans le Ticket", emoji="🎟️", style=discord.ButtonStyle.secondary)
        async def on_inside_texts(i: discord.Interaction):
            cfg = await self.bot.db.get_ticket_config(self.guild_id)
            await i.response.send_modal(TicketInsideTextModal(self, cfg.get("welcome_message"), cfg.get("ticket_guide")))
        btn_inside_texts.callback = on_inside_texts

        btn_cats = discord.ui.Button(label="Catégories", emoji="🏷️", style=discord.ButtonStyle.secondary)
        async def on_cats(i: discord.Interaction):
            cfg = await self.bot.db.get_ticket_config(self.guild_id)
            c_str = ", ".join(c["name"] if isinstance(c, dict) else str(c) for c in (cfg.get("categories") or []))
            await i.response.send_modal(TicketCategoriesModal(self, c_str))
        btn_cats.callback = on_cats

        cont.add_item(discord.ui.TextDisplay("👇 **Personnalisation des Visuels & Contenus :**"))
        cont.add_item(discord.ui.ActionRow(btn_banners, btn_panel_texts, btn_inside_texts, btn_cats))
        cont.add_item(discord.ui.Separator())

        # Select menus for channels/roles
        cont.add_item(discord.ui.TextDisplay("**👮 Rôle Staff Support (accès aux tickets) :**"))
        cont.add_item(discord.ui.ActionRow(TicketSetupRoleSelect()))

        cont.add_item(discord.ui.TextDisplay("**📁 Dossier Discord (Catégorie d'accueil) :**"))
        cont.add_item(discord.ui.ActionRow(TicketSetupCategorySelect()))

        cont.add_item(discord.ui.TextDisplay("**🪵 Salon des Transcriptions (Logs) :**"))
        cont.add_item(discord.ui.ActionRow(TicketSetupLogSelect()))

        cont.add_item(discord.ui.Separator())
        cont.add_item(discord.ui.TextDisplay("🚀 **Déployer le Panel dans un salon :**"))
        cont.add_item(discord.ui.ActionRow(TicketDeploySelect(self)))

        self.add_item(cont)

    async def refresh(self, interaction: discord.Interaction):
        await self.build(interaction.guild)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)


# ══════════════════════════════════════════════════════════════════════════════
#  Main Cog
# ══════════════════════════════════════════════════════════════════════════════

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Register persistent views
        self.bot.add_view(TicketOpenView(self.bot))
        self.bot.add_view(TicketControlView(self.bot))

    # ══════════════════════════════════════════════════════════════════════════
    #  Global Interaction Listener: 100% Fail-Proof Button & Menu Dispatcher
    # ══════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        if not custom_id:
            return

        # 1. Panel Open Button (supports both new and legacy custom_ids)
        if custom_id in ("ticket_open_btn_persistent", "ticket_open_persistent", "ticket_open"):
            config = await self.bot.db.get_ticket_config(interaction.guild.id)
            cats = [c for c in (config.get("categories") or []) if c]
            if not cats:
                cats = [
                    {"name": "Support Général"},
                    {"name": "Plainte & Signalement"},
                    {"name": "Partenariats"}
                ]
            view = discord.ui.View(timeout=60)
            view.add_item(TicketCategorySelect(self.bot, cats))
            return await interaction.response.send_message(
                "👇 **Choisis la catégorie de ton ticket dans le menu déroulant ci-dessous :**",
                view=view,
                ephemeral=True
            )

        # 2. Category Dropdown Menu
        if custom_id in ("ticket_category_select_menu", "ticket_category_select"):
            values = interaction.data.get("values", [])
            if values:
                category = values[0]
                config = await self.bot.db.get_ticket_config(interaction.guild.id)
                questions = config.get("questions") or {}
                if isinstance(questions, str):
                    try:
                        questions = json.loads(questions)
                    except Exception:
                        questions = {}
                cat_questions = questions.get(category)
                if cat_questions:
                    return await interaction.response.send_modal(TicketFormModal(self.bot, cat_questions, category))
                else:
                    return await _open_ticket(self.bot, interaction, category)

        # 3. Inside-ticket Claim Button
        if custom_id in ("ticket_claim_btn", "ticket_claim", "ticket_unclaim"):
            return await handle_ticket_claim(self.bot, interaction)

        # 4. Inside-ticket Close Button
        if custom_id in ("ticket_close_btn", "ticket_close_persistent", "ticket_close"):
            return await handle_ticket_close_prompt(self.bot, interaction)

        # 5. Inside-ticket Transcript Button
        if custom_id in ("ticket_transcript_btn", "ticket_transcript"):
            return await handle_ticket_transcript(self.bot, interaction)

        # 6. Inside-ticket Member Management
        if custom_id in ("ticket_members_btn", "ticket_add", "ticket_remove"):
            return await handle_ticket_members_prompt(self.bot, interaction)

    # ══════════════════════════════════════════════════════════════════════════
    #  Slash Commands
    # ══════════════════════════════════════════════════════════════════════════

    ticket_group = app_commands.Group(name="ticket", description="Gestion avancée du système de tickets")

    @ticket_group.command(name="setup", description="Ouvre le Dashboard complet de configuration des tickets")
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_setup(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        view = TicketSetupDashboardView(self.bot, lang, interaction.guild.id)
        await view.build(interaction.guild)
        await interaction.response.send_message(view=view, ephemeral=True)

    @ticket_group.command(name="close", description="Ferme et archive le ticket actuel")
    async def ticket_close(self, interaction: discord.Interaction):
        await handle_ticket_close_prompt(self.bot, interaction)

    @ticket_group.command(name="claim", description="Prend en charge le ticket actuel")
    async def ticket_claim(self, interaction: discord.Interaction):
        await handle_ticket_claim(self.bot, interaction)

    @ticket_group.command(name="unclaim", description="Se retire de la prise en charge du ticket")
    async def ticket_unclaim(self, interaction: discord.Interaction):
        await handle_ticket_claim(self.bot, interaction)

    @ticket_group.command(name="transcript", description="Génère la transcription immédiate du ticket sans le fermer")
    async def ticket_transcript(self, interaction: discord.Interaction):
        await handle_ticket_transcript(self.bot, interaction)

    @ticket_group.command(name="add", description="Donne accès à un membre sur le ticket actuel")
    @app_commands.describe(membre="Membre à ajouter au ticket")
    async def ticket_cmd_add(self, interaction: discord.Interaction, membre: discord.Member):
        if not await self.bot.db.get_ticket(interaction.channel.id):
            return await interaction.response.send_message(embed=error_embed("❌ Ce salon n'est pas un ticket actif."), ephemeral=True)
        await interaction.channel.set_permissions(
            membre, view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True, embed_links=True
        )
        await interaction.response.send_message(f"✅ {membre.mention} a été ajouté au ticket avec succès !")

    @ticket_group.command(name="remove", description="Retire l'accès d'un membre sur le ticket actuel")
    @app_commands.describe(membre="Membre à retirer du ticket")
    async def ticket_cmd_remove(self, interaction: discord.Interaction, membre: discord.Member):
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(embed=error_embed("❌ Ce salon n'est pas un ticket actif."), ephemeral=True)
        if ticket["user_id"] == membre.id:
            return await interaction.response.send_message(embed=error_embed("❌ Tu ne peux pas retirer le créateur du ticket !"), ephemeral=True)
        await interaction.channel.set_permissions(membre, overwrite=None)
        await interaction.response.send_message(f"✅ {membre.mention} a été retiré du ticket.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
