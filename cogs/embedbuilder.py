import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.embeds import error_embed, success_embed

VALID_STYLES = {"primary", "secondary", "success", "danger"}
STYLE_MAP = {
    "primary":   discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success":   discord.ButtonStyle.success,
    "danger":    discord.ButtonStyle.danger,
}


# ══════════════════════════════════════════════════════════════════════════════
#  Persistent custom button (role / message / link)
# ══════════════════════════════════════════════════════════════════════════════

class EmbedCustomButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot, data: dict):
        self.bot  = bot
        self.data = data
        is_link   = data["action_type"] == "link"
        style     = discord.ButtonStyle.link if is_link else STYLE_MAP.get(data["style"], discord.ButtonStyle.secondary)
        emoji     = data.get("emoji") or None

        kwargs: dict = {"label": data["label"], "style": style}
        if emoji:
            kwargs["emoji"] = emoji
        if is_link:
            kwargs["url"] = data["action_data"]
        else:
            kwargs["custom_id"] = f"emb_{data['id']}"

        super().__init__(**kwargs)

    async def callback(self, interaction: discord.Interaction):
        if self.data["action_type"] == "role":
            role = interaction.guild.get_role(int(self.data["action_data"]))
            if not role:
                return await interaction.response.send_message(embed=error_embed("❌ Ce rôle n'existe plus."), ephemeral=True)
            if role >= interaction.guild.me.top_role:
                return await interaction.response.send_message(embed=error_embed("❌ Je ne peux pas gérer ce rôle."), ephemeral=True)
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Bouton embed")
                await interaction.response.send_message(embed=error_embed(f"❌ Rôle **{role.name}** retiré."), ephemeral=True)
            else:
                await interaction.user.add_roles(role, reason="Bouton embed")
                await interaction.response.send_message(embed=success_embed(f"✅ Rôle **{role.name}** obtenu !"), ephemeral=True)

        elif self.data["action_type"] == "message":
            await interaction.response.send_message(
                self.data["action_data"],
                ephemeral=bool(self.data.get("ephemeral", True))
            )


def build_custom_view(bot: commands.Bot, buttons_data: list) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for btn in buttons_data:
        view.add_item(EmbedCustomButton(bot, dict(btn)))
    return view


# ══════════════════════════════════════════════════════════════════════════════
#  Embed builder — modals
# ══════════════════════════════════════════════════════════════════════════════

class TitleDescModal(discord.ui.Modal, title="Titre & Description"):
    embed_title = discord.ui.TextInput(label="Titre", max_length=256, required=False)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.long, max_length=4000, required=False)

    def __init__(self, v: "EmbedBuilderView"):
        super().__init__()
        self._v = v
        if t := v.data.get("title"):       self.embed_title.default = t
        if d := v.data.get("description"): self.description.default = d

    async def on_submit(self, interaction: discord.Interaction):
        self._v.data["title"]       = self.embed_title.value.strip() or None
        self._v.data["description"] = self.description.value.strip() or None
        await self._v._refresh(interaction)


class ColorModal(discord.ui.Modal, title="Couleur"):
    color = discord.ui.TextInput(label="Code hexadécimal", placeholder="Ex: FF6B35 ou #5865F2", max_length=7)

    def __init__(self, v: "EmbedBuilderView"):
        super().__init__()
        self._v = v
        self.color.default = f"#{v.data.get('color', Colors.INFO.value):06X}"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.color.value.strip().lstrip("#"), 16)
            if not 0 <= val <= 0xFFFFFF: raise ValueError
            self._v.data["color"] = val
            await self._v._refresh(interaction)
        except ValueError:
            await interaction.response.send_message(embed=error_embed("❌ Couleur invalide. Ex : `FF6B35`"), ephemeral=True)


