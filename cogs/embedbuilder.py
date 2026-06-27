import discord
from discord import app_commands
from discord.ext import commands


# ── Modals ────────────────────────────────────────────────────────────────────

class TitleDescModal(discord.ui.Modal, title="Titre & Description"):
    embed_title = discord.ui.TextInput(
        label="Titre", placeholder="Le titre de l'embed", max_length=256, required=False
    )
    description = discord.ui.TextInput(
        label="Description", style=discord.TextStyle.long,
        placeholder="Le contenu principal de l'embed", max_length=4000, required=False
    )

    def __init__(self, view: "EmbedBuilderView"):
        super().__init__()
        self._view = view
        if v := view.data.get("title"):
            self.embed_title.default = v
        if v := view.data.get("description"):
            self.description.default = v

    async def on_submit(self, interaction: discord.Interaction):
        self._view.data["title"]       = self.embed_title.value.strip() or None
        self._view.data["description"] = self.description.value.strip() or None
        await self._view._refresh(interaction)


class ColorModal(discord.ui.Modal, title="Couleur de l'embed"):
    color = discord.ui.TextInput(
        label="Code hexadécimal", placeholder="Ex: FF6B35 ou #5865F2",
        max_length=7, min_length=3, required=True
    )

    def __init__(self, view: "EmbedBuilderView"):
        super().__init__()
        self._view = view
        self.color.default = f"#{view.data.get('color', 0x5865F2):06X}"

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.color.value.strip().lstrip("#")
        try:
            val = int(raw, 16)
            if not 0 <= val <= 0xFFFFFF:
                raise ValueError
            self._view.data["color"] = val
            await self._view._refresh(interaction)
        except ValueError:
            await interaction.response.send_message(
                "❌ Couleur invalide. Exemple : `FF6B35` ou `#5865F2`", ephemeral=True
            )


class ImagesModal(discord.ui.Modal, title="Images"):
    image_url = discord.ui.TextInput(
        label="Image principale (URL)", placeholder="https://...",
        max_length=500, required=False
    )
    thumbnail_url = discord.ui.TextInput(
        label="Miniature (URL)", placeholder="https://...",
        max_length=500, required=False
    )

    def __init__(self, view: "EmbedBuilderView"):
        super().__init__()
        self._view = view
        if v := view.data.get("image_url"):
            self.image_url.default = v
        if v := view.data.get("thumbnail_url"):
            self.thumbnail_url.default = v

    async def on_submit(self, interaction: discord.Interaction):
        self._view.data["image_url"]     = self.image_url.value.strip() or None
        self._view.data["thumbnail_url"] = self.thumbnail_url.value.strip() or None
        await self._view._refresh(interaction)


class AuthorFooterModal(discord.ui.Modal, title="Auteur & Footer"):
    author_name = discord.ui.TextInput(
        label="Nom de l'auteur", placeholder="Ex: Mon Bot", max_length=256, required=False
    )
    author_icon = discord.ui.TextInput(
        label="Icône de l'auteur (URL)", placeholder="https://...", max_length=500, required=False
    )
    footer_text = discord.ui.TextInput(
        label="Texte du footer", placeholder="Ex: Made by MonBot", max_length=2048, required=False
    )
    footer_icon = discord.ui.TextInput(
        label="Icône du footer (URL)", placeholder="https://...", max_length=500, required=False
    )

    def __init__(self, view: "EmbedBuilderView"):
        super().__init__()
        self._view = view
        for attr in ("author_name", "author_icon", "footer_text", "footer_icon"):
            if v := view.data.get(attr):
                getattr(self, attr).default = v

    async def on_submit(self, interaction: discord.Interaction):
        self._view.data["author_name"] = self.author_name.value.strip() or None
        self._view.data["author_icon"] = self.author_icon.value.strip() or None
        self._view.data["footer_text"] = self.footer_text.value.strip() or None
        self._view.data["footer_icon"] = self.footer_icon.value.strip() or None
        await self._view._refresh(interaction)


class AddFieldModal(discord.ui.Modal, title="Ajouter un champ"):
    name = discord.ui.TextInput(
        label="Nom du champ", placeholder="Ex: Informations", max_length=256
    )
    value = discord.ui.TextInput(
        label="Contenu", style=discord.TextStyle.long,
        placeholder="Ex: Voici les détails...", max_length=1024
    )
    inline = discord.ui.TextInput(
        label="Sur la même ligne ? (oui / non)", placeholder="non",
        max_length=3, required=False
    )

    def __init__(self, view: "EmbedBuilderView"):
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction):
        is_inline = self.inline.value.strip().lower() in ("oui", "yes", "o", "y", "true", "1")
        fields = self._view.data.setdefault("fields", [])
        fields.append({
            "name":   self.name.value.strip(),
            "value":  self.value.value.strip(),
            "inline": is_inline
        })
        await self._view._refresh(interaction)


