import asyncio
import discord
from discord import app_commands
from discord.ext import commands


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
        guild = interaction.guild
        user = interaction.user

        existing = await self.bot.db.get_user_open_ticket(guild.id, user.id)
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            if channel:
                return await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket ouvert : {channel.mention}", ephemeral=True
                )

        config = await self.bot.db.get_ticket_config(guild.id)
        if not config.get("staff_role_id"):
            return await interaction.response.send_message(
                "❌ Le système de tickets n'est pas encore configuré.", ephemeral=True
            )

        category = guild.get_channel(config["category_id"]) if config.get("category_id") else None
        staff_role = guild.get_role(config["staff_role_id"]) if config.get("staff_role_id") else None

        ticket_number = await self.bot.db.increment_ticket_counter(guild.id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, attach_files=True
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
                name=f"ticket-{ticket_number:04d}",
                category=category,
                overwrites=overwrites,
                reason=f"Ticket ouvert par {user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Je n'ai pas la permission de créer un salon.", ephemeral=True
            )

        await self.bot.db.create_ticket(guild.id, channel.id, user.id, ticket_number)

        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_number:04d}",
            description=(
                f"Bienvenue {user.mention} !\n\n"
                "Décris ton problème ou ta demande et notre équipe te répondra dès que possible.\n"
                "Clique sur **Fermer** quand le ticket est résolu."
            ),
            color=discord.Color.blurple()
        )
        if staff_role:
            embed.add_field(name="Support", value=staff_role.mention, inline=True)
        embed.set_thumbnail(url=user.display_avatar.url)

        await channel.send(embed=embed, view=TicketCloseView(self.bot))
        await channel.send(user.mention, delete_after=1)

        await interaction.response.send_message(
            f"✅ Ticket créé : {channel.mention}", ephemeral=True
        )

        if logs := self.bot.get_cog("Logs"):
            log_embed = discord.Embed(title="🎫 Ticket ouvert", color=discord.Color.green())
            log_embed.add_field(name="Membre", value=f"{user.mention} (`{user.id}`)", inline=True)
            log_embed.add_field(name="Salon", value=channel.mention, inline=True)
            log_embed.add_field(name="Numéro", value=f"#{ticket_number:04d}", inline=True)
            await logs.send_log(guild, log_embed)


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

        config = await self.bot.db.get_ticket_config(interaction.guild.id)
        staff_role_id = config.get("staff_role_id")
        is_owner = ticket["user_id"] == interaction.user.id
        is_staff = (
            interaction.user.guild_permissions.manage_channels
            or (staff_role_id and any(r.id == staff_role_id for r in interaction.user.roles))
        )

        if not (is_owner or is_staff):
            return await interaction.response.send_message(
                "❌ Seul le créateur du ticket ou un membre du staff peut le fermer.", ephemeral=True
            )

        await interaction.response.send_message(
            "⚠️ Es-tu sûr de vouloir fermer ce ticket ?",
            view=TicketCloseConfirmView(self.bot, ticket, config),
            ephemeral=True
        )


class TicketCloseConfirmView(discord.ui.View):
    def __init__(self, bot: commands.Bot, ticket: dict, config: dict):
        super().__init__(timeout=30)
        self.bot = bot
        self.ticket = ticket
        self.config = config

    @discord.ui.button(label="✅ Confirmer la fermeture", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer()

        channel = interaction.channel
        guild = interaction.guild

        # Génération de la transcription
        transcript_lines = []
        async for msg in channel.history(limit=150, oldest_first=True):
            ts = msg.created_at.strftime("%d/%m %H:%M")
            content = msg.content or ("[embed]" if msg.embeds else "[fichier]" if msg.attachments else "")
            transcript_lines.append(f"[{ts}] {msg.author.display_name}: {content}")

        # Envoi du log avec transcript
        log_channel_id = self.config.get("log_channel_id")
        if not log_channel_id:
            settings = await self.bot.db.get_guild_settings(guild.id)
            log_channel_id = settings.get("log_channel_id")

        if log_channel_id:
            log_ch = guild.get_channel(log_channel_id)
            if log_ch:
                owner = guild.get_member(self.ticket["user_id"])
                embed = discord.Embed(
                    title=f"🎫 Ticket #{self.ticket['ticket_number']:04d} — Fermé",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="Ouvert par",
                    value=owner.mention if owner else f"ID:{self.ticket['user_id']}",
                    inline=True
                )
                embed.add_field(name="Fermé par", value=interaction.user.mention, inline=True)

                transcript_text = "\n".join(transcript_lines[-60:]) if transcript_lines else "Aucun message."
                if len(transcript_text) > 1900:
                    transcript_text = "..." + transcript_text[-1900:]
                embed.add_field(
                    name="Transcription",
                    value=f"```\n{transcript_text}\n```",
                    inline=False
                )
                try:
                    await log_ch.send(embed=embed)
                except discord.Forbidden:
                    pass

        await self.bot.db.close_ticket(channel.id, interaction.user.id)

        try:
            await channel.send("🔒 Ticket fermé. Suppression dans 5 secondes...")
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

    # ── /ticket setup ─────────────────────────────────────────────────────────

    @app_commands.command(name="ticket", description="Configure le système de tickets et envoie le panel")
    @app_commands.describe(
        salon="Salon où envoyer le panel d'ouverture",
        role_staff="Rôle de l'équipe de support",
        categorie="Catégorie où créer les tickets (optionnel)",
        salon_logs="Salon de logs dédié aux tickets (optionnel)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        salon: discord.TextChannel,
        role_staff: discord.Role,
        categorie: discord.CategoryChannel = None,
        salon_logs: discord.TextChannel = None,
    ):
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_ticket_config(gid, "staff_role_id", role_staff.id)
        if categorie:
            await db.update_ticket_config(gid, "category_id", categorie.id)
        if salon_logs:
            await db.update_ticket_config(gid, "log_channel_id", salon_logs.id)

        embed = discord.Embed(
            title="🎫 Support — Ouvrir un ticket",
            description=(
                "Clique sur le bouton ci-dessous pour ouvrir un ticket de support.\n"
                "Notre équipe te répondra dès que possible."
            ),
            color=discord.Color.blurple()
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text=interaction.guild.name)

        view = TicketOpenView(self.bot)
        panel = await salon.send(embed=embed, view=view)

        await db.update_ticket_config(gid, "panel_message_id", panel.id)
        await db.update_ticket_config(gid, "panel_channel_id", salon.id)

        await interaction.response.send_message(
            f"✅ Système de tickets configuré ! Panel envoyé dans {salon.mention}.", ephemeral=True
        )

    # ── /tadd /tremove ────────────────────────────────────────────────────────

    @app_commands.command(name="tadd", description="Ajoute un membre à ce ticket")
    @app_commands.describe(membre="Le membre à ajouter au ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def tadd(self, interaction: discord.Interaction, membre: discord.Member):
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        await interaction.channel.set_permissions(
            membre,
            view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True
        )
        await interaction.response.send_message(f"✅ {membre.mention} a été ajouté au ticket.")

    @app_commands.command(name="tremove", description="Retire un membre de ce ticket")
    @app_commands.describe(membre="Le membre à retirer du ticket")
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
        await interaction.response.send_message(f"✅ {membre.mention} a été retiré du ticket.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