class ImagesModal(discord.ui.Modal, title="Images"):
    image_url     = discord.ui.TextInput(label="Image principale (URL)", max_length=500, required=False)
    thumbnail_url = discord.ui.TextInput(label="Miniature (URL)",        max_length=500, required=False)

    def __init__(self, v: "EmbedBuilderView"):
        super().__init__()
        self._v = v
        if u := v.data.get("image_url"):     self.image_url.default     = u
        if u := v.data.get("thumbnail_url"): self.thumbnail_url.default = u

    async def on_submit(self, interaction: discord.Interaction):
        self._v.data["image_url"]     = self.image_url.value.strip() or None
        self._v.data["thumbnail_url"] = self.thumbnail_url.value.strip() or None
        await self._v._refresh(interaction)


class AuthorFooterModal(discord.ui.Modal, title="Auteur & Footer"):
    author_name = discord.ui.TextInput(label="Nom de l'auteur",          max_length=256,  required=False)
    author_icon = discord.ui.TextInput(label="Icône auteur (URL)",        max_length=500,  required=False)
    footer_text = discord.ui.TextInput(label="Texte du footer",          max_length=2048, required=False)
    footer_icon = discord.ui.TextInput(label="Icône footer (URL)",        max_length=500,  required=False)

    def __init__(self, v: "EmbedBuilderView"):
        super().__init__()
        self._v = v
        for a in ("author_name", "author_icon", "footer_text", "footer_icon"):
            if val := v.data.get(a): getattr(self, a).default = val

    async def on_submit(self, interaction: discord.Interaction):
        for a in ("author_name", "author_icon", "footer_text", "footer_icon"):
            self._v.data[a] = getattr(self, a).value.strip() or None
        await self._v._refresh(interaction)


class AddFieldModal(discord.ui.Modal, title="Ajouter un champ"):
    name   = discord.ui.TextInput(label="Nom du champ", max_length=256)
    value  = discord.ui.TextInput(label="Contenu", style=discord.TextStyle.long, max_length=1024)
    inline = discord.ui.TextInput(label="Sur la même ligne ? (oui/non)", placeholder="non", max_length=3, required=False)

    def __init__(self, v: "EmbedBuilderView"):
        super().__init__()
        self._v = v

    async def on_submit(self, interaction: discord.Interaction):
        is_inline = self.inline.value.strip().lower() in ("oui", "yes", "o", "y", "1")
        self._v.data.setdefault("fields", []).append({
            "name": self.name.value.strip(), "value": self.value.value.strip(), "inline": is_inline
        })
        await self._v._refresh(interaction)


# ══════════════════════════════════════════════════════════════════════════════
#  Button manager — modals & selects
# ══════════════════════════════════════════════════════════════════════════════

class AddLinkButtonModal(discord.ui.Modal, title="Bouton — Lien"):
    btn_label = discord.ui.TextInput(label="Texte du bouton", max_length=80)
    url       = discord.ui.TextInput(label="URL", placeholder="https://...")
    emoji     = discord.ui.TextInput(label="Emoji (optionnel)", required=False, max_length=50)

    def __init__(self, v: "EmbedBuilderView"):
        super().__init__()
        self._v = v

    async def on_submit(self, interaction: discord.Interaction):
        btns = self._v.data.setdefault("buttons", [])
        if len(btns) >= 25:
            return await interaction.response.send_message(embed=error_embed("❌ Maximum 25 boutons."), ephemeral=True)
        btns.append({"label": self.btn_label.value.strip(), "style": "link",
                     "emoji": self.emoji.value.strip() or None,
                     "action_type": "link", "action_data": self.url.value.strip(), "ephemeral": False})
        await self._v.message.edit(embed=self._v._preview(), view=self._v)
        await interaction.response.send_message(
            f"✅ Bouton lien **{self.btn_label.value}** ajouté ({len(btns)}/25).", ephemeral=True
        )


