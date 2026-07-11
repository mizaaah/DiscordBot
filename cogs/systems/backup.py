import discord
from discord.ext import commands
from discord import app_commands
import json
import uuid
import time
from cogs.core.config import Colors

class BackupConfirmView(discord.ui.View):
    def __init__(self, bot, guild, backup_id, data):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild = guild
        self.backup_id = backup_id
        self.data = data
        self.value = None

    @discord.ui.button(label="Confirmer la Restauration (DESTRUCTIF)", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.guild.owner_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Tu n'as pas la permission d'effectuer cette action.", ephemeral=True)
            return

        self.value = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="⏳ **Restauration en cours...** Cela peut prendre plusieurs minutes. NE FAITES RIEN.", view=self, embed=None)
        
        # Lancer la restauration en arrière-plan
        interaction.client.loop.create_task(self.restore_backup(interaction))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ **Restauration annulée.**", view=self, embed=None)

    async def restore_backup(self, interaction: discord.Interaction):
        guild = self.guild
        data = self.data

        try:
            # 1. Supprimer tous les salons
            for channel in guild.channels:
                try:
                    await channel.delete()
                except discord.HTTPException:
                    pass

            # 2. Supprimer tous les rôles (sauf ceux non supprimables)
            for role in guild.roles:
                if role != guild.default_role and not role.managed and role < guild.me.top_role:
                    try:
                        await role.delete()
                    except discord.HTTPException:
                        pass

            role_mapping = {} # old_name -> new_role_obj
            category_mapping = {} # old_name -> new_category_obj

            # 3. Restaurer les rôles
            # Inverser pour respecter l'ordre (les rôles plus bas en premier)
            for role_data in reversed(data.get("roles", [])):
                if role_data["name"] == "@everyone":
                    try:
                        await guild.default_role.edit(permissions=discord.Permissions(role_data["permissions"]))
                        role_mapping["@everyone"] = guild.default_role
                    except Exception:
                        pass
                    continue

                try:
                    new_role = await guild.create_role(
                        name=role_data["name"],
                        color=discord.Color(role_data["color"]),
                        permissions=discord.Permissions(role_data["permissions"]),
                        hoist=role_data["hoist"],
                        mentionable=role_data["mentionable"]
                    )
                    role_mapping[role_data["name"]] = new_role
                except Exception:
                    pass

            def build_overwrites(ow_data):
                overwrites = {}
                for ow in ow_data:
                    if ow["type"] == "role":
                        target_role = role_mapping.get(ow["name"])
                        if target_role:
                            overwrites[target_role] = discord.PermissionOverwrite.from_pair(
                                discord.Permissions(ow["allow"]), discord.Permissions(ow["deny"])
                            )
                return overwrites

            # 4. Restaurer les catégories
            for cat_data in data.get("categories", []):
                try:
                    new_cat = await guild.create_category(
                        name=cat_data["name"],
                        overwrites=build_overwrites(cat_data["overwrites"])
                    )
                    category_mapping[cat_data["name"]] = new_cat
                except Exception:
                    pass

            # 5. Restaurer les salons textuels
            for tc_data in data.get("text_channels", []):
                parent = category_mapping.get(tc_data["category"]) if tc_data["category"] else None
                try:
                    await guild.create_text_channel(
                        name=tc_data["name"],
                        category=parent,
                        topic=tc_data["topic"],
                        nsfw=tc_data["nsfw"],
                        slowmode_delay=tc_data["slowmode_delay"],
                        overwrites=build_overwrites(tc_data["overwrites"])
                    )
                except Exception:
                    pass

            # 6. Restaurer les salons vocaux
            for vc_data in data.get("voice_channels", []):
                parent = category_mapping.get(vc_data["category"]) if vc_data["category"] else None
                try:
                    await guild.create_voice_channel(
                        name=vc_data["name"],
                        category=parent,
                        bitrate=vc_data["bitrate"],
                        user_limit=vc_data["user_limit"],
                        overwrites=build_overwrites(vc_data["overwrites"])
                    )
                except Exception:
                    pass

            # Notifier via le compte du propriétaire si possible, sinon on laisse le bot créer un salon
            try:
                owner = guild.owner
                if owner:
                    await owner.send(f"✅ La restauration de la sauvegarde **{self.backup_id}** sur **{guild.name}** est terminée !")
            except Exception:
                pass
                
        except Exception as e:
            import logging
            logging.error(f"Erreur lors de la restauration : {e}", exc_info=True)


