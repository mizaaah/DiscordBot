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
    global_staff_role_id = config.get("staff_role_id")
    global_category_id = config.get("category_id")

    # Determine category channel and specific staff role
    ticket_cat = None
    category_staff_role = None
    if category:
        cats = config.get("categories") or []
        for c in cats:
            if isinstance(c, dict) and c.get("name", "").lower() == category.lower():
                if c.get("category_id"):
                    ticket_cat = guild.get_channel(c["category_id"])
                if c.get("staff_role_id"):
                    category_staff_role = guild.get_role(c["staff_role_id"])
                break

    if not ticket_cat and global_category_id:
        ticket_cat = guild.get_channel(global_category_id)

    global_staff_role = guild.get_role(global_staff_role_id) if global_staff_role_id else None

    if not global_staff_role and not category_staff_role:
        return await interaction.followup.send(
            embed=error_embed("❌ Le système de tickets n'a aucun rôle Staff configuré. Veuillez exécuter `/ticket setup`."),
            ephemeral=True
        )

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

    staff_mentions = []
    if global_staff_role:
        overwrites[global_staff_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            manage_messages=True, attach_files=True, embed_links=True
        )
        staff_mentions.append(global_staff_role.mention)

    if category_staff_role and category_staff_role != global_staff_role:
        overwrites[category_staff_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            manage_messages=True, attach_files=True, embed_links=True
        )
        staff_mentions.append(category_staff_role.mention)

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            category=ticket_cat,
            overwrites=overwrites,
            reason=f"Ticket #{ticket_num:04d} ({category or 'Général'}) ouvert par {user}"
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
    pings = f"{user.mention} {' '.join(staff_mentions)}"
    await channel.send(content=pings, embed=embed, view=view)

    # Inform the user with direct link
    await interaction.followup.send(
        embed=success_embed(f"✅ Ton ticket **{category or 'Général'}** a été créé avec succès dans {channel.mention} !"),
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
            emoji = c.get("emoji") if (isinstance(c, dict) and c.get("emoji")) else "🎫"
            desc = c.get("description") if (isinstance(c, dict) and c.get("description")) else "Ouvrir une demande dans cette section"
            nl = name.lower()
            if emoji == "🎫":
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
                elif "vip" in nl or "boost" in nl or "grade" in nl or "boutique" in nl:
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
    def __init__(self, refresh_cb, current_welcome: str, current_guide: str):
        super().__init__(title="🎟️ Textes à l'Intérieur du Ticket")
        self.refresh_cb = refresh_cb

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
        await self.refresh_cb(interaction)


class TicketAddCategoryModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot, parent_view: "TicketCategoryManagerView"):
        super().__init__(title="➕ Nouvelle Catégorie de Ticket")
        self.bot = bot
        self.parent_view = parent_view

        self.name_input = discord.ui.TextInput(
            label="Nom de la catégorie",
            placeholder="Ex: Recrutement, Support Technique, Plaintes, Partenariats",
            required=True,
            max_length=40
        )
        self.emoji_input = discord.ui.TextInput(
            label="Emoji représentatif",
            placeholder="Ex: 📋, 🛠️, ⚖️, 🤝, 💎",
            default="🎫",
            required=False,
            max_length=10
        )
        self.desc_input = discord.ui.TextInput(
            label="Description courte (affichée dans le menu)",
            style=discord.TextStyle.short,
            placeholder="Ex: Postuler pour rejoindre l'équipe du serveur",
            required=False,
            max_length=100
        )
        self.add_item(self.name_input)
        self.add_item(self.emoji_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        cat_data = {
            "name": self.name_input.value.strip(),
            "emoji": self.emoji_input.value.strip() or "🎫",
            "description": self.desc_input.value.strip() or "Ouvrir une demande dans cette section",
            "category_id": None,
            "staff_role_id": None
        }
        # Proceed to step 2: choose discord category and staff role
        view = TicketCategoryConfigureView(self.bot, interaction.guild.id, cat_data, self.parent_view)
        await view.render(interaction)


# ══════════════════════════════════════════════════════════════════════════════
#  Sub-View: Category Discord Folder & Staff Mapping
# ══════════════════════════════════════════════════════════════════════════════

class TicketCategoryConfigureView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, cat_data: dict, parent_view: "TicketCategoryManagerView"):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.cat_data = cat_data
        self.parent_view = parent_view

        self.selected_cat_id = cat_data.get("category_id")
        self.selected_role_id = cat_data.get("staff_role_id")

        self._build_components()

    def _build_components(self):
        self.clear_items()

        # 1. Channel select for Discord Category
        cat_select = discord.ui.ChannelSelect(
            placeholder="📁 Choisir la Catégorie Discord (dossier d'accueil)...",
            channel_types=[discord.ChannelType.category],
            min_values=1,
            max_values=1,
            row=0
        )
        async def on_cat_change(i: discord.Interaction):
            self.selected_cat_id = cat_select.values[0].id
            await self._update_msg(i)
        cat_select.callback = on_cat_change
        self.add_item(cat_select)

        # 2. Role select for Staff
        role_select = discord.ui.RoleSelect(
            placeholder="👮 Choisir le Rôle Staff dédié (optionnel)...",
            min_values=1,
            max_values=1,
            row=1
        )
        async def on_role_change(i: discord.Interaction):
            self.selected_role_id = role_select.values[0].id
            await self._update_msg(i)
        role_select.callback = on_role_change
        self.add_item(role_select)

        # 3. Save button
        btn_save = discord.ui.Button(label="Enregistrer la Catégorie", emoji="💾", style=discord.ButtonStyle.success, row=2)
        async def on_save(i: discord.Interaction):
            cfg = await self.bot.db.get_ticket_config(self.guild_id)
            cats = [c for c in (cfg.get("categories") or []) if c]

            # Update if already exists, else append
            updated = False
            for idx, c in enumerate(cats):
                if isinstance(c, dict) and c.get("name", "").lower() == self.cat_data["name"].lower():
                    cats[idx] = {
                        "name": self.cat_data["name"],
                        "emoji": self.cat_data.get("emoji", "🎫"),
                        "description": self.cat_data.get("description", ""),
                        "category_id": self.selected_cat_id,
                        "staff_role_id": self.selected_role_id
                    }
                    updated = True
                    break

            if not updated:
                cats.append({
                    "name": self.cat_data["name"],
                    "emoji": self.cat_data.get("emoji", "🎫"),
                    "description": self.cat_data.get("description", ""),
                    "category_id": self.selected_cat_id,
                    "staff_role_id": self.selected_role_id
                })

            await self.bot.db.update_ticket_config(self.guild_id, "categories", cats)
            await self.parent_view.render(i)
        btn_save.callback = on_save
        self.add_item(btn_save)

        # 4. Cancel button
        btn_cancel = discord.ui.Button(label="Annuler", emoji="🔙", style=discord.ButtonStyle.secondary, row=2)
        async def on_cancel(i: discord.Interaction):
            await self.parent_view.render(i)
        btn_cancel.callback = on_cancel
        self.add_item(btn_cancel)

    def _get_embed(self, guild: discord.Guild) -> discord.Embed:
        cat_ch = guild.get_channel(self.selected_cat_id) if self.selected_cat_id else None
        role_obj = guild.get_role(self.selected_role_id) if self.selected_role_id else None

        cat_str = cat_ch.mention if cat_ch else "*Dossier par défaut du serveur*"
        role_str = role_obj.mention if role_obj else "*Staff Support par défaut*"

        embed = discord.Embed(
            title=f"📁 Configuration de « {self.cat_data.get('emoji', '🎫')} {self.cat_data['name']} »",
            description=(
                f"Définissez dans quel dossier Discord les tickets de cette catégorie seront créés "
                f"et quelle équipe aura les permissions nécessaires.\n\n"
                f"📝 **Description :** *{self.cat_data.get('description', 'Aucune')}*\n"
                f"📁 **Dossier Discord cible :** {cat_str}\n"
                f"👮 **Rôle Staff assigné :** {role_str}\n\n"
                f"💡 *Utilisez les menus ci-dessous puis cliquez sur **Enregistrer**.*"
            ),
            color=Colors.PRIMARY.value
        )
        return embed

    async def render(self, interaction: discord.Interaction):
        embed = self._get_embed(interaction.guild)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def _update_msg(self, interaction: discord.Interaction):
        embed = self._get_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)