class RoleButtonConfigModal(discord.ui.Modal, title="Bouton — Rôle"):
    btn_label = discord.ui.TextInput(label="Texte du bouton", max_length=80)
    emoji     = discord.ui.TextInput(label="Emoji (optionnel)", required=False, max_length=50)
    couleur   = discord.ui.TextInput(label="Couleur : primary / secondary / success / danger",
                                     placeholder="secondary", max_length=10, required=False)

    def __init__(self, v: "EmbedBuilderView", role: discord.Role):
        super().__init__()
        self._v    = v
        self._role = role

    async def on_submit(self, interaction: discord.Interaction):
        style = self.couleur.value.strip().lower() or "secondary"
        if style not in VALID_STYLES: style = "secondary"
        btns = self._v.data.setdefault("buttons", [])
        if len(btns) >= 25:
            return await interaction.response.send_message(embed=error_embed("❌ Maximum 25 boutons."), ephemeral=True)
        btns.append({"label": self.btn_label.value.strip(), "style": style,
                     "emoji": self.emoji.value.strip() or None,
                     "action_type": "role", "action_data": str(self._role.id), "ephemeral": True})
        await self._v.message.edit(embed=self._v._preview(), view=self._v)
        await interaction.response.send_message(
            f"✅ Bouton rôle **{self.btn_label.value}** → {self._role.mention} ajouté ({len(btns)}/25).",
            ephemeral=True
        )


class RoleSelectForButton(discord.ui.RoleSelect):
    def __init__(self, v: "EmbedBuilderView"):
        super().__init__(placeholder="Choisis le rôle à attribuer...")
        self._v = v

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RoleButtonConfigModal(self._v, self.values[0]))


class AddMessageButtonModal(discord.ui.Modal, title="Bouton — Message"):
    btn_label = discord.ui.TextInput(label="Texte du bouton", max_length=80)
    message   = discord.ui.TextInput(label="Message envoyé au clic", style=discord.TextStyle.long, max_length=2000)
    ephemeral = discord.ui.TextInput(label="Message privé ? (oui/non)", placeholder="oui", max_length=3, required=False)
    emoji     = discord.ui.TextInput(label="Emoji (optionnel)", required=False, max_length=50)
    couleur   = discord.ui.TextInput(label="Couleur : primary / secondary / success / danger",
                                     placeholder="primary", max_length=10, required=False)

    def __init__(self, v: "EmbedBuilderView"):
        super().__init__()
        self._v = v

    async def on_submit(self, interaction: discord.Interaction):
        is_eph = self.ephemeral.value.strip().lower() not in ("non", "no", "n", "0", "false")
        style  = self.couleur.value.strip().lower() or "primary"
        if style not in VALID_STYLES: style = "primary"
        btns = self._v.data.setdefault("buttons", [])
        if len(btns) >= 25:
            return await interaction.response.send_message(embed=error_embed("❌ Maximum 25 boutons."), ephemeral=True)
        btns.append({"label": self.btn_label.value.strip(), "style": style,
                     "emoji": self.emoji.value.strip() or None,
                     "action_type": "message", "action_data": self.message.value.strip(), "ephemeral": is_eph})
        await self._v.message.edit(embed=self._v._preview(), view=self._v)
        await interaction.response.send_message(
            f"✅ Bouton message **{self.btn_label.value}** ajouté ({'privé' if is_eph else 'public'}, {len(btns)}/25).",
            ephemeral=True
        )


class RemoveButtonSelect(discord.ui.Select):
    def __init__(self, v: "EmbedBuilderView"):
        self._v = v
        btns    = v.data.get("buttons") or []
        icons   = {"link": "🔗", "role": "🎭", "message": "💬"}
        options = [
            discord.SelectOption(label=f"#{i+1} {icons.get(b['action_type'],'🔘')} {b['label'][:60]}", value=str(i))
            for i, b in enumerate(btns[:25])
        ]
        super().__init__(placeholder="Sélectionne le bouton à supprimer...", options=options)

    async def callback(self, interaction: discord.Interaction):
        idx  = int(self.values[0])
        btns = self._v.data.get("buttons") or []
        if 0 <= idx < len(btns):
            removed = btns.pop(idx)
            await self._v.message.edit(embed=self._v._preview(), view=self._v)
            await interaction.response.send_message(embed=success_embed(f"✅ Bouton **{removed['label']}** supprimé."), ephemeral=True)