# ── Remove-field select ───────────────────────────────────────────────────────

class RemoveFieldSelect(discord.ui.Select):
    def __init__(self, builder_view: "EmbedBuilderView"):
        self._builder = builder_view
        fields = builder_view.data.get("fields") or []
        options = [
            discord.SelectOption(
                label=f"#{i + 1} — {f['name'][:80]}",
                value=str(i)
            )
            for i, f in enumerate(fields[:25])
        ]
        super().__init__(placeholder="Sélectionne le champ à supprimer...", options=options)

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        fields = self._builder.data.get("fields") or []
        if 0 <= idx < len(fields):
            removed = fields.pop(idx)
            await self._builder.message.edit(embed=self._builder._build(), view=self._builder)
            await interaction.response.send_message(
                f"✅ Champ **{removed['name']}** supprimé.", ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ Champ introuvable.", ephemeral=True)


class RemoveFieldView(discord.ui.View):
    def __init__(self, builder_view: "EmbedBuilderView"):
        super().__init__(timeout=30)
        self.add_item(RemoveFieldSelect(builder_view))


# ── Channel select (send mode) ────────────────────────────────────────────────

class EmbedChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="📤 Envoyer dans un salon...",
            channel_types=[discord.ChannelType.text],
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        view: EmbedBuilderView = self.view
        embed = view._build()
        if not embed.title and not embed.description and not embed.fields:
            return await interaction.response.send_message("❌ L'embed est vide !", ephemeral=True)
        channel = self.values[0]
        if not channel.permissions_for(interaction.guild.me).send_messages:
            return await interaction.response.send_message(
                f"❌ Je ne peux pas envoyer dans {channel.mention}.", ephemeral=True
            )
        await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Embed envoyé dans {channel.mention} !", ephemeral=True)
        view.stop()
        if view.message:
            try:
                await view.message.delete()
            except discord.HTTPException:
                pass


# ── Save button (edit mode) ───────────────────────────────────────────────────

class EmbedSaveButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="💾 Sauvegarder les modifications",
            style=discord.ButtonStyle.success,
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        view: EmbedBuilderView = self.view
        embed = view._build()
        if not embed.title and not embed.description and not embed.fields:
            return await interaction.response.send_message("❌ L'embed est vide !", ephemeral=True)
        await view.edit_target.edit(embed=embed)
        await interaction.response.send_message("✅ Embed modifié avec succès !", ephemeral=True)
        view.stop()
        if view.message:
            try:
                await view.message.delete()
            except discord.HTTPException:
                pass


# ── Main builder view ─────────────────────────────────────────────────────────

def _default_data() -> dict:
    return {
        "title": None, "description": None, "color": 0x5865F2,
        "image_url": None, "thumbnail_url": None,
        "author_name": None, "author_icon": None,
        "footer_text": None, "footer_icon": None,
        "fields": []
    }


class EmbedBuilderView(discord.ui.View):
    def __init__(self, data: dict = None, edit_target: discord.Message = None):
        super().__init__(timeout=300)
        self.data        = data or _default_data()
        self.edit_target = edit_target
        self.message: discord.Message = None

        if edit_target is None:
            self.add_item(EmbedChannelSelect())
        else:
            self.add_item(EmbedSaveButton())

    def _build(self) -> discord.Embed:
        embed = discord.Embed(color=discord.Color(self.data.get("color") or 0x5865F2))
        if t := self.data.get("title"):
            embed.title = t
        if d := self.data.get("description"):
            embed.description = d
        if u := self.data.get("image_url"):
            try:
                embed.set_image(url=u)
            except Exception:
                pass
        if u := self.data.get("thumbnail_url"):
            try:
                embed.set_thumbnail(url=u)
            except Exception:
                pass
        if n := self.data.get("author_name"):
            kw: dict = {"name": n}
            if i := self.data.get("author_icon"):
                kw["icon_url"] = i
            embed.set_author(**kw)
        if t := self.data.get("footer_text"):
            kw = {"text": t}
            if i := self.data.get("footer_icon"):
                kw["icon_url"] = i
            embed.set_footer(**kw)
        for f in self.data.get("fields") or []:
            embed.add_field(name=f["name"], value=f["value"], inline=f.get("inline", False))
        return embed

    def _preview_embed(self) -> discord.Embed:
        embed = self._build()
        if not embed.title and not embed.description and not embed.fields and not embed.image and not embed.thumbnail:
            embed.description = (
                "*L'embed est vide pour l'instant.*\n"
                "Utilise les boutons ci-dessous pour le construire."
            )
        return embed

    async def _refresh(self, interaction: discord.Interaction):
        """Called after a modal submit to update the preview."""
        if self.message:
            await self.message.edit(embed=self._preview_embed(), view=self)
        await interaction.response.defer()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                embed = self._preview_embed()
                embed.set_footer(text="⌛ Session expirée (5 min).")
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass

    # ── Row 0 — Content ───────────────────────────────────────────────────────

    @discord.ui.button(label="✏️ Titre & Description", style=discord.ButtonStyle.secondary, row=0)
    async def btn_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TitleDescModal(self))

    @discord.ui.button(label="🎨 Couleur", style=discord.ButtonStyle.secondary, row=0)
    async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self))

    @discord.ui.button(label="🖼️ Images", style=discord.ButtonStyle.secondary, row=0)
    async def btn_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagesModal(self))

    @discord.ui.button(label="🔻 Auteur & Footer", style=discord.ButtonStyle.secondary, row=0)
    async def btn_author(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuthorFooterModal(self))

    # ── Row 1 — Fields & Utils ────────────────────────────────────────────────

    @discord.ui.button(label="➕ Ajouter un champ", style=discord.ButtonStyle.secondary, row=1)
    async def btn_add_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.data.get("fields") or []) >= 25:
            return await interaction.response.send_message("❌ Maximum 25 champs.", ephemeral=True)
        await interaction.response.send_modal(AddFieldModal(self))

    @discord.ui.button(label="🗑️ Supprimer un champ", style=discord.ButtonStyle.secondary, row=1)
    async def btn_remove_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        fields = self.data.get("fields") or []
        if not fields:
            return await interaction.response.send_message("❌ Aucun champ à supprimer.", ephemeral=True)
        await interaction.response.send_message(
            "Quel champ supprimer ?", view=RemoveFieldView(self), ephemeral=True
        )

    @discord.ui.button(label="🔄 Reset", style=discord.ButtonStyle.danger, row=1)
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.data.clear()
        self.data.update(_default_data())
        await self._refresh(interaction)

    @discord.ui.button(label="❌ Fermer", style=discord.ButtonStyle.danger, row=1)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer()
        if self.message:
            try:
                await self.message.delete()
            except discord.HTTPException:
                pass