# ══════════════════════════════════════════════════════════════════════════════
#  Sub-View: Category Management
# ══════════════════════════════════════════════════════════════════════════════

class TicketCategoryManagerView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, dashboard: "TicketSetupDashboardView"):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.dashboard = dashboard

    async def render(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await self.bot.db.get_ticket_config(self.guild_id)
        cats = [c for c in (cfg.get("categories") or []) if c]

        self.clear_items()

        # Add Category Button
        btn_add = discord.ui.Button(label="Ajouter une Catégorie", emoji="➕", style=discord.ButtonStyle.success, row=0)
        async def on_add(i: discord.Interaction):
            await i.response.send_modal(TicketAddCategoryModal(self.bot, self))
        btn_add.callback = on_add
        self.add_item(btn_add)

        # Edit Category Select Menu
        if cats:
            edit_options = []
            for c in cats[:25]:
                name = c["name"] if isinstance(c, dict) else str(c)
                emoji = c.get("emoji", "🎫") if isinstance(c, dict) else "🎫"
                edit_options.append(discord.SelectOption(label=name[:100], value=name[:100], emoji=emoji, description="Modifier le dossier Discord ou le rôle staff"))

            edit_select = discord.ui.Select(
                placeholder="✏️ Modifier une catégorie existante...",
                options=edit_options,
                row=1
            )
            async def on_edit(i: discord.Interaction):
                chosen_name = edit_select.values[0]
                target_c = None
                for c in cats:
                    if isinstance(c, dict) and c.get("name") == chosen_name:
                        target_c = c
                        break
                if not target_c:
                    target_c = {"name": chosen_name, "emoji": "🎫", "description": "", "category_id": None, "staff_role_id": None}
                view = TicketCategoryConfigureView(self.bot, self.guild_id, target_c, self)
                await view.render(i)
            edit_select.callback = on_edit
            self.add_item(edit_select)

            # Delete Select Menu
            del_options = [
                discord.SelectOption(label=f"Supprimer {c['name'] if isinstance(c, dict) else c}"[:100], value=c["name"] if isinstance(c, dict) else str(c), emoji="🗑️")
                for c in cats[:25]
            ]
            del_select = discord.ui.Select(
                placeholder="🗑️ Supprimer une catégorie...",
                options=del_options,
                row=2
            )
            async def on_delete(i: discord.Interaction):
                chosen = del_select.values[0]
                new_cats = [c for c in cats if (c["name"] if isinstance(c, dict) else str(c)) != chosen]
                await self.bot.db.update_ticket_config(self.guild_id, "categories", new_cats)
                await self.render(i)
            del_select.callback = on_delete
            self.add_item(del_select)

        # Back to Dashboard Button
        btn_back = discord.ui.Button(label="Retour au Dashboard", emoji="🔙", style=discord.ButtonStyle.secondary, row=3)
        async def on_back(i: discord.Interaction):
            await self.dashboard.render(i)
        btn_back.callback = on_back
        self.add_item(btn_back)

        # Build clean embed
        lines = []
        if cats:
            for idx, c in enumerate(cats, start=1):
                name = c["name"] if isinstance(c, dict) else str(c)
                emoji = c.get("emoji", "🎫") if isinstance(c, dict) else "🎫"
                desc = c.get("description", "") if isinstance(c, dict) else ""
                cat_id = c.get("category_id") if isinstance(c, dict) else None
                role_id = c.get("staff_role_id") if isinstance(c, dict) else None

                cat_ch = guild.get_channel(cat_id) if cat_id else None
                role_obj = guild.get_role(role_id) if role_id else None

                cat_str = cat_ch.mention if cat_ch else "`Dossier par défaut`"
                role_str = role_obj.mention if role_obj else "`Staff par défaut`"

                prefix = "┌" if idx == 1 else ("└" if idx == len(cats) else "├")
                lines.append(f"{prefix} {emoji} **{name}**\n│  📁 Dossier: {cat_str} ┆ 👮 Staff: {role_str}\n│  📝 *{desc or 'Aucune description'}*")
        else:
            lines.append("*Aucune catégorie personnalisée configurée. Les catégories par défaut sont utilisées.*")

        embed = discord.Embed(
            title=f"📁 Gestionnaire des Catégories de Tickets • {guild.name}",
            description=(
                f"Chaque catégorie de ticket peut être envoyée dans **son propre dossier Discord** "
                f"et être gérée par **une équipe Staff dédiée** (ex: Recruteurs, Modérateurs, Support).\n\n"
                + "\n│\n".join(lines) + "\n\n"
                f"➕ **Ajouter :** Cliquez sur le bouton vert ci-dessous.\n"
                f"✏️ **Associer un dossier Discord :** Utilisez le menu déroulant bleu ci-dessous."
            ),
            color=Colors.PRIMARY.value
        )
        embed.set_footer(text="Système de Tickets Avancé • Antigravity")

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


# ══════════════════════════════════════════════════════════════════════════════
#  Sub-View: General Settings (Default Staff, Category, Logs)
# ══════════════════════════════════════════════════════════════════════════════

class TicketGeneralSettingsView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, dashboard: "TicketSetupDashboardView"):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.dashboard = dashboard

    async def render(self, interaction: discord.Interaction):
        self.clear_items()
        guild = interaction.guild
        cfg = await self.bot.db.get_ticket_config(self.guild_id)

        # 1. Staff Support Role
        role_select = discord.ui.RoleSelect(
            placeholder="👮 Définir le Rôle Staff Support par défaut...",
            min_values=1, max_values=1, row=0
        )
        async def on_role(i: discord.Interaction):
            await self.bot.db.update_ticket_config(self.guild_id, "staff_role_id", role_select.values[0].id)
            await self.render(i)
        role_select.callback = on_role
        self.add_item(role_select)

        # 2. Default Discord Category
        cat_select = discord.ui.ChannelSelect(
            placeholder="📁 Définir le Dossier Discord (catégorie) par défaut...",
            channel_types=[discord.ChannelType.category],
            min_values=1, max_values=1, row=1
        )
        async def on_cat(i: discord.Interaction):
            await self.bot.db.update_ticket_config(self.guild_id, "category_id", cat_select.values[0].id)
            await self.render(i)
        cat_select.callback = on_cat
        self.add_item(cat_select)

        # 3. Log channel
        log_select = discord.ui.ChannelSelect(
            placeholder="🪵 Définir le Salon des Transcriptions (Logs)...",
            channel_types=[discord.ChannelType.text],
            min_values=1, max_values=1, row=2
        )
        async def on_log(i: discord.Interaction):
            await self.bot.db.update_ticket_config(self.guild_id, "log_channel_id", log_select.values[0].id)
            await self.render(i)
        log_select.callback = on_log
        self.add_item(log_select)

        # 4. Back button
        btn_back = discord.ui.Button(label="Retour au Dashboard", emoji="🔙", style=discord.ButtonStyle.secondary, row=3)
        async def on_back(i: discord.Interaction):
            await self.dashboard.render(i)
        btn_back.callback = on_back
        self.add_item(btn_back)

        staff_role = guild.get_role(cfg.get("staff_role_id")) if cfg.get("staff_role_id") else None
        cat_ch = guild.get_channel(cfg.get("category_id")) if cfg.get("category_id") else None
        log_ch = guild.get_channel(cfg.get("log_channel_id")) if cfg.get("log_channel_id") else None

        embed = discord.Embed(
            title=f"⚙️ Paramètres Généraux des Tickets • {guild.name}",
            description=(
                f"Ces réglages constituent les **valeurs par défaut** du système.\n\n"
                f"👮 **Rôle Staff par défaut :** {staff_role.mention if staff_role else '*Non configuré*'}\n"
                f"> *Reçoit l'accès aux tickets qui n'ont pas de rôle spécifique.*\n\n"
                f"📁 **Dossier Discord d'accueil par défaut :** {cat_ch.mention if cat_ch else '*Non configuré*'}\n"
                f"> *Salon catégorie où sont placés les tickets sans dossier spécifique.*\n\n"
                f"🪵 **Salon des Transcriptions & Logs :** {log_ch.mention if log_ch else '*Non configuré*'}\n"
                f"> *Reçoit les récapitulatifs complets et fichiers .txt lors de la fermeture.*"
            ),
            color=Colors.PRIMARY.value
        )
        embed.set_footer(text="Sélectionnez une option dans les menus ci-dessous pour modifier")

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