class ButtonManagerView(discord.ui.View):
    def __init__(self, v: "EmbedBuilderView"):
        super().__init__(timeout=60)
        self._v = v

    @discord.ui.button(label="🔗 Lien",    style=discord.ButtonStyle.secondary)
    async def add_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddLinkButtonModal(self._v))

    @discord.ui.button(label="🎭 Rôle",    style=discord.ButtonStyle.secondary)
    async def add_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View(timeout=30)
        view.add_item(RoleSelectForButton(self._v))
        await interaction.response.send_message("Sélectionne le rôle :", view=view, ephemeral=True)

    @discord.ui.button(label="💬 Message", style=discord.ButtonStyle.secondary)
    async def add_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddMessageButtonModal(self._v))

    @discord.ui.button(label="🗑️ Supprimer", style=discord.ButtonStyle.danger)
    async def remove_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        btns = self._v.data.get("buttons") or []
        if not btns:
            return await interaction.response.send_message(embed=error_embed("❌ Aucun bouton à supprimer."), ephemeral=True)
        view = discord.ui.View(timeout=30)
        view.add_item(RemoveButtonSelect(self._v))
        await interaction.response.send_message("Sélectionne le bouton :", view=view, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Field remove select
# ══════════════════════════════════════════════════════════════════════════════

class RemoveFieldSelect(discord.ui.Select):
    def __init__(self, v: "EmbedBuilderView"):
        self._v    = v
        fields     = v.data.get("fields") or []
        options    = [
            discord.SelectOption(label=f"#{i+1} — {f['name'][:80]}", value=str(i))
            for i, f in enumerate(fields[:25])
        ]
        super().__init__(placeholder="Sélectionne le champ à supprimer...", options=options)

    async def callback(self, interaction: discord.Interaction):
        idx    = int(self.values[0])
        fields = self._v.data.get("fields") or []
        if 0 <= idx < len(fields):
            removed = fields.pop(idx)
            await self._v.message.edit(embed=self._v._preview(), view=self._v)
            await interaction.response.send_message(embed=success_embed(f"✅ Champ **{removed['name']}** supprimé."), ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Channel select / Save button (dynamically added)
# ══════════════════════════════════════════════════════════════════════════════

class EmbedChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📤 Envoyer dans un salon...",
                         channel_types=[discord.ChannelType.text], row=2)

    async def callback(self, interaction: discord.Interaction):
        v: EmbedBuilderView = self.view
        embed   = v._build()
        channel = self.values[0]

        if not embed.title and not embed.description and not embed.fields:
            return await interaction.response.send_message(embed=error_embed("❌ L'embed est vide !"), ephemeral=True)
        if not channel.permissions_for(interaction.guild.me).send_messages:
            return await interaction.response.send_message(
                f"❌ Je ne peux pas envoyer dans {channel.mention}.", ephemeral=True
            )

        sent = await channel.send(embed=embed)
        await interaction.response.send_message(embed=success_embed(f"✅ Embed envoyé dans {channel.mention} !"), ephemeral=True)

        await _persist_buttons(interaction.client, interaction.guild.id, channel.id, sent, v.data.get("buttons") or [])

        v.stop()
        if v.message:
            try: await v.message.delete()
            except discord.HTTPException: pass


class EmbedSaveButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="💾 Sauvegarder", style=discord.ButtonStyle.success, row=2)

    async def callback(self, interaction: discord.Interaction):
        v: EmbedBuilderView = self.view
        embed = v._build()

        if not embed.title and not embed.description and not embed.fields:
            return await interaction.response.send_message(embed=error_embed("❌ L'embed est vide !"), ephemeral=True)

        # Save new buttons (delete old ones first)
        await interaction.client.db.delete_embed_buttons_for_message(v.edit_target.id)
        await _persist_buttons(
            interaction.client,
            interaction.guild.id,
            v.edit_target.channel.id,
            v.edit_target,
            v.data.get("buttons") or [],
            existing_message=True
        )
        # Edit the target message embed (view is rebuilt inside _persist_buttons)
        await v.edit_target.edit(embed=embed)
        await interaction.response.send_message(embed=success_embed("✅ Embed modifié avec succès !"), ephemeral=True)

        v.stop()
        if v.message:
            try: await v.message.delete()
            except discord.HTTPException: pass


