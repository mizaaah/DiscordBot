import discord
import json
from discord import app_commands
from discord.ext import commands


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _control_embed(channel: discord.VoiceChannel, owner: discord.Member | None, row: dict) -> discord.Embed:
    locked  = bool(row.get("locked", 0))
    hidden  = bool(row.get("hidden", 0))
    allowed = json.loads(row.get("allowed_users") or "[]")
    members = len(channel.members)
    limit   = channel.user_limit

    embed = discord.Embed(
        title=f"🎙️ {channel.name}",
        description="Gère ton salon vocal avec les boutons ci-dessous.",
        color=discord.Color.red() if (locked or hidden) else discord.Color.green()
    )
    embed.add_field(name="👑 Propriétaire", value=owner.mention if owner else "❓", inline=True)
    embed.add_field(name="👥 Membres", value=f"{members}/{limit}" if limit else str(members), inline=True)
    embed.add_field(
        name="Statut",
        value=f"{'🔒 Verrouillé' if locked else '🔓 Ouvert'} • {'🙈 Caché' if hidden else '👁️ Visible'}",
        inline=False
    )
    if allowed:
        embed.add_field(
            name=f"✅ Autorisés ({len(allowed)})",
            value=" ".join(f"<@{uid}>" for uid in allowed[:15]),
            inline=False
        )
    embed.set_footer(text="Seul le propriétaire peut modifier ce salon.")
    return embed


async def _get_row_and_channel(interaction: discord.Interaction):
    row = await interaction.client.db.get_tempvoice_by_msg(interaction.message.id)
    if not row:
        await interaction.response.send_message("❌ Salon introuvable en base.", ephemeral=True)
        return None, None
    channel = interaction.guild.get_channel(row["channel_id"])
    if not channel:
        await interaction.client.db.delete_tempvoice_channel(row["channel_id"])
        await interaction.response.send_message("❌ Le salon vocal a déjà été supprimé.", ephemeral=True)
        return None, None
    return row, channel


async def _owner_only(interaction: discord.Interaction, row: dict) -> bool:
    if interaction.user.id != row["owner_id"]:
        await interaction.response.send_message("❌ Seul le propriétaire peut faire ça.", ephemeral=True)
        return False
    return True


async def _update_control_msg(bot: commands.Bot, guild: discord.Guild, row: dict, embed: discord.Embed):
    if not row or not row.get("control_msg_id"):
        return
    config  = await bot.db.get_tempvoice_config(guild.id)
    ctrl_ch = guild.get_channel(config.get("control_channel_id") or 0)
    if not ctrl_ch:
        return
    try:
        msg = await ctrl_ch.fetch_message(row["control_msg_id"])
        await msg.edit(embed=embed)
    except (discord.NotFound, discord.Forbidden):
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Modals
# ══════════════════════════════════════════════════════════════════════════════

class RenameModal(discord.ui.Modal, title="✏️ Renommer le salon"):
    new_name = discord.ui.TextInput(label="Nouveau nom", max_length=100, min_length=1)

    def __init__(self, channel_id: int, bot: commands.Bot):
        super().__init__()
        self.channel_id = channel_id
        self.bot        = bot

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Salon introuvable.", ephemeral=True)
        await channel.edit(name=self.new_name.value.strip(), reason="TempVoice: renommé")
        row   = await self.bot.db.get_tempvoice_channel(self.channel_id)
        owner = interaction.guild.get_member(row["owner_id"]) if row else None
        await _update_control_msg(self.bot, interaction.guild, row, _control_embed(channel, owner, row or {}))
        await interaction.response.send_message(f"✅ Salon renommé en **{self.new_name.value}** !", ephemeral=True)