class Backup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def serialize_overwrites(self, overwrites):
        result = []
        for target, overwrite in overwrites.items():
            if isinstance(target, discord.Role):
                result.append({
                    "type": "role",
                    "name": target.name,
                    "allow": overwrite.pair()[0].value,
                    "deny": overwrite.pair()[1].value
                })
        return result

    backup_group = app_commands.Group(name="backup", description="Commandes de sauvegarde du serveur", default_permissions=discord.Permissions(administrator=True))

    @backup_group.command(name="create", description="Créer une sauvegarde complète du serveur")
    async def backup_create(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        data = {
            "roles": [],
            "categories": [],
            "text_channels": [],
            "voice_channels": []
        }

        for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
            if not role.managed:
                data["roles"].append({
                    "name": role.name,
                    "color": role.color.value,
                    "permissions": role.permissions.value,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable
                })

        for cat in guild.categories:
            data["categories"].append({
                "name": cat.name,
                "position": cat.position,
                "overwrites": self.serialize_overwrites(cat.overwrites)
            })

        for tc in guild.text_channels:
            data["text_channels"].append({
                "name": tc.name,
                "category": tc.category.name if tc.category else None,
                "position": tc.position,
                "topic": tc.topic,
                "nsfw": tc.nsfw,
                "slowmode_delay": tc.slowmode_delay,
                "overwrites": self.serialize_overwrites(tc.overwrites)
            })

        for vc in guild.voice_channels:
            data["voice_channels"].append({
                "name": vc.name,
                "category": vc.category.name if vc.category else None,
                "position": vc.position,
                "bitrate": vc.bitrate,
                "user_limit": vc.user_limit,
                "overwrites": self.serialize_overwrites(vc.overwrites)
            })

        backup_id = uuid.uuid4().hex[:8]
        json_data = json.dumps(data)

        await self.bot.db.create_backup(backup_id, guild.id, json_data)
        
        embed = discord.Embed(
            title="✅ Sauvegarde Créée",
            description=f"La sauvegarde du serveur a été créée avec succès.\n\n**ID de la Sauvegarde :** `{backup_id}`",
            color=Colors.SUCCESS.value
        )
        embed.add_field(name="Rôles sauvegardés", value=str(len(data["roles"])))
        embed.add_field(name="Catégories", value=str(len(data["categories"])))
        embed.add_field(name="Salons (Text/Vocal)", value=f"{len(data['text_channels'])} / {len(data['voice_channels'])}")
        
        await interaction.followup.send(embed=embed)

    @backup_group.command(name="list", description="Lister les sauvegardes du serveur")
    async def backup_list(self, interaction: discord.Interaction):
        backups = await self.bot.db.get_backups(interaction.guild.id)
        if not backups:
            await interaction.response.send_message("Aucune sauvegarde trouvée pour ce serveur.", ephemeral=True)
            return

        desc = ""
        for b in backups:
            desc += f"• **ID :** `{b['id']}` - Créée le : {b['created_at']}\n"

        embed = discord.Embed(
            title="💾 Sauvegardes Disponibles",
            description=desc,
            color=Colors.INFO.value
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @backup_group.command(name="info", description="Voir les détails d'une sauvegarde")
    @app_commands.describe(backup_id="L'ID de la sauvegarde")
    async def backup_info(self, interaction: discord.Interaction, backup_id: str):
        backup = await self.bot.db.get_backup(backup_id)
        if not backup or backup["guild_id"] != interaction.guild.id:
            await interaction.response.send_message("Sauvegarde introuvable.", ephemeral=True)
            return

        data = json.loads(backup["data"])
        embed = discord.Embed(
            title=f"ℹ️ Infos Sauvegarde `{backup_id}`",
            description=f"Créée le : {backup['created_at']}",
            color=Colors.INFO.value
        )
        embed.add_field(name="Rôles", value=str(len(data["roles"])))
        embed.add_field(name="Catégories", value=str(len(data["categories"])))
        embed.add_field(name="Salons Textuels", value=str(len(data["text_channels"])))
        embed.add_field(name="Salons Vocaux", value=str(len(data["voice_channels"])))

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @backup_group.command(name="delete", description="Supprimer une sauvegarde")
    @app_commands.describe(backup_id="L'ID de la sauvegarde")
    async def backup_delete(self, interaction: discord.Interaction, backup_id: str):
        backup = await self.bot.db.get_backup(backup_id)
        if not backup or backup["guild_id"] != interaction.guild.id:
            await interaction.response.send_message("Sauvegarde introuvable.", ephemeral=True)
            return

        await self.bot.db.delete_backup(backup_id)
        await interaction.response.send_message(f"✅ Sauvegarde `{backup_id}` supprimée avec succès.", ephemeral=True)

    @backup_group.command(name="load", description="Restaurer une sauvegarde (DESTRUCTIF)")
    @app_commands.describe(backup_id="L'ID de la sauvegarde")
    async def backup_load(self, interaction: discord.Interaction, backup_id: str):
        if interaction.user.id != interaction.guild.owner_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Tu n'as pas la permission de restaurer une sauvegarde.", ephemeral=True)
            return

        backup = await self.bot.db.get_backup(backup_id)
        if not backup or backup["guild_id"] != interaction.guild.id:
            await interaction.response.send_message("Sauvegarde introuvable.", ephemeral=True)
            return

        data = json.loads(backup["data"])

        embed = discord.Embed(
            title="⚠️ RESTAURATION DESTRUCTIVE",
            description=(
                f"Tu es sur le point de restaurer la sauvegarde `{backup_id}`.\n\n"
                "**CETTE ACTION VA :**\n"
                "1. Supprimer TOUS les salons actuels.\n"
                "2. Supprimer TOUS les rôles actuels.\n"
                "3. Recréer la structure de la sauvegarde.\n\n"
                "**Cette action est IRRÉVERSIBLE.** Es-tu sûr de vouloir continuer ?"
            ),
            color=Colors.ERROR.value
        )

        view = BackupConfirmView(self.bot, interaction.guild, backup_id, data)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
