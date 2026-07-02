import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.embeds import error_embed, success_embed
from utils.i18n import t

STYLE_MAP = {
    "primary":   discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success":   discord.ButtonStyle.success,
    "danger":    discord.ButtonStyle.danger,
}


# ── Button & View ─────────────────────────────────────────────────────────────

class RoleButton(discord.ui.Button):
    def __init__(self, role_id: int, label: str, emoji: str = None,
                 style: discord.ButtonStyle = discord.ButtonStyle.secondary, custom_id: str = ""):
        super().__init__(label=label, emoji=emoji, style=style, custom_id=custom_id)
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        lang = await interaction.client.db.get_guild_lang(interaction.guild_id)
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message(embed=error_embed(t(lang, "rr.role_gone")), ephemeral=True)
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                t(lang, "rr.role_too_high"), ephemeral=True
            )
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Rôle réactif — retrait")
            await interaction.response.send_message(embed=error_embed(t(lang, "rr.role_removed", role=role.name)), ephemeral=True)
        else:
            await interaction.user.add_roles(role, reason="Rôle réactif — attribution")
            await interaction.response.send_message(embed=success_embed(t(lang, "rr.role_added", role=role.name)), ephemeral=True)


def build_rr_view(buttons_data: list) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for btn in buttons_data:
        style = STYLE_MAP.get(btn["style"], discord.ButtonStyle.secondary)
        view.add_item(RoleButton(
            role_id=btn["role_id"],
            label=btn["label"],
            emoji=btn["emoji"],
            style=style,
            custom_id=f"rr_{btn['id']}"
        ))
    return view


# ── Cog ───────────────────────────────────────────────────────────────────────

class ReactionRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        panels = await self.bot.db.get_all_rr_panels_global()
        for panel in panels:
            buttons = await self.bot.db.get_rr_buttons(panel["id"])
            if buttons:
                view = build_rr_view([dict(b) for b in buttons])
                self.bot.add_view(view, message_id=panel["message_id"])

    rr_group = app_commands.Group(name="rr", description="Gestion des rôles réactifs")

    # ── Autocomplete ──────────────────────────────────────────────────────────

    async def _panel_autocomplete(self, interaction: discord.Interaction, current: str):
        panels = await self.bot.db.get_all_rr_panels(interaction.guild.id)
        choices = []
        for p in panels:
            label = f"#{p['id']} — {p['title']}"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=p["id"]))
        return choices[:25]

    async def _button_autocomplete(self, interaction: discord.Interaction, current: str):
        panel_id = interaction.namespace.panel_id
        if not panel_id:
            return []
        buttons = await self.bot.db.get_rr_buttons(panel_id)
        choices = []
        for b in buttons:
            role = interaction.guild.get_role(b["role_id"])
            label = f"#{b['id']} — {b['label']} → {role.name if role else '???'}"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=b["id"]))
        return choices[:25]

    # ── /rr create ────────────────────────────────────────────────────────────

    @rr_group.command(name="create", description="Crée un panel de rôles réactifs dans un salon")
    @app_commands.describe(
        salon="Le salon où envoyer le panel",
        titre="Le titre du panel",
        description="Description du panel (optionnel)"
    )
    @app_commands.default_permissions(manage_roles=True)
    async def rr_create(self, interaction: discord.Interaction, salon: discord.TextChannel, titre: str, description: str = None):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        embed = discord.Embed(
            title=titre,
            description=description or "",
            color=Colors.INFO
        )
        embed.set_footer(text=t(lang, "rr.panel_footer"))

        msg = await salon.send(embed=embed)
        panel_id = await self.bot.db.create_rr_panel(interaction.guild.id, salon.id, msg.id, titre, description)

        await interaction.response.send_message(
            t(lang, "rr.create_success", panel_id=panel_id, channel=salon.mention),
            ephemeral=True
        )

    # ── /rr add ───────────────────────────────────────────────────────────────

    @rr_group.command(name="add", description="Ajoute un bouton de rôle à un panel")
    @app_commands.describe(
        panel_id="L'ID du panel (voir /rr list)",
        role="Le rôle à attribuer",
        etiquette="Le texte affiché sur le bouton",
        emoji="Un emoji pour le bouton (optionnel)",
        couleur="La couleur du bouton"
    )
    @app_commands.choices(couleur=[
        app_commands.Choice(name="Bleu (défaut)", value="primary"),
        app_commands.Choice(name="Gris", value="secondary"),
        app_commands.Choice(name="Vert", value="success"),
        app_commands.Choice(name="Rouge", value="danger"),
    ])
    @app_commands.autocomplete(panel_id=_panel_autocomplete)
    @app_commands.default_permissions(manage_roles=True)
    async def rr_add(
        self, interaction: discord.Interaction,
        panel_id: int, role: discord.Role,
        etiquette: str, emoji: str = None, couleur: str = "secondary"
    ):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        panel = await self.bot.db.get_rr_panel_by_id(panel_id, interaction.guild.id)
        if not panel:
            return await interaction.response.send_message(embed=error_embed(t(lang, "rr.panel_not_found", panel_id=panel_id)), ephemeral=True)

        buttons = await self.bot.db.get_rr_buttons(panel_id)
        if len(buttons) >= 25:
            return await interaction.response.send_message(embed=error_embed(t(lang, "rr.max_buttons")), ephemeral=True)

        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                t(lang, "rr.role_too_high"), ephemeral=True
            )

        btn_id = await self.bot.db.add_rr_button(panel_id, role.id, etiquette, emoji, couleur)
        await self._rebuild_panel(interaction.guild, dict(panel), panel_id, lang)

        await interaction.response.send_message(
            t(lang, "rr.add_success", btn_id=btn_id, panel_id=panel_id, role=role.mention), ephemeral=True
        )

    # ── /rr remove ────────────────────────────────────────────────────────────

    @rr_group.command(name="remove", description="Retire un bouton d'un panel")
    @app_commands.describe(panel_id="L'ID du panel", bouton_id="L'ID du bouton à retirer (voir /rr list)")
    @app_commands.autocomplete(panel_id=_panel_autocomplete, bouton_id=_button_autocomplete)
    @app_commands.default_permissions(manage_roles=True)
    async def rr_remove(self, interaction: discord.Interaction, panel_id: int, bouton_id: int):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        panel = await self.bot.db.get_rr_panel_by_id(panel_id, interaction.guild.id)
        if not panel:
            return await interaction.response.send_message(embed=error_embed(t(lang, "rr.panel_not_found", panel_id=panel_id)), ephemeral=True)

        await self.bot.db.remove_rr_button(bouton_id, panel_id)
        await self._rebuild_panel(interaction.guild, dict(panel), panel_id, lang)

        await interaction.response.send_message(
            t(lang, "rr.remove_success", btn_id=bouton_id, panel_id=panel_id), ephemeral=True
        )

    # ── /rr delete ────────────────────────────────────────────────────────────

    @rr_group.command(name="delete", description="Supprime un panel de rôles réactifs")
    @app_commands.describe(panel_id="L'ID du panel à supprimer")
    @app_commands.autocomplete(panel_id=_panel_autocomplete)
    @app_commands.default_permissions(manage_roles=True)
    async def rr_delete(self, interaction: discord.Interaction, panel_id: int):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        panel = await self.bot.db.get_rr_panel_by_id(panel_id, interaction.guild.id)
        if not panel:
            return await interaction.response.send_message(embed=error_embed(t(lang, "rr.panel_not_found", panel_id=panel_id)), ephemeral=True)

        channel = interaction.guild.get_channel(panel["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(panel["message_id"])
                await msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        await self.bot.db.delete_rr_panel(panel_id)
        await interaction.response.send_message(embed=success_embed(t(lang, "rr.delete_success", panel_id=panel_id)), ephemeral=True)

    # ── /rr list ──────────────────────────────────────────────────────────────

    @rr_group.command(name="list", description="Liste tous les panels de rôles réactifs du serveur")
    @app_commands.default_permissions(manage_roles=True)
    async def rr_list(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        panels = await self.bot.db.get_all_rr_panels(interaction.guild.id)
        if not panels:
            return await interaction.response.send_message(
                t(lang, "rr.list_empty"), ephemeral=True
            )

        embed = discord.Embed(title=t(lang, "rr.list_title"), color=Colors.INFO)
        for panel in panels:
            channel = interaction.guild.get_channel(panel["channel_id"])
            buttons = await self.bot.db.get_rr_buttons(panel["id"])
            btn_info = "\n".join(
                f"  `#{b['id']}` {b['emoji'] or ''} **{b['label']}** → <@&{b['role_id']}>"
                for b in buttons
            ) or t(lang, "rr.no_buttons")
            embed.add_field(
                name=f"#{panel['id']} — {panel['title']}",
                value=t(lang, "rr.panel_entry", channel=channel.mention if channel else t(lang, "rr.channel_not_found"), buttons=btn_info),
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Helper ────────────────────────────────────────────────────────────────

    async def _rebuild_panel(self, guild: discord.Guild, panel: dict, panel_id: int, lang: str):
        channel = guild.get_channel(panel["channel_id"])
        if not channel:
            return
        try:
            msg = await channel.fetch_message(panel["message_id"])
        except (discord.NotFound, discord.Forbidden):
            return

        buttons = await self.bot.db.get_rr_buttons(panel_id)
        embed = discord.Embed(
            title=panel["title"],
            description=panel.get("description") or "",
            color=Colors.INFO
        )
        embed.set_footer(text=t(lang, "rr.panel_footer"))

        if buttons:
            view = build_rr_view([dict(b) for b in buttons])
            self.bot.add_view(view, message_id=msg.id)
            await msg.edit(embed=embed, view=view)
        else:
            await msg.edit(embed=embed, view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
