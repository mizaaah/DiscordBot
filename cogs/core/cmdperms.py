import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.embeds import error_embed, success_embed
from utils.i18n import t

TYPE_LABEL_KEYS = {
    "allow_role":    "cmdperm.type_allow_role",
    "deny_role":     "cmdperm.type_deny_role",
    "allow_channel": "cmdperm.type_allow_channel",
}


def get_logs(bot: commands.Bot):
    return bot.get_cog("Logs")


class CmdPerms(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        original = self.bot.tree.interaction_check

        async def patched(interaction: discord.Interaction) -> bool:
            if not await original(interaction):
                return False
            return await self._perm_check(interaction)

        self.bot.tree.interaction_check = patched

    async def _perm_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not interaction.command:
            return True
        if interaction.user.guild_permissions.administrator:
            return True

        cmd_name = interaction.command.qualified_name
        perms    = await self.bot.db.get_cmd_permissions(interaction.guild.id, cmd_name)
        if not perms:
            return True

        lang     = await self.bot.db.get_guild_lang(interaction.guild.id)
        role_ids = {r.id for r in interaction.user.roles}

        # Rôles bloqués
        denied = {p["target_id"] for p in perms if p["type"] == "deny_role"}
        if denied & role_ids:
            await interaction.response.send_message(
                embed=error_embed(t(lang, "cmdperm.denied_role")), ephemeral=True
            )
            return False

        # Salons autorisés
        allowed_ch = {p["target_id"] for p in perms if p["type"] == "allow_channel"}
        if allowed_ch and interaction.channel_id not in allowed_ch:
            ch_list = " ".join(f"<#{cid}>" for cid in list(allowed_ch)[:5])
            await interaction.response.send_message(
                embed=error_embed(t(lang, "cmdperm.wrong_channel", channels=ch_list)), ephemeral=True
            )
            return False

        # Rôles autorisés
        allowed_r = {p["target_id"] for p in perms if p["type"] == "allow_role"}
        if allowed_r and not (allowed_r & role_ids):
            await interaction.response.send_message(
                embed=error_embed(t(lang, "cmdperm.missing_role")), ephemeral=True
            )
            return False

        return True

    # ── Autocomplete ──────────────────────────────────────────────────────────

    async def _cmd_autocomplete(self, interaction: discord.Interaction, current: str):
        names = []
        for cmd in self.bot.tree.get_commands():
            if isinstance(cmd, app_commands.Group):
                for sub in cmd.commands:
                    if isinstance(sub, app_commands.Group):
                        for sub2 in sub.commands:
                            names.append(sub2.qualified_name)
                    else:
                        names.append(sub.qualified_name)
            else:
                names.append(cmd.qualified_name)
        filtered = sorted(c for c in names if current.lower() in c.lower())
        return [app_commands.Choice(name=c, value=c) for c in filtered[:25]]

    # ── Commands ──────────────────────────────────────────────────────────────

    cp_group = app_commands.Group(name="cmdperm", description="Permissions personnalisées par commande")

    @cp_group.command(name="allow-role", description="Réserve une commande à un rôle (whitelist)")
    @app_commands.describe(commande="Commande à restreindre", role="Rôle autorisé")
    @app_commands.autocomplete(commande=_cmd_autocomplete)
    @app_commands.default_permissions(manage_guild=True)
    async def cp_allow_role(self, interaction: discord.Interaction, commande: str, role: discord.Role):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.add_cmd_permission(interaction.guild.id, commande, "allow_role", role.id)
        await interaction.response.send_message(
            embed=success_embed(t(lang, "cmdperm.allow_role_success", command=commande, role=role.mention))
        )
        if logs := get_logs(self.bot):
            await logs.log_config_change(interaction.guild, interaction.user, f"cmdperm allow-role /{commande}", role.mention)

    @cp_group.command(name="deny-role", description="Interdit un rôle d'utiliser une commande (blacklist)")
    @app_commands.describe(commande="Commande à restreindre", role="Rôle bloqué")
    @app_commands.autocomplete(commande=_cmd_autocomplete)
    @app_commands.default_permissions(manage_guild=True)
    async def cp_deny_role(self, interaction: discord.Interaction, commande: str, role: discord.Role):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.add_cmd_permission(interaction.guild.id, commande, "deny_role", role.id)
        await interaction.response.send_message(
            embed=success_embed(t(lang, "cmdperm.deny_role_success", role=role.mention, command=commande))
        )
        if logs := get_logs(self.bot):
            await logs.log_config_change(interaction.guild, interaction.user, f"cmdperm deny-role /{commande}", role.mention)

    @cp_group.command(name="channel", description="Limite une commande à un salon spécifique")
    @app_commands.describe(commande="Commande à restreindre", salon="Salon autorisé")
    @app_commands.autocomplete(commande=_cmd_autocomplete)
    @app_commands.default_permissions(manage_guild=True)
    async def cp_channel(self, interaction: discord.Interaction, commande: str, salon: discord.TextChannel):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.add_cmd_permission(interaction.guild.id, commande, "allow_channel", salon.id)
        await interaction.response.send_message(
            embed=success_embed(t(lang, "cmdperm.channel_success", command=commande, channel=salon.mention))
        )
        if logs := get_logs(self.bot):
            await logs.log_config_change(interaction.guild, interaction.user, f"cmdperm channel /{commande}", salon.mention)

    @cp_group.command(name="reset", description="Supprime toutes les restrictions d'une commande")
    @app_commands.describe(commande="Commande à libérer")
    @app_commands.autocomplete(commande=_cmd_autocomplete)
    @app_commands.default_permissions(manage_guild=True)
    async def cp_reset(self, interaction: discord.Interaction, commande: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        count = await self.bot.db.clear_cmd_permissions(interaction.guild.id, commande)
        if count:
            await interaction.response.send_message(embed=success_embed(t(lang, "cmdperm.reset_success", count=count, command=commande)))
            if logs := get_logs(self.bot):
                await logs.log_config_change(interaction.guild, interaction.user, f"cmdperm reset /{commande}", t(lang, "cmdperm.reset_log", count=count))
        else:
            await interaction.response.send_message(embed=error_embed(t(lang, "cmdperm.reset_none", command=commande)), ephemeral=True)

    @cp_group.command(name="list", description="Liste toutes les restrictions de commandes")
    @app_commands.describe(commande="Filtrer par commande (optionnel)")
    @app_commands.autocomplete(commande=_cmd_autocomplete)
    @app_commands.default_permissions(manage_guild=True)
    async def cp_list(self, interaction: discord.Interaction, commande: str = None):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        rows = await self.bot.db.get_all_cmd_permissions(interaction.guild.id, commande)
        embed = discord.Embed(title=t(lang, "cmdperm.list_title"), color=Colors.INFO)
        if not rows:
            embed.description = t(lang, "cmdperm.list_empty")
        else:
            grouped: dict[str, list] = {}
            for r in rows:
                grouped.setdefault(r["command"], []).append(r)
            lines = []
            for cmd_name, cmd_perms in sorted(grouped.items()):
                lines.append(f"**/{cmd_name}**")
                for p in cmd_perms:
                    label  = t(lang, TYPE_LABEL_KEYS.get(p["type"], p["type"]))
                    target = f"<@&{p['target_id']}>" if "role" in p["type"] else f"<#{p['target_id']}>"
                    lines.append(f"  {label} → {target}")
            embed.description = "\n".join(lines[:40])
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CmdPerms(bot))
