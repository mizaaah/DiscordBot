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


async def _update_control_msg(bot: commands.Bot, guild: discord.Guild, row: dict, view: discord.ui.View):
    """Edit the control panel message inside the voice channel."""
    if not row or not row.get("control_msg_id"):
        return
    channel = guild.get_channel(row["channel_id"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(row["control_msg_id"])
        await msg.edit(view=view, embed=None)
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
        await _update_control_msg(self.bot, interaction.guild, row, TempVoiceControlView(self.bot, channel, owner, row or {}, lang))
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
        await _update_control_msg(self.bot, interaction.guild, row, TempVoiceControlView(self.bot, channel, owner, row or {}, lang))
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
            await _update_control_msg(interaction.client, interaction.guild, row, TempVoiceControlView(self.bot, channel, owner, row, lang))
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
                                      TempVoiceControlView(self.bot, channel, new_owner, updated, lang))
        await interaction.response.send_message(embed=success_embed(t(lang, "tv.ownership_transferred", user=new_owner.mention)), ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Persistent control view
# ══════════════════════════════════════════════════════════════════════════════

class TempVoiceControlView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, channel: discord.VoiceChannel = None, owner: discord.Member = None, row: dict = None, lang: str = "fr"):
        super().__init__(timeout=None)
        self.bot = bot
        
        self.btn_kick = discord.ui.Button(label="Expulser", emoji="🚫", style=discord.ButtonStyle.secondary, custom_id="tv_btn_kick")
        self.btn_kick.callback = self._cb_kick
        
        self.btn_ban = discord.ui.Button(label="Bannir", emoji="🔨", style=discord.ButtonStyle.secondary, custom_id="tv_btn_ban")
        self.btn_ban.callback = self._cb_ban
        
        self.btn_lock = discord.ui.Button(label="Verrouiller / Déverrouiller", emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="tv_btn_lock")
        self.btn_lock.callback = self._cb_lock
        
        self.btn_invite = discord.ui.Button(label="Créer une invitation", emoji="✉️", style=discord.ButtonStyle.primary, custom_id="tv_btn_invite")
        self.btn_invite.callback = self._cb_invite
        
        self.btn_transfer = discord.ui.Button(label="Choisir un nouveau responsable", emoji="👑", style=discord.ButtonStyle.success, custom_id="tv_btn_transfer")
        self.btn_transfer.callback = self._cb_transfer
        
        self.btn_report = discord.ui.Button(label="Signaler un problème...", emoji="🚨", style=discord.ButtonStyle.danger, custom_id="tv_btn_report")
        self.btn_report.callback = self._cb_report
        
        self.select_action = discord.ui.Select(
            placeholder="⚙️ Autres paramètres avancés...",
            custom_id="tv_action_select",
            options=[
                discord.SelectOption(label="Masquer / Afficher", emoji="👁️", value="hide"),
                discord.SelectOption(label="Rendre Privé / Public", emoji="🔐", value="private"),
                discord.SelectOption(label="Renommer le salon", emoji="✏️", value="rename"),
                discord.SelectOption(label="Modifier la limite", emoji="👥", value="limit"),
                discord.SelectOption(label="Autoriser un membre", emoji="➕", value="allow"),
                discord.SelectOption(label="Supprimer le salon", emoji="🗑️", value="delete"),
            ]
        )
        self.select_action.callback = self._cb_select

        if channel and row:
            self._build_layout(channel, owner, row, lang)
        else:
            # During boot/setup, just register the components
            self.add_item(self.btn_kick)
            self.add_item(self.btn_ban)
            self.add_item(self.btn_lock)
            self.add_item(self.btn_invite)
            self.add_item(self.btn_transfer)
            self.add_item(self.btn_report)
            self.add_item(self.select_action)

    def _build_layout(self, channel: discord.VoiceChannel, owner: discord.Member | None, row: dict, lang: str):
        self.clear_items()
        
        locked  = bool(row.get("locked", 0))
        hidden  = bool(row.get("hidden", 0))
        allowed = json.loads(row.get("allowed_users") or "[]")

        if locked and hidden:
            color = Colors.ERROR.value
        elif locked or hidden:
            color = Colors.WARNING.value
        else:
            color = Colors.SUCCESS.value

        owner_name = owner.display_name if owner else t(lang, "tv.unknown")
        locked_txt = t(lang, "tv.locked") if locked else t(lang, "tv.unlocked")
        hidden_txt = t(lang, "tv.hidden") if hidden else t(lang, "tv.visible")
        
        members = channel.members if channel else []
        limit   = channel.user_limit if channel else 0
        limit_str = f"{len(members)}/{limit}" if limit else f"{len(members)}/∞"

        header = f"# 🎙️ Salon de {owner_name}\n"
        header += f"> **{locked_txt}** • **{hidden_txt}**\n\n"
        header += f"👑 **Propriétaire:** {owner.mention if owner else '❓'}\n"
        header += f"👥 **Membres:** {limit_str}\n"

        if members:
            header += f"\n🎶 **Dans le salon:**\n> {' '.join(m.mention for m in members[:10])}\n"
            
        if allowed:
            header += f"\n✅ **Autorisés:**\n> {' '.join(f'<@{uid}>' for uid in allowed[:15])}\n"
            
        header += f"\n*Seul le propriétaire peut modifier ce salon*"

        cont = discord.ui.Container(accent_color=color)
        cont.add_item(discord.ui.TextDisplay(header))
        
        cont.add_item(discord.ui.ActionRow(self.btn_kick, self.btn_ban, self.btn_lock))
        cont.add_item(discord.ui.ActionRow(self.btn_invite, self.btn_transfer, self.btn_report))
        cont.add_item(discord.ui.ActionRow(self.select_action))
        
        self.add_item(cont)

    async def _cb_kick(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        row, channel = await _get_row_and_channel(interaction, lang)
        if not row: return
        if not await _owner_only(interaction, row, lang): return
        view = discord.ui.View(timeout=30)
        view.add_item(KickUserSelect(row["channel_id"], lang))
        await interaction.response.send_message(embed=info_embed(t(lang, "tv.pick_user_kick")), view=view, ephemeral=True)

    async def _cb_ban(self, interaction: discord.Interaction):
        await interaction.response.send_message("Fonctionnalité Bannir bientôt disponible (utilise Expulser + Verrouiller pour l'instant).", ephemeral=True)

    async def _cb_lock(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        row, channel = await _get_row_and_channel(interaction, lang)
        if not row: return
        if not await _owner_only(interaction, row, lang): return
        
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
        
        await interaction.response.edit_message(view=TempVoiceControlView(self.bot, channel, owner, row, lang), embed=None)

    async def _cb_invite(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        row, channel = await _get_row_and_channel(interaction, lang)
        if not row: return
        invite = await channel.create_invite(max_age=3600, max_uses=0, reason="TempVoice Invitation")
        await interaction.response.send_message(f"🔗 Voici l'invitation pour le salon : {invite.url}", ephemeral=True)

    async def _cb_transfer(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        row, channel = await _get_row_and_channel(interaction, lang)
        if not row: return
        if not await _owner_only(interaction, row, lang): return
        view = discord.ui.View(timeout=30)
        view.add_item(TransferUserSelect(row["channel_id"], lang))
        await interaction.response.send_message(embed=info_embed(t(lang, "tv.pick_new_owner")), view=view, ephemeral=True)

    async def _cb_report(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        row, channel = await _get_row_and_channel(interaction, lang)
        
        class TVReportModal(discord.ui.Modal, title="Signaler un problème"):
            raison = discord.ui.TextInput(label="Raison du signalement", style=discord.TextStyle.paragraph, required=True, max_length=1000)
            async def on_submit(self, inter: discord.Interaction):
                logs = inter.client.get_cog("Logs")
                if logs and channel:
                    embed = discord.Embed(title="🚨 Signalement Vocal", description=f"**Auteur:** {inter.user.mention}\n**Salon:** {channel.mention}\n\n**Raison:**\n{self.raison.value}", color=Colors.DANGER.value)
                    await logs.send_log(inter.guild, embed)
                await inter.response.send_message(embed=success_embed("Signalement envoyé à l'équipe de modération !"), ephemeral=True)
                
        await interaction.response.send_modal(TVReportModal())

    async def _cb_select(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        row, channel = await _get_row_and_channel(interaction, lang)
        if not row: return
        
        if not await _owner_only(interaction, row, lang):
            try: await interaction.response.edit_message(view=TempVoiceControlView(self.bot, channel, interaction.guild.get_member(row["owner_id"]), row, lang), embed=None)
            except: pass
            return

        action = self.select_action.values[0]
        
        if action == "hide":
            new_val = not bool(row["hidden"])
            ow = channel.overwrites_for(interaction.guild.default_role)
            ow.view_channel = False if new_val else None
            await channel.set_permissions(interaction.guild.default_role, overwrite=ow if not ow.is_empty() else None)
            await interaction.client.db.update_tempvoice_state(row["channel_id"], hidden=int(new_val))
            row["hidden"] = int(new_val)
            owner = interaction.guild.get_member(row["owner_id"])
            await interaction.response.edit_message(view=TempVoiceControlView(self.bot, channel, owner, row, lang), embed=None)

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
            await interaction.response.edit_message(view=TempVoiceControlView(self.bot, channel, owner, row, lang), embed=None)

        elif action == "rename":
            await interaction.response.send_modal(RenameModal(row["channel_id"], self.bot, lang))
            try: await interaction.message.edit(view=TempVoiceControlView(self.bot, channel, interaction.guild.get_member(row["owner_id"]), row, lang), embed=None)
            except: pass

        elif action == "limit":
            await interaction.response.send_modal(LimitModal(row["channel_id"], self.bot, lang))
            try: await interaction.message.edit(view=TempVoiceControlView(self.bot, channel, interaction.guild.get_member(row["owner_id"]), row, lang), embed=None)
            except: pass

        elif action == "allow":
            view = discord.ui.View(timeout=30)
            view.add_item(AllowUserSelect(row["channel_id"], lang))
            await interaction.response.send_message(embed=info_embed(t(lang, "tv.pick_user_allow")), view=view, ephemeral=True)
            try: await interaction.message.edit(view=TempVoiceControlView(self.bot, channel, interaction.guild.get_member(row["owner_id"]), row, lang), embed=None)
            except: pass

        elif action == "delete":
            await interaction.client.db.delete_tempvoice_channel(row["channel_id"])
            await channel.delete(reason="TempVoice: supprimé manuellement")
            # Note: interaction context might be invalid if the channel is deleted and the message goes with it
            try: await interaction.response.send_message("Salon supprimé.", ephemeral=True)
            except discord.NotFound: pass


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
                    TempVoiceControlView(self.bot, before.channel, new_owner, updated, lang)
                )

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _create_temp_channel(self, member: discord.Member, config: dict):
        guild    = member.guild
        lang     = await self.bot.db.get_guild_lang(guild.id)
        category = guild.get_channel(config.get("category_id") or 0)
        name     = (config.get("name_format") or "✨ | Salon de {user}").replace(
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
        view = TempVoiceControlView(self.bot, channel, member, row_preview, lang)

        ctrl_msg_id = None
        try:
            msg         = await channel.send(view=view)
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



async def setup(bot: commands.Bot):
    await bot.add_cog(TempVoice(bot))
