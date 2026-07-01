import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors

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
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message("❌ Ce rôle n'existe plus.", ephemeral=True)
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Je ne peux pas gérer ce rôle (rang trop élevé).", ephemeral=True
            )
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Rôle réactif — retrait")
            await interaction.response.send_message(f"❌ Rôle **{role.name}** retiré.", ephemeral=True)
        else:
            await interaction.user.add_roles(role, reason="Rôle réactif — attribution")
            await interaction.response.send_message(f"✅ Rôle **{role.name}** obtenu !", ephemeral=True)


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

    # ── /rr create ────────────────────────────────────────────────────────────

    @rr_group.command(name="create", description="Crée un panel de rôles réactifs dans un salon")
    @app_commands.describe(
        salon="Le salon où envoyer le panel",
        titre="Le titre du panel",
        description="Description du panel (optionnel)"
    )
    @app_commands.default_permissions(manage_roles=True)
    async def rr_create(self, interaction: discord.Interaction, salon: discord.TextChannel, titre: str, description: str = None):
        embed = discord.Embed(
            title=titre,
            description=description or "",
            color=Colors.INFO
        )
        embed.set_footer(text="Clique sur un bouton pour obtenir ou retirer un rôle.")

        msg = await salon.send(embed=embed)
        panel_id = await self.bot.db.create_rr_panel(interaction.guild.id, salon.id, msg.id, titre, description)

        await interaction.response.send_message(
            f"✅ Panel **#{panel_id}** créé dans {salon.mention}.\n"
            f"Utilise `/rr add {panel_id} @rôle Étiquette` pour ajouter des boutons.",
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
    @app_commands.default_permissions(manage_roles=True)
    async def rr_add(
        self, interaction: discord.Interaction,
        panel_id: int, role: discord.Role,
        etiquette: str, emoji: str = None, couleur: str = "secondary"
    ):
        panel = await self.bot.db.get_rr_panel_by_id(panel_id, interaction.guild.id)
        if not panel:
            return await interaction.response.send_message(f"❌ Panel `#{panel_id}` introuvable.", ephemeral=True)

        buttons = await self.bot.db.get_rr_buttons(panel_id)
        if len(buttons) >= 25:
            return await interaction.response.send_message("❌ Maximum 25 boutons par panel.", ephemeral=True)

        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Je ne peux pas gérer ce rôle (rang trop élevé).", ephemeral=True
            )

        btn_id = await self.bot.db.add_rr_button(panel_id, role.id, etiquette, emoji, couleur)
        await self._rebuild_panel(interaction.guild, dict(panel), panel_id)

        await interaction.response.send_message(
            f"✅ Bouton `#{btn_id}` ajouté au panel `#{panel_id}` pour {role.mention}.", ephemeral=True
        )

    # ── /rr remove ────────────────────────────────────────────────────────────

    @rr_group.command(name="remove", description="Retire un bouton d'un panel")
    @app_commands.describe(panel_id="L'ID du panel", bouton_id="L'ID du bouton à retirer (voir /rr list)")
    @app_commands.default_permissions(manage_roles=True)
    async def rr_remove(self, interaction: discord.Interaction, panel_id: int, bouton_id: int):
        panel = await self.bot.db.get_rr_panel_by_id(panel_id, interaction.guild.id)
        if not panel:
            return await interaction.response.send_message(f"❌ Panel `#{panel_id}` introuvable.", ephemeral=True)

        await self.bot.db.remove_rr_button(bouton_id, panel_id)
        await self._rebuild_panel(interaction.guild, dict(panel), panel_id)

        await interaction.response.send_message(
            f"✅ Bouton `#{bouton_id}` retiré du panel `#{panel_id}`.", ephemeral=True
        )

    # ── /rr delete ────────────────────────────────────────────────────────────

    @rr_group.command(name="delete", description="Supprime un panel de rôles réactifs")
    @app_commands.describe(panel_id="L'ID du panel à supprimer")
    @app_commands.default_permissions(manage_roles=True)
    async def rr_delete(self, interaction: discord.Interaction, panel_id: int):
        panel = await self.bot.db.get_rr_panel_by_id(panel_id, interaction.guild.id)
        if not panel:
            return await interaction.response.send_message(f"❌ Panel `#{panel_id}` introuvable.", ephemeral=True)

        channel = interaction.guild.get_channel(panel["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(panel["message_id"])
                await msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        await self.bot.db.delete_rr_panel(panel_id)
        await interaction.response.send_message(f"✅ Panel `#{panel_id}` supprimé.", ephemeral=True)

    # ── /rr list ──────────────────────────────────────────────────────────────

    @rr_group.command(name="list", description="Liste tous les panels de rôles réactifs du serveur")
    @app_commands.default_permissions(manage_roles=True)
    async def rr_list(self, interaction: discord.Interaction):
        panels = await self.bot.db.get_all_rr_panels(interaction.guild.id)
        if not panels:
            return await interaction.response.send_message(
                "❌ Aucun panel de rôles réactifs sur ce serveur.", ephemeral=True
            )

        embed = discord.Embed(title="🎭 Panels de rôles réactifs", color=Colors.INFO)
        for panel in panels:
            channel = interaction.guild.get_channel(panel["channel_id"])
            buttons = await self.bot.db.get_rr_buttons(panel["id"])
            btn_info = "\n".join(
                f"  `#{b['id']}` {b['emoji'] or ''} **{b['label']}** → <@&{b['role_id']}>"
                for b in buttons
            ) or "  *Aucun bouton*"
            embed.add_field(
                name=f"#{panel['id']} — {panel['title']}",
                value=f"Salon : {channel.mention if channel else '⚠️ introuvable'}\n{btn_info}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Helper ────────────────────────────────────────────────────────────────

    async def _rebuild_panel(self, guild: discord.Guild, panel: dict, panel_id: int):
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
        embed.set_footer(text="Clique sur un bouton pour obtenir ou retirer un rôle.")

        if buttons:
            view = build_rr_view([dict(b) for b in buttons])
            self.bot.add_view(view, message_id=msg.id)
            await msg.edit(embed=embed, view=view)
        else:
            await msg.edit(embed=embed, view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
