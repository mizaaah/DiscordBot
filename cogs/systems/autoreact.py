import re
import logging
import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.embeds import success_embed, error_embed

logger = logging.getLogger(__name__)


def parse_emojis(emoji_str: str) -> list[str]:
    """Extrait les emojis personnalisés Discord et Unicode depuis une chaîne."""
    if not emoji_str or not emoji_str.strip():
        return ["❤️"]
    
    # Trouver les custom emojis du type <:nom:id> ou <a:nom:id>
    custom_emojis = re.findall(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', emoji_str)
    # Remplacer les custom emojis par un espace pour parser le reste
    clean_str = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', ' ', emoji_str)
    # Extraire les emojis Unicode ou morceaux séparés par des espaces/virgules
    parts = [p.strip() for p in re.split(r'[\s,]+', clean_str) if p.strip()]
    
    combined = custom_emojis + parts
    return combined[:5] if combined else ["❤️"]


class AutoReact(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Cache en mémoire : channel_id -> {"guild_id": int, "emojis": list[str], "photos_only": int}
        self._cache: dict[int, dict] = {}
        self._cache_loaded = False

    async def _ensure_cache(self):
        """Charge l'ensemble des salons configurés en mémoire au premier appel."""
        if self._cache_loaded:
            return
        try:
            rows = await self.bot.db._rows("SELECT * FROM autoreact_channels")
            import json
            for r in rows:
                d = dict(r)
                try:
                    d["emojis"] = json.loads(d["emojis"])
                except Exception:
                    d["emojis"] = ["❤️"]
                self._cache[d["channel_id"]] = d
            self._cache_loaded = True
        except Exception as e:
            logger.warning(f"Erreur chargement cache autoreact: {e}")

    def _has_photo_or_media(self, message: discord.Message) -> bool:
        """Vérifie si un message contient une photo, vidéo, GIF ou lien multimédia."""
        # 1. Pièces jointes (images / vidéos / gifs)
        for att in message.attachments:
            if att.content_type and (att.content_type.startswith("image/") or att.content_type.startswith("video/")):
                return True
            fname = att.filename.lower()
            if fname.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm")):
                return True

        # 2. Embeds déjà générés
        for embed in message.embeds:
            if embed.type in ("image", "video", "gifv"):
                return True
            if embed.image and embed.image.url:
                return True
            if embed.thumbnail and embed.thumbnail.url:
                return True

        # 3. Liens médias dans le texte (Klipy, Tenor, Giphy, Imgur, extensions directes)
        media_pattern = re.compile(
            r"https?://\S+\.(?:png|jpg|jpeg|gif|webp|mp4|mov)|https?://(?:www\.)?(?:tenor\.com|giphy\.com|klipy\.com|imgur\.com)/\S+",
            re.IGNORECASE
        )
        if media_pattern.search(message.content):
            return True

        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        await self._ensure_cache()

        cfg = self._cache.get(message.channel.id)
        if not cfg:
            return

        # Si le mode "photos uniquement" est actif, vérifier la présence d'une image
        if cfg.get("photos_only", 1):
            if not self._has_photo_or_media(message):
                return

        # Ajouter chaque réaction configurée
        emojis = cfg.get("emojis", ["❤️"])
        for emoji in emojis:
            try:
                await message.add_reaction(emoji)
            except (discord.HTTPException, discord.Forbidden):
                break

    # ── Groupe Slash /autoreact ────────────────────────────────────────────────

    autoreact_group = app_commands.Group(
        name="autoreact",
        description="Gestion des réactions automatiques aux photos et médias",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @autoreact_group.command(name="add", description="Configure l'auto-réaction dans un salon dédié")
    @app_commands.describe(
        salon="Le salon où le bot réagira automatiquement",
        emojis="Les emojis à ajouter (ex: ❤️ ou ❤️ 🔥, max 5)",
        photos_seulement="Réagir uniquement si le message contient une photo/média (par défaut: Oui)"
    )
    async def add(
        self,
        interaction: discord.Interaction,
        salon: discord.TextChannel,
        emojis: str = "❤️",
        photos_seulement: bool = True
    ):
        await self._ensure_cache()
        emoji_list = parse_emojis(emojis)

        await self.bot.db.add_autoreact_channel(interaction.guild_id, salon.id, emoji_list, photos_only=photos_seulement)
        
        # Mettre à jour le cache
        self._cache[salon.id] = {
            "guild_id": interaction.guild_id,
            "channel_id": salon.id,
            "emojis": emoji_list,
            "photos_only": 1 if photos_seulement else 0
        }

        mode_str = "📸 Photos uniquement" if photos_seulement else "💬 Tous les messages"
        emojis_str = " ".join(emoji_list)
        await interaction.response.send_message(
            embed=success_embed(
                f"✅ **Auto-réaction activée avec succès !**\n\n"
                f"• **Salon :** {salon.mention}\n"
                f"• **Réactions :** {emojis_str}\n"
                f"• **Condition :** `{mode_str}`"
            ),
            ephemeral=True
        )

    @autoreact_group.command(name="remove", description="Désactive l'auto-réaction dans un salon")
    @app_commands.describe(salon="Le salon à retirer")
    async def remove(self, interaction: discord.Interaction, salon: discord.TextChannel):
        await self._ensure_cache()
        await self.bot.db.remove_autoreact_channel(interaction.guild_id, salon.id)
        self._cache.pop(salon.id, None)

        await interaction.response.send_message(
            embed=success_embed(f"✅ L'auto-réaction a été **désactivée** dans {salon.mention}."),
            ephemeral=True
        )

    @autoreact_group.command(name="list", description="Affiche les salons d'auto-réaction configurés")
    async def list_channels(self, interaction: discord.Interaction):
        channels = await self.bot.db.get_autoreact_channels(interaction.guild_id)
        if not channels:
            return await interaction.response.send_message(
                "ℹ️ Aucun salon d'auto-réaction n'est configuré sur ce serveur.\nUtilisez `/autoreact add` pour en ajouter un !",
                ephemeral=True
            )

        embed = discord.Embed(
            title="📸 Salons d'Auto-Réaction aux Photos",
            color=Colors.INFO.value
        )
        for c in channels:
            ch = interaction.guild.get_channel(c["channel_id"])
            ch_str = ch.mention if ch else f"`#{c['channel_id']}`"
            mode = "📸 Photos uniquement" if c.get("photos_only", 1) else "💬 Tous les messages"
            emojis_str = " ".join(c.get("emojis", ["❤️"]))
            embed.add_field(
                name=f"Salon {ch_str}",
                value=f"• **Réactions :** {emojis_str}\n• **Mode :** {mode}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @autoreact_group.command(name="clear", description="Supprime toutes les auto-réactions du serveur")
    async def clear_all(self, interaction: discord.Interaction):
        await self._ensure_cache()
        channels = await self.bot.db.get_autoreact_channels(interaction.guild_id)
        for c in channels:
            self._cache.pop(c["channel_id"], None)
        await self.bot.db.clear_autoreact_channels(interaction.guild_id)

        await interaction.response.send_message(
            embed=success_embed("✅ Toutes les auto-réactions ont été supprimées sur ce serveur."),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReact(bot))