# ══════════════════════════════════════════════════════════════════════════════
#  Sub-View: Deploy Panel to a Channel
# ══════════════════════════════════════════════════════════════════════════════

class TicketDeployView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, dashboard: "TicketSetupDashboardView"):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.dashboard = dashboard

    async def render(self, interaction: discord.Interaction):
        self.clear_items()
        guild = interaction.guild
        cfg = await self.bot.db.get_ticket_config(self.guild_id)

        chan_select = discord.ui.ChannelSelect(
            placeholder="🚀 Sélectionner le salon où poster le Panel...",
            channel_types=[discord.ChannelType.text],
            min_values=1, max_values=1, row=0
        )
        async def on_deploy(i: discord.Interaction):
            ch = guild.get_channel(chan_select.values[0].id)
            if not ch:
                return await i.response.send_message("❌ Salon introuvable.", ephemeral=True)

            await i.response.defer(ephemeral=True)
            title = cfg.get("panel_title") or f"Centre d'Assistance • {guild.name}"
            desc = cfg.get("panel_desc") or "Besoin d'aide ? Choisissez la catégorie appropriée dans le menu déroulant ci-dessous pour ouvrir un ticket privé avec notre équipe."
            color = discord.Color(cfg.get("embed_color") or Colors.PRIMARY.value)

            cats = [c for c in (cfg.get("categories") or []) if c]
            if not cats:
                cats = [
                    {"name": "Support Général", "emoji": "🛠️", "description": "Besoin d'aide ou d'une information"},
                    {"name": "Recrutement Staff", "emoji": "📋", "description": "Candidater pour rejoindre l'équipe"},
                    {"name": "Plaintes & Abus", "emoji": "⚠️", "description": "Signaler un problème ou un comportement"}
                ]

            embed = discord.Embed(title=f"🎫 {title}", description=f"{desc}\n", color=color)
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            if cfg.get("panel_banner"):
                embed.set_image(url=cfg["panel_banner"])

            cat_lines = []
            for c in cats[:12]:
                name = c["name"] if isinstance(c, dict) else str(c)
                emoji = c.get("emoji", "🎫") if isinstance(c, dict) else "🎫"
                desc_c = c.get("description", "") if isinstance(c, dict) else ""
                cat_lines.append(f"{emoji} **{name}** — *{desc_c or 'Assistance'}*")

            embed.add_field(name="📂 Catégories Prises en Charge", value="\n".join(cat_lines) if cat_lines else "*Support Général*", inline=False)
            embed.set_footer(text=f"Support • {guild.name}")

            panel_view = TicketOpenView(self.bot, cats)
            msg = await ch.send(embed=embed, view=panel_view)

            await self.bot.db.update_ticket_config(self.guild_id, "panel_message_id", msg.id)
            await self.bot.db.update_ticket_config(self.guild_id, "panel_channel_id", ch.id)

            await i.followup.send(f"🎉 **Panneau de tickets déployé avec succès dans {ch.mention} !**", ephemeral=True)
            await self.dashboard.render(i)

        chan_select.callback = on_deploy
        self.add_item(chan_select)

        # Back button
        btn_back = discord.ui.Button(label="Retour au Dashboard", emoji="🔙", style=discord.ButtonStyle.secondary, row=1)
        async def on_back(i: discord.Interaction):
            await self.dashboard.render(i)
        btn_back.callback = on_back
        self.add_item(btn_back)

        cur_panel_ch = f"<#{cfg.get('panel_channel_id')}>" if cfg.get("panel_channel_id") else "*Aucun*"
        embed = discord.Embed(
            title=f"🚀 Déploiement du Panneau Public • {guild.name}",
            description=(
                f"Sélectionnez le salon textuel dans lequel vous souhaitez afficher le message de support public.\n\n"
                f"Les membres pourront y voir vos différentes catégories avec leurs emojis et ouvrir un ticket en un clic !\n\n"
                f"📍 *Salon actuellement configuré :* {cur_panel_ch}"
            ),
            color=Colors.SUCCESS.value
        )
        if cfg.get("panel_banner"):
            embed.set_thumbnail(url=cfg["panel_banner"])

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