async def _persist_buttons(
    bot: commands.Bot, guild_id: int, channel_id: int,
    message: discord.Message, buttons: list, existing_message: bool = False
):
    """Saves buttons to DB and registers the persistent view."""
    if not buttons:
        return
    db = bot.db
    saved = []
    for i, btn in enumerate(buttons):
        bid = await db.save_embed_button(
            guild_id, channel_id, message.id,
            btn["label"], btn["style"], btn.get("emoji"),
            btn["action_type"], btn["action_data"],
            btn.get("ephemeral", True), i
        )
        saved.append({**btn, "id": bid})

    view = build_custom_view(bot, saved)
    bot.add_view(view, message_id=message.id)
    await message.edit(view=view)


# ══════════════════════════════════════════════════════════════════════════════
#  Main builder view
# ══════════════════════════════════════════════════════════════════════════════

def _default_data() -> dict:
    return {"title": None, "description": None, "color": Colors.INFO.value,
            "image_url": None, "thumbnail_url": None,
            "author_name": None, "author_icon": None,
            "footer_text": None, "footer_icon": None,
            "fields": [], "buttons": []}


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

    # ── Build embed from data ─────────────────────────────────────────────────

    def _build(self) -> discord.Embed:
        embed = discord.Embed(color=discord.Color(self.data.get("color") or Colors.INFO.value))
        if t := self.data.get("title"):       embed.title       = t
        if d := self.data.get("description"): embed.description = d
        if u := self.data.get("image_url"):
            try: embed.set_image(url=u)
            except Exception: pass
        if u := self.data.get("thumbnail_url"):
            try: embed.set_thumbnail(url=u)
            except Exception: pass
        if n := self.data.get("author_name"):
            kw = {"name": n}
            if i := self.data.get("author_icon"): kw["icon_url"] = i
            embed.set_author(**kw)
        if t := self.data.get("footer_text"):
            kw = {"text": t}
            if i := self.data.get("footer_icon"): kw["icon_url"] = i
            embed.set_footer(**kw)
        for f in self.data.get("fields") or []:
            embed.add_field(name=f["name"], value=f["value"], inline=f.get("inline", False))
        return embed

    def _preview(self) -> discord.Embed:
        embed = self._build()
        if not (embed.title or embed.description or embed.fields or embed.image or embed.thumbnail):
            embed.description = "*Utilise les boutons ci-dessous pour construire ton embed.*"
        btns = self.data.get("buttons") or []
        if btns:
            icons = {"link": "🔗", "role": "🎭", "message": "💬"}
            lines = "\n".join(
                f"{icons.get(b['action_type'],'🔘')} **{b['label']}** — `{b['action_type']}`"
                for b in btns
            )
            embed.add_field(name=f"🔘 Boutons ({len(btns)}/25) — aperçu seulement", value=lines, inline=False)
        return embed

    async def _refresh(self, interaction: discord.Interaction):
        if self.message:
            await self.message.edit(embed=self._preview(), view=self)
        await interaction.response.defer()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                e = self._preview()
                e.set_footer(text="⌛ Session expirée (5 min).")
                await self.message.edit(embed=e, view=self)
            except discord.HTTPException:
                pass

    # ── Row 0 — Contenu ───────────────────────────────────────────────────────

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

    # ── Row 1 — Champs & Boutons ──────────────────────────────────────────────

    @discord.ui.button(label="➕ Champ", style=discord.ButtonStyle.secondary, row=1)
    async def btn_add_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.data.get("fields") or []) >= 25:
            return await interaction.response.send_message(embed=error_embed("❌ Maximum 25 champs."), ephemeral=True)
        await interaction.response.send_modal(AddFieldModal(self))

    @discord.ui.button(label="🗑️ Champ", style=discord.ButtonStyle.secondary, row=1)
    async def btn_remove_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (self.data.get("fields") or []):
            return await interaction.response.send_message(embed=error_embed("❌ Aucun champ à supprimer."), ephemeral=True)
        view = discord.ui.View(timeout=30)
        view.add_item(RemoveFieldSelect(self))
        await interaction.response.send_message("Quel champ supprimer ?", view=view, ephemeral=True)

    @discord.ui.button(label="🔘 Boutons", style=discord.ButtonStyle.primary, row=1)
    async def btn_buttons(self, interaction: discord.Interaction, button: discord.ui.Button):
        btns  = self.data.get("buttons") or []
        icons = {"link": "🔗", "role": "🎭", "message": "💬"}
        embed = discord.Embed(title="🔘 Gérer les boutons", color=Colors.INFO)
        if btns:
            embed.description = "\n".join(
                f"`#{i+1}` {icons.get(b['action_type'],'🔘')} **{b['label']}** — `{b['action_type']}`"
                for i, b in enumerate(btns)
            )
        else:
            embed.description = "*Aucun bouton ajouté pour l'instant.*"
        embed.set_footer(text=f"{len(btns)}/25 boutons | Types : 🔗 Lien  🎭 Rôle  💬 Message")
        await interaction.response.send_message(embed=embed, view=ButtonManagerView(self), ephemeral=True)

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
            try: await self.message.delete()
            except discord.HTTPException: pass


