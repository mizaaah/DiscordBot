import discord
import json
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.embeds import error_embed, info_embed, success_embed
from utils.i18n import t


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _control_embed(channel: discord.VoiceChannel, owner: discord.Member | None, row: dict, lang: str) -> discord.Embed:
    locked  = bool(row.get("locked", 0))
    hidden  = bool(row.get("hidden", 0))
    allowed = json.loads(row.get("allowed_users") or "[]")

    if locked and hidden:
        color = Colors.ERROR
    elif locked or hidden:
        color = Colors.WARNING
    else:
        color = Colors.SUCCESS

    owner_name = owner.display_name if owner else t(lang, "tv.unknown")
    embed = discord.Embed(
        title=t(lang, "tv.channel_title", owner=owner_name),
        color=color,
        description=(
            f"{t(lang, 'tv.locked') if locked else t(lang, 'tv.unlocked')}"
            f"  •  "
            f"{t(lang, 'tv.hidden') if hidden else t(lang, 'tv.visible')}"
        ),
    )

    if owner:
        embed.set_thumbnail(url=owner.display_avatar.url)

    members = channel.members
    limit   = channel.user_limit
    limit_str = f"{len(members)}/{limit}" if limit else f"{len(members)}/∞"

    embed.add_field(name=t(lang, "tv.owner_field"), value=owner.mention if owner else "❓", inline=True)
    embed.add_field(name=t(lang, "tv.members_field"), value=limit_str,                        inline=True)

    if members:
        member_list = " ".join(m.mention for m in members[:10])
        if len(members) > 10:
            member_list += f" *+{len(members) - 10}*"
        embed.add_field(name=t(lang, "tv.in_channel_field"), value=member_list, inline=False)

    if allowed:
        embed.add_field(
            name=t(lang, "tv.allowed_field", count=len(allowed)),
            value=" ".join(f"<@{uid}>" for uid in allowed[:15]),
            inline=False,
        )

    embed.set_footer(text=t(lang, "tv.owner_only_footer"))
    return embed


async def _get_row_and_channel(interaction: discord.Interaction, lang: str):
    row = await interaction.client.db.get_tempvoice_by_msg(interaction.message.id)
    if not row:
        await interaction.response.send_message(embed=error_embed(t(lang, "tv.channel_not_in_db")), ephemeral=True)
        return None, None
    channel = interaction.guild.get_channel(row["channel_id"])
    if not channel:
        await interaction.client.db.delete_tempvoice_channel(row["channel_id"])
        await interaction.response.send_message(embed=error_embed(t(lang, "tv.channel_already_deleted")), ephemeral=True)
        return None, None
    return row, channel


async def _owner_only(interaction: discord.Interaction, row: dict, lang: str) -> bool:
    if interaction.user.id != row["owner_id"]:
        await interaction.response.send_message(embed=error_embed(t(lang, "tv.owner_only")), ephemeral=True)
        return False
    return True