# ══════════════════════════════════════════════════════════════════════════════
#  Main Setup Dashboard (Ultra Clean, Modern Tabbed View)
# ══════════════════════════════════════════════════════════════════════════════

class TicketSetupDashboardView(discord.ui.View):
    def __init__(self, bot: commands.Bot, lang: str, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.lang = lang
        self.guild_id = guild_id

    async def render(self, interaction: discord.Interaction):
        self.clear_items()
        guild = interaction.guild
        cfg = await self.bot.db.get_ticket_config(self.guild_id)

        # Helpers
        def ch(cid):
            if not cid: return "*Non configuré*"
            c = guild.get_channel(cid)
            return c.mention if c else "*Introuvable*"

        def role(rid):
            if not rid: return "*Non configuré*"
            r = guild.get_role(rid)
            return r.mention if r else "*Introuvable*"

        cats = [c for c in (cfg.get("categories") or []) if c]
        staff_str = role(cfg.get("staff_role_id"))
        cat_str = ch(cfg.get("category_id"))
        log_str = ch(cfg.get("log_channel_id"))
        panel_ch = ch(cfg.get("panel_channel_id"))

        panel_b = "✅ Image/GIF active" if cfg.get("panel_banner") else "❌ Aucune (par défaut)"
        welcome_b = "✅ Image/GIF active" if cfg.get("welcome_banner") else "❌ Aucune (par défaut)"
        guide_stat = "✅ Personnalisées" if cfg.get("ticket_guide") else "Par défaut"
        welc_stat = "✅ Personnalisé" if cfg.get("welcome_message") else "Par défaut"

        # Build Clean Tree of Categories
        cat_summary_lines = []
        if cats:
            for idx, c in enumerate(cats[:6], start=1):
                name = c["name"] if isinstance(c, dict) else str(c)
                emoji = c.get("emoji", "🎫") if isinstance(c, dict) else "🎫"
                cat_id = c.get("category_id") if isinstance(c, dict) else None
                role_id = c.get("staff_role_id") if isinstance(c, dict) else None

                target_f = guild.get_channel(cat_id).mention if (cat_id and guild.get_channel(cat_id)) else "*Dossier par défaut*"
                target_r = guild.get_role(role_id).mention if (role_id and guild.get_role(role_id)) else "*Staff par défaut*"

                prefix = "┌" if idx == 1 else ("└" if idx == min(len(cats), 6) else "├")
                cat_summary_lines.append(f"{prefix} {emoji} **{name}** ➔ 📁 {target_f} ┆ 👮 {target_r}")
            if len(cats) > 6:
                cat_summary_lines.append(f"*(+{len(cats) - 6} autre(s) catégorie(s)...)*")
        else:
            cat_summary_lines.append("*Aucune catégorie personnalisée (Support, Recrutement, Plainte par défaut)*")

        embed = discord.Embed(
            title=f"⚙️ Panneau de Contrôle • Système de Tickets",
            description=(
                f"Bienvenue dans l'interface de gestion avancée des tickets de **{guild.name}**.\n"
                f"Gérez vos catégories indépendantes, vos dossiers Discord d'accueil, vos équipes et vos bannières.\n\n"
                f"### 📂 Catégories de Tickets Définies ({len(cats)})\n"
                + "\n".join(cat_summary_lines) + "\n\n"
                f"### ⚙️ Paramètres par Défaut\n"
                f"• 👮 **Staff Support :** {staff_str}\n"
                f"• 📁 **Dossier d'accueil :** {cat_str}\n"
                f"• 🪵 **Salon des Logs :** {log_str}\n"
                f"• 📍 **Panel Public :** {panel_ch}\n\n"
                f"### 🎨 Visuels & Textes\n"
                f"• 🖼️ **Bannière Panel :** `{panel_b}`\n"
                f"• 🖼️ **Bannière dans le Ticket :** `{welcome_b}`\n"
                f"• 📋 **Consignes :** `{guide_stat}` ┆ 💬 **Message Accueil :** `{welc_stat}`"
            ),
            color=Colors.PRIMARY.value
        )
        if cfg.get("panel_banner"):
            embed.set_image(url=cfg["panel_banner"])
        elif guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.set_footer(text="Cliquez sur un bouton ci-dessous pour ouvrir un menu de configuration")

        # Row 0: Primary Action Buttons
        btn_cats = discord.ui.Button(label="Gérer les Catégories", emoji="📁", style=discord.ButtonStyle.primary, row=0)
        async def on_cats(i: discord.Interaction):
            view = TicketCategoryManagerView(self.bot, self.guild_id, self)
            await view.render(i)
        btn_cats.callback = on_cats
        self.add_item(btn_cats)

        btn_settings = discord.ui.Button(label="Paramètres Généraux", emoji="⚙️", style=discord.ButtonStyle.secondary, row=0)
        async def on_settings(i: discord.Interaction):
            view = TicketGeneralSettingsView(self.bot, self.guild_id, self)
            await view.render(i)
        btn_settings.callback = on_settings
        self.add_item(btn_settings)

        btn_deploy = discord.ui.Button(label="Déployer le Panel", emoji="🚀", style=discord.ButtonStyle.success, row=0)
        async def on_deploy(i: discord.Interaction):
            view = TicketDeployView(self.bot, self.guild_id, self)
            await view.render(i)
        btn_deploy.callback = on_deploy
        self.add_item(btn_deploy)

        # Row 1: Visuals & Texts
        btn_banners = discord.ui.Button(label="Bannières Image/GIF", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
        async def on_banners(i: discord.Interaction):
            await i.response.send_modal(TicketBannerModal(self, cfg.get("panel_banner"), cfg.get("welcome_banner")))
        btn_banners.callback = on_banners
        self.add_item(btn_banners)

        btn_panel_texts = discord.ui.Button(label="Textes du Panel", emoji="💬", style=discord.ButtonStyle.secondary, row=1)
        async def on_panel_texts(i: discord.Interaction):
            await i.response.send_modal(TicketPanelTextModal(self, cfg.get("panel_title"), cfg.get("panel_desc"), cfg.get("open_button_label")))
        btn_panel_texts.callback = on_panel_texts
        self.add_item(btn_panel_texts)

        btn_inside_texts = discord.ui.Button(label="Consignes & Accueil", emoji="🎟️", style=discord.ButtonStyle.secondary, row=1)
        async def on_inside_texts(i: discord.Interaction):
            await i.response.send_modal(TicketInsideTextModal(self.render, cfg.get("welcome_message"), cfg.get("ticket_guide")))
        btn_inside_texts.callback = on_inside_texts
        self.add_item(btn_inside_texts)

        btn_refresh = discord.ui.Button(label="Actualiser", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        async def on_refresh(i: discord.Interaction):
            await self.render(i)
        btn_refresh.callback = on_refresh
        self.add_item(btn_refresh)

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def refresh(self, interaction: discord.Interaction):
        await self.render(interaction)


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
        await view.render(interaction)

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