class LimitModal(discord.ui.Modal, title="👥 Limite de membres"):
    limit = discord.ui.TextInput(label="Limite (0 = illimité)", max_length=2, placeholder="0–99")

    def __init__(self, channel_id: int, bot: commands.Bot):
        super().__init__()
        self.channel_id = channel_id
        self.bot        = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.limit.value.strip())
            if not 0 <= val <= 99:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Valeur invalide (0–99).", ephemeral=True)
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Salon introuvable.", ephemeral=True)
        await channel.edit(user_limit=val, reason="TempVoice: limite modifiée")
        row   = await self.bot.db.get_tempvoice_channel(self.channel_id)
        owner = interaction.guild.get_member(row["owner_id"]) if row else None
        await _update_control_msg(self.bot, interaction.guild, row, _control_embed(channel, owner, row or {}))
        lim_str = f"**{val}** membres" if val else "illimitée"
        await interaction.response.send_message(f"✅ Limite définie à {lim_str}.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  UserSelect components
# ══════════════════════════════════════════════════════════════════════════════

class AllowUserSelect(discord.ui.UserSelect):
    def __init__(self, channel_id: int):
        super().__init__(placeholder="Utilisateur à autoriser...", min_values=1, max_values=1)
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        user    = self.values[0]
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Salon introuvable.", ephemeral=True)
        await channel.set_permissions(user, connect=True, view_channel=True, reason="TempVoice: autorisé")
        row = await interaction.client.db.get_tempvoice_channel(self.channel_id)
        if row:
            allowed = json.loads(row.get("allowed_users") or "[]")
            if user.id not in allowed:
                allowed.append(user.id)
                await interaction.client.db.update_tempvoice_allowed(self.channel_id, allowed)
                row["allowed_users"] = json.dumps(allowed)
            owner = interaction.guild.get_member(row["owner_id"])
            await _update_control_msg(interaction.client, interaction.guild, row, _control_embed(channel, owner, row))
        await interaction.response.send_message(f"✅ {user.mention} peut maintenant rejoindre.", ephemeral=True)


class KickUserSelect(discord.ui.UserSelect):
    def __init__(self, channel_id: int):
        super().__init__(placeholder="Utilisateur à expulser...", min_values=1, max_values=1)
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        user    = self.values[0]
        channel = interaction.guild.get_channel(self.channel_id)
        member  = interaction.guild.get_member(user.id)
        if not member or not member.voice or member.voice.channel != channel:
            return await interaction.response.send_message(f"❌ {user.mention} n'est pas dans le salon.", ephemeral=True)
        if user.id == interaction.user.id:
            return await interaction.response.send_message("❌ Tu ne peux pas t'expulser toi-même.", ephemeral=True)
        await member.move_to(None, reason="TempVoice: expulsé par le propriétaire")
        await interaction.response.send_message(f"✅ {user.mention} a été expulsé du salon.", ephemeral=True)


class TransferUserSelect(discord.ui.UserSelect):
    def __init__(self, channel_id: int):
        super().__init__(placeholder="Nouveau propriétaire...", min_values=1, max_values=1)
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        new_owner = self.values[0]
        if new_owner.bot:
            return await interaction.response.send_message("❌ Tu ne peux pas transférer à un bot.", ephemeral=True)
        if new_owner.id == interaction.user.id:
            return await interaction.response.send_message("❌ Tu es déjà propriétaire.", ephemeral=True)
        await interaction.client.db.update_tempvoice_owner(self.channel_id, new_owner.id)
        row     = await interaction.client.db.get_tempvoice_channel(self.channel_id)
        channel = interaction.guild.get_channel(self.channel_id)
        if row and channel:
            updated = {**row, "owner_id": new_owner.id}
            await _update_control_msg(interaction.client, interaction.guild, updated,
                                      _control_embed(channel, new_owner, updated))
        await interaction.response.send_message(f"✅ Propriété transférée à {new_owner.mention}.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Persistent control view
# ══════════════════════════════════════════════════════════════════════════════

class TempVoiceControlView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    # ── Row 0 : Lock | Masquer | Privé ────────────────────────────────────────

    @discord.ui.button(label="🔒 Lock", style=discord.ButtonStyle.secondary, custom_id="tv_lock", row=0)
    async def btn_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        row, channel = await _get_row_and_channel(interaction)
        if not row: return
        if not await _owner_only(interaction, row): return

        new_val = not bool(row["locked"])
        ow = channel.overwrites_for(interaction.guild.default_role)
        ow.connect = False if new_val else None
        await channel.set_permissions(interaction.guild.default_role,
                                      overwrite=ow if not ow.is_empty() else None)
        if new_val:
            for uid in json.loads(row.get("allowed_users") or "[]"):
                if m := interaction.guild.get_member(uid):
                    await channel.set_permissions(m, connect=True)

        await interaction.client.db.update_tempvoice_state(row["channel_id"], locked=int(new_val))
        row["locked"] = int(new_val)
        owner = interaction.guild.get_member(row["owner_id"])
        await interaction.response.edit_message(embed=_control_embed(channel, owner, row))

    @discord.ui.button(label="👁️ Masquer", style=discord.ButtonStyle.secondary, custom_id="tv_hide", row=0)
    async def btn_hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        row, channel = await _get_row_and_channel(interaction)
        if not row: return
        if not await _owner_only(interaction, row): return

        new_val = not bool(row["hidden"])
        ow = channel.overwrites_for(interaction.guild.default_role)
        ow.view_channel = False if new_val else None
        await channel.set_permissions(interaction.guild.default_role,
                                      overwrite=ow if not ow.is_empty() else None)

        await interaction.client.db.update_tempvoice_state(row["channel_id"], hidden=int(new_val))
        row["hidden"] = int(new_val)
        owner = interaction.guild.get_member(row["owner_id"])
        await interaction.response.edit_message(embed=_control_embed(channel, owner, row))

    @discord.ui.button(label="🔐 Privé", style=discord.ButtonStyle.primary, custom_id="tv_private", row=0)
    async def btn_private(self, interaction: discord.Interaction, button: discord.ui.Button):
        row, channel = await _get_row_and_channel(interaction)
        if not row: return
        if not await _owner_only(interaction, row): return

        both_on = bool(row["locked"]) and bool(row["hidden"])
        new_val = not both_on
        ow = channel.overwrites_for(interaction.guild.default_role)
        ow.connect      = False if new_val else None
        ow.view_channel = False if new_val else None
        await channel.set_permissions(interaction.guild.default_role,
                                      overwrite=ow if not ow.is_empty() else None)
        if new_val:
            for uid in json.loads(row.get("allowed_users") or "[]"):
                if m := interaction.guild.get_member(uid):
                    await channel.set_permissions(m, connect=True, view_channel=True)

        await interaction.client.db.update_tempvoice_state(row["channel_id"], locked=int(new_val), hidden=int(new_val))
        row["locked"] = int(new_val)
        row["hidden"] = int(new_val)
        owner = interaction.guild.get_member(row["owner_id"])
        await interaction.response.edit_message(embed=_control_embed(channel, owner, row))

    # ── Row 1 : Renommer | Limite | Transférer ────────────────────────────────

    @discord.ui.button(label="✏️ Renommer", style=discord.ButtonStyle.secondary, custom_id="tv_rename", row=1)
    async def btn_rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        row, channel = await _get_row_and_channel(interaction)
        if not row: return
        if not await _owner_only(interaction, row): return
        await interaction.response.send_modal(RenameModal(row["channel_id"], self.bot))

    @discord.ui.button(label="👥 Limite", style=discord.ButtonStyle.secondary, custom_id="tv_limit", row=1)
    async def btn_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        row, channel = await _get_row_and_channel(interaction)
        if not row: return
        if not await _owner_only(interaction, row): return
        await interaction.response.send_modal(LimitModal(row["channel_id"], self.bot))

    @discord.ui.button(label="👑 Transférer", style=discord.ButtonStyle.secondary, custom_id="tv_transfer", row=1)
    async def btn_transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        row, channel = await _get_row_and_channel(interaction)
        if not row: return
        if not await _owner_only(interaction, row): return
        view = discord.ui.View(timeout=30)
        view.add_item(TransferUserSelect(row["channel_id"]))
        await interaction.response.send_message("Choisis le nouveau propriétaire :", view=view, ephemeral=True)

    # ── Row 2 : Autoriser | Expulser | Supprimer ──────────────────────────────

    @discord.ui.button(label="➕ Autoriser", style=discord.ButtonStyle.success, custom_id="tv_allow", row=2)
    async def btn_allow(self, interaction: discord.Interaction, button: discord.ui.Button):
        row, channel = await _get_row_and_channel(interaction)
        if not row: return
        if not await _owner_only(interaction, row): return
        view = discord.ui.View(timeout=30)
        view.add_item(AllowUserSelect(row["channel_id"]))
        await interaction.response.send_message("Choisis un utilisateur à autoriser :", view=view, ephemeral=True)

    @discord.ui.button(label="🚫 Expulser", style=discord.ButtonStyle.danger, custom_id="tv_kick", row=2)
    async def btn_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        row, channel = await _get_row_and_channel(interaction)
        if not row: return
        if not await _owner_only(interaction, row): return
        view = discord.ui.View(timeout=30)
        view.add_item(KickUserSelect(row["channel_id"]))
        await interaction.response.send_message("Choisis un utilisateur à expulser :", view=view, ephemeral=True)

    @discord.ui.button(label="🗑️ Supprimer", style=discord.ButtonStyle.danger, custom_id="tv_delete", row=2)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        row, channel = await _get_row_and_channel(interaction)
        if not row: return
        if not await _owner_only(interaction, row): return

        await interaction.client.db.delete_tempvoice_channel(row["channel_id"])
        await interaction.response.send_message("✅ Salon vocal supprimé.", ephemeral=True)
        try: await channel.delete(reason="TempVoice: supprimé par le propriétaire")
        except discord.NotFound: pass
        try: await interaction.message.delete()
        except (discord.NotFound, discord.Forbidden): pass


# ══════════════════════════════════════════════════════════════════════════════
#  Cog
# ══════════════════════════════════════════════════════════════════════════════

class TempVoice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TempVoiceControlView(self.bot))

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        rows = await self.bot.db.get_all_tempvoice_channels()
        for row in rows:
            guild   = self.bot.get_guild(row["guild_id"])
            if not guild: continue
            channel = guild.get_channel(row["channel_id"])
            if not channel or len(channel.members) == 0:
                await self._delete_temp_channel(guild, row)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Member joined a channel
        if after.channel:
            config = await self.bot.db.get_tempvoice_config(member.guild.id)
            trigger = config.get("trigger_channel_id")
            if trigger and after.channel.id == trigger:
                await self._create_temp_channel(member, config)

        # Member left a channel
        if before.channel and before.channel != after.channel:
            row = await self.bot.db.get_tempvoice_channel(before.channel.id)
            if not row:
                return
            if len(before.channel.members) == 0:
                await self._delete_temp_channel(member.guild, row)
            elif member.id == row["owner_id"]:
                # Transfer ownership to the next member
                new_owner = before.channel.members[0]
                await self.bot.db.update_tempvoice_owner(before.channel.id, new_owner.id)
                updated = {**row, "owner_id": new_owner.id}
                await _update_control_msg(
                    self.bot, member.guild, updated,
                    _control_embed(before.channel, new_owner, updated)
                )

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _create_temp_channel(self, member: discord.Member, config: dict):
        guild    = member.guild
        category = guild.get_channel(config.get("category_id") or 0)
        name     = (config.get("name_format") or "{user} • Salon").replace(
            "{user}", member.display_name[:20]
        )
        limit = config.get("default_limit") or 0

        try:
            channel = await guild.create_voice_channel(
                name=name,
                category=category,
                user_limit=limit,
                reason="TempVoice: création automatique"
            )
            await member.move_to(channel, reason="TempVoice")
        except (discord.Forbidden, discord.HTTPException):
            return

        ctrl_msg_id = None
        ctrl_ch = guild.get_channel(config.get("control_channel_id") or 0)
        if ctrl_ch:
            row_preview = {
                "channel_id": channel.id, "owner_id": member.id,
                "locked": 0, "hidden": 0, "allowed_users": "[]"
            }
            embed = _control_embed(channel, member, row_preview)
            view  = TempVoiceControlView(self.bot)
            try:
                msg         = await ctrl_ch.send(embed=embed, view=view)
                ctrl_msg_id = msg.id
            except discord.Forbidden:
                pass

        await self.bot.db.create_tempvoice_channel(channel.id, guild.id, member.id, ctrl_msg_id)

    async def _delete_temp_channel(self, guild: discord.Guild, row: dict):
        channel = guild.get_channel(row["channel_id"])
        await self.bot.db.delete_tempvoice_channel(row["channel_id"])

        if channel:
            try: await channel.delete(reason="TempVoice: salon vide")
            except discord.NotFound: pass

        if row.get("control_msg_id"):
            config  = await self.bot.db.get_tempvoice_config(guild.id)
            ctrl_ch = guild.get_channel(config.get("control_channel_id") or 0)
            if ctrl_ch:
                try:
                    msg = await ctrl_ch.fetch_message(row["control_msg_id"])
                    await msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

    # ── Commands ──────────────────────────────────────────────────────────────

    tempvoice_group = app_commands.Group(name="tempvoice", description="Salons vocaux temporaires")

    @tempvoice_group.command(name="setup", description="Configure les salons vocaux temporaires")
    @app_commands.describe(
        trigger="Salon vocal à rejoindre pour créer son salon",
        control="Salon textuel où le panneau de contrôle sera envoyé",
        categorie="Catégorie où créer les salons (optionnel)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def tv_setup(
        self,
        interaction: discord.Interaction,
        trigger:    discord.VoiceChannel,
        control:    discord.TextChannel,
        categorie:  discord.CategoryChannel = None
    ):
        db  = self.bot.db
        gid = interaction.guild.id
        await db.update_tempvoice_config(gid, "trigger_channel_id", trigger.id)
        await db.update_tempvoice_config(gid, "control_channel_id", control.id)
        if categorie:
            await db.update_tempvoice_config(gid, "category_id", categorie.id)

        embed = discord.Embed(title="✅ TempVoice configuré", color=discord.Color.green())
        embed.add_field(name="🎙️ Déclencheur",      value=trigger.mention,                          inline=True)
        embed.add_field(name="🎛️ Panneau de contrôle", value=control.mention,                       inline=True)
        if categorie:
            embed.add_field(name="📁 Catégorie", value=categorie.mention, inline=True)
        embed.set_footer(text="Rejoins le salon déclencheur pour créer ton salon vocal !")
        await interaction.response.send_message(embed=embed)

    @tempvoice_group.command(name="config", description="Configure le nom et la limite par défaut")
    @app_commands.describe(
        format="Format du nom ({user} = pseudo du membre)",
        limite="Limite de membres par défaut (0 = illimité)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def tv_config(
        self,
        interaction: discord.Interaction,
        format: str = None,
        limite: app_commands.Range[int, 0, 99] = None
    ):
        gid = interaction.guild.id
        if format is not None:
            await self.bot.db.update_tempvoice_config(gid, "name_format", format)
        if limite is not None:
            await self.bot.db.update_tempvoice_config(gid, "default_limit", limite)
        await interaction.response.send_message("✅ Configuration mise à jour.", ephemeral=True)

    @tempvoice_group.command(name="status", description="Affiche la configuration TempVoice")
    @app_commands.default_permissions(manage_guild=True)
    async def tv_status(self, interaction: discord.Interaction):
        config   = await self.bot.db.get_tempvoice_config(interaction.guild.id)
        trigger  = interaction.guild.get_channel(config.get("trigger_channel_id")  or 0)
        control  = interaction.guild.get_channel(config.get("control_channel_id")  or 0)
        category = interaction.guild.get_channel(config.get("category_id") or 0)

        embed = discord.Embed(title="🎙️ TempVoice — Configuration", color=discord.Color.blurple())
        embed.add_field(name="Déclencheur",   value=trigger.mention  if trigger  else "❌ Non configuré", inline=True)
        embed.add_field(name="Contrôle",      value=control.mention  if control  else "❌ Non configuré", inline=True)
        embed.add_field(name="Catégorie",     value=category.mention if category else "Aucune",           inline=True)
        embed.add_field(name="Format du nom", value=f"`{config.get('name_format') or '{user} • Salon'}`", inline=True)
        embed.add_field(name="Limite défaut", value=str(config.get("default_limit") or "Illimitée"),      inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TempVoice(bot))