async def _update_control_msg(bot: commands.Bot, guild: discord.Guild, row: dict, embed: discord.Embed):
    """Edit the control panel message inside the voice channel."""
    if not row or not row.get("control_msg_id"):
        return
    channel = guild.get_channel(row["channel_id"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(row["control_msg_id"])
        await msg.edit(embed=embed)
    except (discord.NotFound, discord.Forbidden):
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Modals
# ══════════════════════════════════════════════════════════════════════════════

class RenameModal(discord.ui.Modal, title="✏️ Renommer le salon"):
    new_name = discord.ui.TextInput(label="Nouveau nom", max_length=100, min_length=1)

    def __init__(self, channel_id: int, bot: commands.Bot, lang: str):
        super().__init__()
        self.channel_id = channel_id
        self.bot        = bot
        self.lang       = lang

    async def on_submit(self, interaction: discord.Interaction):
        lang = self.lang
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message(embed=error_embed(t(lang, "tv.channel_not_found")), ephemeral=True)
        await channel.edit(name=self.new_name.value.strip(), reason="TempVoice: renommé")
        row   = await self.bot.db.get_tempvoice_channel(self.channel_id)
        owner = interaction.guild.get_member(row["owner_id"]) if row else None
        await _update_control_msg(self.bot, interaction.guild, row, _control_embed(channel, owner, row or {}, lang))
        await interaction.response.send_message(embed=success_embed(t(lang, "tv.renamed", name=self.new_name.value)), ephemeral=True)


class LimitModal(discord.ui.Modal, title="👥 Limite de membres"):
    limit = discord.ui.TextInput(label="Limite (0 = illimité)", max_length=2, placeholder="0–99")

    def __init__(self, channel_id: int, bot: commands.Bot, lang: str):
        super().__init__()
        self.channel_id = channel_id
        self.bot        = bot
        self.lang       = lang

    async def on_submit(self, interaction: discord.Interaction):
        lang = self.lang
        try:
            val = int(self.limit.value.strip())
            if not 0 <= val <= 99:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(embed=error_embed(t(lang, "tv.invalid_limit")), ephemeral=True)
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message(embed=error_embed(t(lang, "tv.channel_not_found")), ephemeral=True)
        await channel.edit(user_limit=val, reason="TempVoice: limite modifiée")
        row   = await self.bot.db.get_tempvoice_channel(self.channel_id)
        owner = interaction.guild.get_member(row["owner_id"]) if row else None
        await _update_control_msg(self.bot, interaction.guild, row, _control_embed(channel, owner, row or {}, lang))
        lim_str = t(lang, "tv.limit_n", n=val) if val else t(lang, "tv.limit_unlimited")
        await interaction.response.send_message(embed=success_embed(t(lang, "tv.limit_set", limit=lim_str)), ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  UserSelect components
# ══════════════════════════════════════════════════════════════════════════════

class AllowUserSelect(discord.ui.UserSelect):
    def __init__(self, channel_id: int, lang: str):
        super().__init__(placeholder="Utilisateur à autoriser…", min_values=1, max_values=1)
        self.channel_id = channel_id
        self.lang = lang

    async def callback(self, interaction: discord.Interaction):
        lang    = self.lang
        user    = self.values[0]
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message(embed=error_embed(t(lang, "tv.channel_not_found")), ephemeral=True)
        await channel.set_permissions(user, connect=True, view_channel=True, reason="TempVoice: autorisé")
        row = await interaction.client.db.get_tempvoice_channel(self.channel_id)
        if row:
            allowed = json.loads(row.get("allowed_users") or "[]")
            if user.id not in allowed:
                allowed.append(user.id)
                await interaction.client.db.update_tempvoice_allowed(self.channel_id, allowed)
                row["allowed_users"] = json.dumps(allowed)
            owner = interaction.guild.get_member(row["owner_id"])
            await _update_control_msg(interaction.client, interaction.guild, row, _control_embed(channel, owner, row, lang))
        await interaction.response.send_message(embed=success_embed(t(lang, "tv.user_allowed", user=user.mention)), ephemeral=True)


class KickUserSelect(discord.ui.UserSelect):
    def __init__(self, channel_id: int, lang: str):
        super().__init__(placeholder="Utilisateur à expulser…", min_values=1, max_values=1)
        self.channel_id = channel_id
        self.lang = lang

    async def callback(self, interaction: discord.Interaction):
        lang    = self.lang
        user    = self.values[0]
        channel = interaction.guild.get_channel(self.channel_id)
        member  = interaction.guild.get_member(user.id)
        if not member or not member.voice or member.voice.channel != channel:
            return await interaction.response.send_message(embed=error_embed(t(lang, "tv.user_not_in_channel", user=user.mention)), ephemeral=True)
        if user.id == interaction.user.id:
            return await interaction.response.send_message(embed=error_embed(t(lang, "tv.cant_kick_self")), ephemeral=True)
        await member.move_to(None, reason="TempVoice: expulsé par le propriétaire")
        await interaction.response.send_message(embed=success_embed(t(lang, "tv.user_kicked", user=user.mention)), ephemeral=True)


class TransferUserSelect(discord.ui.UserSelect):
    def __init__(self, channel_id: int, lang: str):
        super().__init__(placeholder="Nouveau propriétaire…", min_values=1, max_values=1)
        self.channel_id = channel_id
        self.lang = lang

    async def callback(self, interaction: discord.Interaction):
        lang      = self.lang
        new_owner = self.values[0]
        if new_owner.bot:
            return await interaction.response.send_message(embed=error_embed(t(lang, "tv.cant_transfer_bot")), ephemeral=True)
        if new_owner.id == interaction.user.id:
            return await interaction.response.send_message(embed=error_embed(t(lang, "tv.already_owner")), ephemeral=True)
        await interaction.client.db.update_tempvoice_owner(self.channel_id, new_owner.id)
        row     = await interaction.client.db.get_tempvoice_channel(self.channel_id)
        channel = interaction.guild.get_channel(self.channel_id)
        if row and channel:
            updated = {**row, "owner_id": new_owner.id}
            await _update_control_msg(interaction.client, interaction.guild, updated,
                                      _control_embed(channel, new_owner, updated, lang))
        await interaction.response.send_message(embed=success_embed(t(lang, "tv.ownership_transferred", user=new_owner.mention)), ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Persistent control view
# ══════════════════════════════════════════════════════════════════════════════

class TempVoiceControlView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.select(
        placeholder="⚙️ Gérer le salon vocal...",
        custom_id="tv_action_select",
        options=[
            discord.SelectOption(label="Verrouiller / Déverrouiller", emoji="🔒", value="lock"),
            discord.SelectOption(label="Masquer / Afficher", emoji="👁️", value="hide"),
            discord.SelectOption(label="Rendre Privé / Public", emoji="🔐", value="private"),
            discord.SelectOption(label="Renommer le salon", emoji="✏️", value="rename"),
            discord.SelectOption(label="Modifier la limite", emoji="👥", value="limit"),
            discord.SelectOption(label="Transférer la propriété", emoji="👑", value="transfer"),
            discord.SelectOption(label="Autoriser un membre", emoji="➕", value="allow"),
            discord.SelectOption(label="Expulser un membre", emoji="🚫", value="kick"),
            discord.SelectOption(label="Supprimer le salon", emoji="🗑️", value="delete"),
        ]
    )
    async def select_action(self, interaction: discord.Interaction, select: discord.ui.Select):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        row, channel = await _get_row_and_channel(interaction, lang)
        if not row: return
        
        # Vérification propriétaire
        if not await _owner_only(interaction, row, lang):
            # Refresh view silently
            try: await interaction.response.edit_message(view=self)
            except: pass
            return

        action = select.values[0]
        
        # Reset select visually for toggles that edit message
        if action in ["lock", "hide", "private"]:
            select.values = []

        if action == "lock":
            new_val = not bool(row["locked"])
            ow = channel.overwrites_for(interaction.guild.default_role)
            ow.connect = False if new_val else None
            await channel.set_permissions(interaction.guild.default_role, overwrite=ow if not ow.is_empty() else None)
            if new_val:
                for uid in json.loads(row.get("allowed_users") or "[]"):
                    if m := interaction.guild.get_member(uid):
                        await channel.set_permissions(m, connect=True)
            await interaction.client.db.update_tempvoice_state(row["channel_id"], locked=int(new_val))
            row["locked"] = int(new_val)
            owner = interaction.guild.get_member(row["owner_id"])
            await interaction.response.edit_message(embed=_control_embed(channel, owner, row, lang), view=self)

        elif action == "hide":
            new_val = not bool(row["hidden"])
            ow = channel.overwrites_for(interaction.guild.default_role)
            ow.view_channel = False if new_val else None
            await channel.set_permissions(interaction.guild.default_role, overwrite=ow if not ow.is_empty() else None)
            await interaction.client.db.update_tempvoice_state(row["channel_id"], hidden=int(new_val))
            row["hidden"] = int(new_val)
            owner = interaction.guild.get_member(row["owner_id"])
            await interaction.response.edit_message(embed=_control_embed(channel, owner, row, lang), view=self)

        elif action == "private":
            both_on = bool(row["locked"]) and bool(row["hidden"])
            new_val = not both_on
            ow = channel.overwrites_for(interaction.guild.default_role)
            ow.connect      = False if new_val else None
            ow.view_channel = False if new_val else None
            await channel.set_permissions(interaction.guild.default_role, overwrite=ow if not ow.is_empty() else None)
            if new_val:
                for uid in json.loads(row.get("allowed_users") or "[]"):
                    if m := interaction.guild.get_member(uid):
                        await channel.set_permissions(m, connect=True, view_channel=True)
            await interaction.client.db.update_tempvoice_state(row["channel_id"], locked=int(new_val), hidden=int(new_val))
            row["locked"] = int(new_val)
            row["hidden"] = int(new_val)
            owner = interaction.guild.get_member(row["owner_id"])
            await interaction.response.edit_message(embed=_control_embed(channel, owner, row, lang), view=self)

        elif action == "rename":
            await interaction.response.send_modal(RenameModal(row["channel_id"], self.bot, lang))

        elif action == "limit":
            await interaction.response.send_modal(LimitModal(row["channel_id"], self.bot, lang))

        elif action == "transfer":
            view = discord.ui.View(timeout=30)
            view.add_item(TransferUserSelect(row["channel_id"], lang))
            await interaction.response.send_message(embed=info_embed(t(lang, "tv.pick_new_owner")), view=view, ephemeral=True)

        elif action == "allow":
            view = discord.ui.View(timeout=30)
            view.add_item(AllowUserSelect(row["channel_id"], lang))
            await interaction.response.send_message(embed=info_embed(t(lang, "tv.pick_user_allow")), view=view, ephemeral=True)

        elif action == "kick":
            view = discord.ui.View(timeout=30)
            view.add_item(KickUserSelect(row["channel_id"], lang))
            await interaction.response.send_message(embed=info_embed(t(lang, "tv.pick_user_kick")), view=view, ephemeral=True)

        elif action == "delete":
            await interaction.client.db.delete_tempvoice_channel(row["channel_id"])
            await interaction.response.send_message(embed=success_embed(t(lang, "tv.channel_deleted")), ephemeral=True)
            try: await channel.delete(reason="TempVoice: supprimé par le propriétaire")
            except discord.NotFound: pass


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
        if after.channel:
            config  = await self.bot.db.get_tempvoice_config(member.guild.id)
            trigger = config.get("trigger_channel_id")
            if trigger and after.channel.id == trigger:
                await self._create_temp_channel(member, config)

        if before.channel and before.channel != after.channel:
            row = await self.bot.db.get_tempvoice_channel(before.channel.id)
            if not row:
                return
            if len(before.channel.members) == 0:
                await self._delete_temp_channel(member.guild, row)
            elif member.id == row["owner_id"]:
                lang = await self.bot.db.get_guild_lang(member.guild.id)
                new_owner = before.channel.members[0]
                await self.bot.db.update_tempvoice_owner(before.channel.id, new_owner.id)
                updated = {**row, "owner_id": new_owner.id}
                await _update_control_msg(
                    self.bot, member.guild, updated,
                    _control_embed(before.channel, new_owner, updated, lang)
                )

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _create_temp_channel(self, member: discord.Member, config: dict):
        guild    = member.guild
        lang     = await self.bot.db.get_guild_lang(guild.id)
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
                reason="TempVoice: création automatique",
            )
            await member.move_to(channel, reason="TempVoice")
        except (discord.Forbidden, discord.HTTPException):
            return

        row_preview = {
            "channel_id": channel.id, "owner_id": member.id,
            "locked": 0, "hidden": 0, "allowed_users": "[]",
        }
        embed = _control_embed(channel, member, row_preview, lang)
        view  = TempVoiceControlView(self.bot)

        ctrl_msg_id = None
        try:
            msg         = await channel.send(embed=embed, view=view)
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

    # ── Commands ──────────────────────────────────────────────────────────────

    tempvoice_group = app_commands.Group(name="tempvoice", description="Salons vocaux temporaires")

    @tempvoice_group.command(name="setup", description="Configure les salons vocaux temporaires")
    @app_commands.describe(
        trigger="Salon vocal à rejoindre pour créer son salon",
        categorie="Catégorie où créer les salons (optionnel)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def tv_setup(
        self,
        interaction: discord.Interaction,
        trigger:    discord.VoiceChannel,
        categorie:  discord.CategoryChannel = None,
    ):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        db  = self.bot.db
        gid = interaction.guild.id
        await db.update_tempvoice_config(gid, "trigger_channel_id", trigger.id)
        if categorie:
            await db.update_tempvoice_config(gid, "category_id", categorie.id)

        embed = discord.Embed(
            title=t(lang, "tv.setup_success_title"),
            color=Colors.SUCCESS,
            description=t(lang, "tv.setup_success_desc"),
        )
        embed.add_field(name=t(lang, "tv.trigger_field"), value=trigger.mention, inline=True)
        if categorie:
            embed.add_field(name=t(lang, "tv.category_field"), value=categorie.mention, inline=True)
        embed.set_footer(text=t(lang, "tv.setup_footer"))
        await interaction.response.send_message(embed=embed)

    @tempvoice_group.command(name="config", description="Configure le nom et la limite par défaut")
    @app_commands.describe(
        format="Format du nom ({user} = pseudo du membre)",
        limite="Limite de membres par défaut (0 = illimité)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def tv_config(
        self,
        interaction: discord.Interaction,
        format: str = None,
        limite: app_commands.Range[int, 0, 99] = None,
    ):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        gid = interaction.guild.id
        if format is not None:
            await self.bot.db.update_tempvoice_config(gid, "name_format", format)
        if limite is not None:
            await self.bot.db.update_tempvoice_config(gid, "default_limit", limite)
        await interaction.response.send_message(embed=success_embed(t(lang, "tv.config_updated")), ephemeral=True)

    @tempvoice_group.command(name="status", description="Affiche la configuration TempVoice")
    @app_commands.default_permissions(manage_guild=True)
    async def tv_status(self, interaction: discord.Interaction):
        lang     = await self.bot.db.get_guild_lang(interaction.guild_id)
        config   = await self.bot.db.get_tempvoice_config(interaction.guild.id)
        trigger  = interaction.guild.get_channel(config.get("trigger_channel_id") or 0)
        category = interaction.guild.get_channel(config.get("category_id") or 0)
        rows     = await self.bot.db.get_all_tempvoice_channels()
        active   = sum(1 for r in rows if r["guild_id"] == interaction.guild.id)

        embed = discord.Embed(title=t(lang, "tv.status_title"), color=Colors.INFO)
        embed.add_field(name=t(lang, "tv.trigger_field"),  value=trigger.mention  if trigger  else t(lang, "tv.not_configured"), inline=True)
        embed.add_field(name=t(lang, "tv.category_field"), value=category.mention if category else t(lang, "tv.none"),           inline=True)
        embed.add_field(name=t(lang, "tv.active_channels_field"), value=str(active),                                          inline=True)
        embed.add_field(name=t(lang, "tv.name_format_field"), value=f"`{config.get('name_format') or '{user} • Salon'}`", inline=True)
        embed.add_field(name=t(lang, "tv.default_limit_field"), value=str(config.get("default_limit") or t(lang, "tv.limit_unlimited")), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TempVoice(bot))