# ── Cog ───────────────────────────────────────────────────────────────────────

class EmbedBuilder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    embed_group = app_commands.Group(name="embed", description="Constructeur d'embeds personnalisés")

    @embed_group.command(name="create", description="Ouvre le constructeur d'embed interactif")
    @app_commands.default_permissions(manage_messages=True)
    async def embed_create(self, interaction: discord.Interaction):
        view  = EmbedBuilderView()
        await interaction.response.send_message(embed=view._preview_embed(), view=view)
        view.message = await interaction.original_response()

    @embed_group.command(name="edit", description="Édite un embed existant envoyé par le bot")
    @app_commands.describe(
        message_id="L'ID du message à modifier",
        salon="Le salon contenant le message (salon actuel si non précisé)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def embed_edit(
        self, interaction: discord.Interaction,
        message_id: str, salon: discord.TextChannel = None
    ):
        channel = salon or interaction.channel
        try:
            msg = await channel.fetch_message(int(message_id))
        except (ValueError, discord.NotFound):
            return await interaction.response.send_message(
                "❌ Message introuvable. Vérifie l'ID et le salon.", ephemeral=True
            )
        if msg.author != interaction.guild.me:
            return await interaction.response.send_message(
                "❌ Je ne peux éditer que les messages envoyés par le bot.", ephemeral=True
            )
        if not msg.embeds:
            return await interaction.response.send_message(
                "❌ Ce message ne contient pas d'embed.", ephemeral=True
            )

        # Charge l'embed existant dans le builder
        ex = msg.embeds[0]
        data = {
            "title":         ex.title,
            "description":   ex.description,
            "color":         ex.color.value if ex.color else 0x5865F2,
            "image_url":     ex.image.url        if ex.image        else None,
            "thumbnail_url": ex.thumbnail.url    if ex.thumbnail    else None,
            "author_name":   ex.author.name      if ex.author       else None,
            "author_icon":   ex.author.icon_url  if ex.author       else None,
            "footer_text":   ex.footer.text      if ex.footer       else None,
            "footer_icon":   ex.footer.icon_url  if ex.footer       else None,
            "fields":        [
                {"name": f.name, "value": f.value, "inline": f.inline}
                for f in ex.fields
            ]
        }

        view = EmbedBuilderView(data=data, edit_target=msg)
        await interaction.response.send_message(
            embed=view._preview_embed(), view=view
        )
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedBuilder(bot))