# ══════════════════════════════════════════════════════════════════════════════
#  Cog
# ══════════════════════════════════════════════════════════════════════════════

class EmbedBuilder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        rows = await self.bot.db.get_all_embed_button_message_ids()
        for row in rows:
            btns = await self.bot.db.get_embed_buttons(row["message_id"])
            if btns:
                view = build_custom_view(self.bot, [dict(b) for b in btns])
                self.bot.add_view(view, message_id=row["message_id"])

    embed_group = app_commands.Group(name="embed", description="Constructeur d'embeds avec boutons")

    @embed_group.command(name="create", description="Ouvre le constructeur d'embed interactif")
    @app_commands.default_permissions(manage_messages=True)
    async def embed_create(self, interaction: discord.Interaction):
        view = EmbedBuilderView()
        await interaction.response.send_message(embed=view._preview(), view=view)
        view.message = await interaction.original_response()

    @embed_group.command(name="edit", description="Édite un embed existant envoyé par le bot")
    @app_commands.describe(
        message_id="L'ID du message à modifier",
        salon="Le salon contenant le message (salon actuel si vide)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def embed_edit(self, interaction: discord.Interaction, message_id: str, salon: discord.TextChannel = None):
        channel = salon or interaction.channel
        try:
            msg = await channel.fetch_message(int(message_id))
        except (ValueError, discord.NotFound):
            return await interaction.response.send_message(embed=error_embed("❌ Message introuvable."), ephemeral=True)
        if msg.author != interaction.guild.me:
            return await interaction.response.send_message(embed=error_embed("❌ Ce message n'est pas envoyé par le bot."), ephemeral=True)
        if not msg.embeds:
            return await interaction.response.send_message(embed=error_embed("❌ Ce message ne contient pas d'embed."), ephemeral=True)

        ex   = msg.embeds[0]
        data = {
            "title":         ex.title,
            "description":   ex.description,
            "color":         ex.color.value if ex.color else Colors.INFO.value,
            "image_url":     ex.image.url       if ex.image     else None,
            "thumbnail_url": ex.thumbnail.url   if ex.thumbnail else None,
            "author_name":   ex.author.name     if ex.author    else None,
            "author_icon":   ex.author.icon_url if ex.author    else None,
            "footer_text":   ex.footer.text     if ex.footer    else None,
            "footer_icon":   ex.footer.icon_url if ex.footer    else None,
            "fields":        [{"name": f.name, "value": f.value, "inline": f.inline} for f in ex.fields],
            "buttons":       [dict(b) for b in await self.bot.db.get_embed_buttons(msg.id)],
        }

        view = EmbedBuilderView(data=data, edit_target=msg)
        await interaction.response.send_message(embed=view._preview(), view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedBuilder(bot))
