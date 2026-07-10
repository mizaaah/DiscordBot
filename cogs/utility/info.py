import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from utils.colors import Colors
from utils.i18n import t



# ══════════════════════════════════════════════════════════════════════════════
#  Help UI (V2)
# ══════════════════════════════════════════════════════════════════════════════

HELP_CATEGORIES = {
    "home": {
        "title": "📚 Centre d'Aide",
        "desc": "Sélectionnez une catégorie ci-dessous pour voir les commandes associées.",
        "emoji": "🏠"
    },
    "moderation": {
        "title": "🛡️ Modération",
        "desc": "Commandes pour gérer les membres et les salons.\n\n"
                "- `/kick` : Expulser un membre\n"
                "- `/ban` / `/unban` : Bannir ou débannir un membre\n"
                "- `/mute` / `/unmute` : Rendre muet un membre\n"
                "- `/warn` / `/warnings` / `/clearwarnings` : Gérer les avertissements\n"
                "- `/clear` : Effacer des messages\n"
                "- `/slowmode` : Activer le mode lent\n"
                "- `/lock` / `/unlock` : Verrouiller un salon",
        "emoji": "🛡️"
    },
    "automod": {
        "title": "🤖 AutoMod & Anti-Raid",
        "desc": "Systèmes de protection automatiques du serveur.\n\n"
                "- `/config` (Puis AutoMod / AntiRaid) : Configurer les systèmes\n"
                "- `/ghostping` : Activer/Désactiver la détection de ghost pings",
        "emoji": "🤖"
    },
    "xp": {
        "title": "📈 Système de Niveaux",
        "desc": "Commandes liées à l'expérience et aux niveaux.\n\n"
                "- `/rank` : Voir son niveau ou celui d'un membre\n"
                "- `/leaderboard` : Afficher le classement du serveur\n"
                "- `/setxp` / `/addxp` / `/resetxp` : Gérer l'XP des membres (Admin)\n"
                "- `/xprole add` / `remove` / `list` : Récompenses de rôles par niveau",
        "emoji": "📈"
    },
    "tickets": {
        "title": "🎟️ Système de Tickets",
        "desc": "Commandes pour le support et les tickets.\n\n"
                "- `/ticket setup` : Créer un panel de tickets (V2)\n"
                "- `/tadd` / `/tremove` : Ajouter/Retirer un membre d'un ticket\n"
                "- `/tclaim` / `/tunclaim` : Gérer la prise en charge d'un ticket",
        "emoji": "🎟️"
    },
    "roles": {
        "title": "🎭 Rôles & Sanctions",
        "desc": "Gestion avancée des rôles et sanctions automatiques.\n\n"
                "- `/rr setup` / `/rr add` / `/rr remove` : Reaction Roles (Boutons)\n"
                "- `/autosanction add` / `remove` / `list` : Sanctions automatiques selon les warns",
        "emoji": "🎭"
    },
    "community": {
        "title": "🎁 Communauté & Vocaux",
        "desc": "Outils d'interaction pour la communauté.\n\n"
                "- `/tempvoice` : Créer un panel de vocaux temporaires\n"
                "- `/giveaway start` / `reroll` / `end` / `list` : Gérer les giveaways\n"
                "- `/starboard` : Configurer le starboard\n"
                "- `/afk set` : Se mettre en mode AFK",
        "emoji": "🎁"
    },
    "config": {
        "title": "⚙️ Configuration & Infos",
        "desc": "Paramétrage global et commandes d'informations.\n\n"
                "- `/config` : Ouvrir le panel V2 (Logs, Bienvenue, Auto-Rôle, etc.)\n"
                "- `/embed create` / `edit` / `button` : Créateur d'embeds interactifs\n"
                "- `/cmdperm` : Restreindre certaines commandes\n"
                "- `/userinfo` / `/serverinfo` / `/botinfo` / `/avatar` / `/roleinfo` : Informations utiles",
        "emoji": "⚙️"
    }
}

class HelpCategorySelect(discord.ui.Select):
    def __init__(self, current_page: str):
        options = [
            discord.SelectOption(
                label=data["title"].split(" ", 1)[1] if " " in data["title"] else data["title"],
                value=key,
                emoji=data["emoji"],
                default=(key == current_page)
            ) for key, data in HELP_CATEGORIES.items()
        ]
        super().__init__(placeholder="Choisissez une catégorie d'aide...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(interaction, self.values[0])

class HelpViewV2(discord.ui.LayoutView):
    def __init__(self, default_page="home"):
        super().__init__(timeout=300)
        self.current_page = default_page

    async def show_page(self, interaction: discord.Interaction, page_key: str):
        self.current_page = page_key
        self.clear_items()
        
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        
        # Build Section
        data = HELP_CATEGORIES.get(page_key, HELP_CATEGORIES["home"])
        cont.add_item(discord.ui.TextDisplay(f"# {data['title']}\n{data['desc']}"))
        
        cont.add_item(discord.ui.ActionRow(HelpCategorySelect(page_key)))
        
        self.add_item(cont)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self, embed=None)
        else:
            await interaction.response.edit_message(view=self, embed=None)

    async def send_initial(self, interaction: discord.Interaction):
        self.clear_items()
        
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        data = HELP_CATEGORIES.get(self.current_page, HELP_CATEGORIES["home"])
        cont.add_item(discord.ui.TextDisplay(f"# {data['title']}\n{data['desc']}"))
        cont.add_item(discord.ui.ActionRow(HelpCategorySelect(self.current_page)))
        self.add_item(cont)
        
        await interaction.response.send_message(view=self, ephemeral=True)
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

    @app_commands.command(name="help", description="Affiche l'aide complète et moderne du bot")
    @app_commands.describe(commande="Aller directement à la section d'une commande précise (optionnel)")
    @app_commands.autocomplete(commande=_cmd_autocomplete)
    async def help(self, interaction: discord.Interaction, commande: str = None):
        # Pour faire correspondre la commande à une page, on garde un petit mapping simple
        cmd_map = {
            "kick": "moderation", "ban": "moderation", "warn": "moderation", "mute": "moderation", "clear": "moderation", "slowmode": "moderation", "lock": "moderation",
            "automod": "automod", "antiraid": "automod", "ghostping": "automod",
            "rank": "xp", "leaderboard": "xp", "setxp": "xp", "xprole": "xp",
            "ticket": "tickets", "tadd": "tickets",
            "rr": "roles", "autosanction": "roles",
            "tempvoice": "community", "giveaway": "community", "starboard": "community", "afk": "community",
            "config": "config", "embed": "config", "cmdperm": "config", "userinfo": "config", "serverinfo": "config"
        }
        
        page = "home"
        if commande:
            base_cmd = commande.split()[0].lower()
            page = cmd_map.get(base_cmd, "home")
            
        view = HelpViewV2(default_page=page)
        await view.send_initial(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
