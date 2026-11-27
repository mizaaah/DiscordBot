import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors


def make_bar(score: int) -> str:
    filled = max(0, min(10, round(score / 10)))
    empty = 10 - filled
    if score >= 85:
        return "🟩" * filled + "⬛" * empty
    elif score >= 65:
        return "🟨" * filled + "⬛" * empty
    elif score >= 50:
        return "🟧" * filled + "⬛" * empty
    else:
        return "🟥" * filled + "⬛" * empty


class SecurityAuditView(discord.ui.LayoutView):
    def __init__(self, cog: "SecurityAudit", guild: discord.Guild):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild

    @discord.ui.button(label="🔄 Réanalyser", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        container = await self.cog._perform_audit(self.guild)
        self.clear_items()
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.refresh))
        await interaction.edit_original_response(view=self)


class SecurityAudit(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _perform_audit(self, guild: discord.Guild) -> discord.ui.Container:
        score = 100
        critical = []
        warnings = []
        positives = []

        # ── 1. Analyse du rôle @everyone ─────────────────────────────────────
        ev_perms = guild.default_role.permissions

        if ev_perms.administrator:
            score -= 40
            critical.append("Le rôle `@everyone` a les permissions **Administrateur** ! N'importe qui peut détruire le serveur.")
        if ev_perms.manage_guild or ev_perms.manage_roles or ev_perms.manage_channels:
            score -= 30
            critical.append("Le rôle `@everyone` a la permission de gérer le serveur, les rôles ou les salons.")
        if ev_perms.ban_members or ev_perms.kick_members:
            score -= 25
            critical.append("Le rôle `@everyone` a la permission d'expulser ou bannir des membres.")
        if ev_perms.mention_everyone:
            score -= 15
            critical.append("Le rôle `@everyone` peut mentionner `@everyone` et `@here` (risque élevé de spam).")
        if ev_perms.manage_messages:
            score -= 15
            critical.append("Le rôle `@everyone` peut supprimer ou modifier les messages des autres.")
        if ev_perms.manage_webhooks:
            score -= 10
            warnings.append("Le rôle `@everyone` peut créer et modifier des Webhooks.")

        if not critical and not any("everyone" in w for w in warnings):
            positives.append("Le rôle `@everyone` a des permissions sécurisées et restreintes.")

        # ── 2. Administrateurs et Rôles Élevés ────────────────────────────────
        admin_roles = [r for r in guild.roles if r.permissions.administrator and not r.is_default()]
        admin_humans = set()
        admin_bots = set()

        for m in guild.members:
            if m.guild_permissions.administrator:
                if m.bot:
                    admin_bots.add(m)
                else:
                    admin_humans.add(m)

        if len(admin_roles) > 4:
            score -= 10
            warnings.append(f"**{len(admin_roles)} rôles** possèdent la permission Administrateur (recommandé: 1 à 2 max).")
        else:
            positives.append(f"Nombre de rôles administrateurs restreint ({len(admin_roles)} rôle(s)).")

        if len(admin_humans) > 5:
            score -= 10
            warnings.append(f"**{len(admin_humans)} membres humains** ont les pleins pouvoirs administrateur.")
        else:
            positives.append(f"Nombre de modérateurs admins sous contrôle ({len(admin_humans)} humain(s)).")

        # Bots avec admin
        if len(admin_bots) > 3:
            score -= 8
            warnings.append(f"**{len(admin_bots)} bots** possèdent la permission Administrateur. En cas de faille sur un bot tiers, le serveur est à risque.")
        else:
            positives.append(f"Bots administrateurs limités ({len(admin_bots)} bot(s)).")

        # ── 3. Paramètres de Sécurité Discord ────────────────────────────────
        v_level = str(guild.verification_level)
        if v_level == "none":
            score -= 15
            warnings.append("Niveau de vérification Discord sur **Aucun**. Les bots et faux comptes peuvent immédiatement parler.")
        elif v_level in ["low", "medium"]:
            positives.append("Vérification Discord active (email ou ancienneté de compte requise).")
        else:
            positives.append("Vérification Discord maximale (numéro de téléphone requis).")

        # Filtre de contenu explicite
        content_filter = str(guild.explicit_content_filter)
        if content_filter == "disabled":
            score -= 10
            warnings.append("Filtre automatique des médias explicites Discord **désactivé**.")
        else:
            positives.append("Filtre des médias explicites Discord activé.")

        # 2FA Modération
        if guild.mfa_level == discord.MFALevel.disabled:
            score -= 10
            warnings.append("La double authentification (2FA) n'est pas exigée pour les modérateurs du serveur.")
        else:
            positives.append("Double authentification (2FA) obligatoire pour l'équipe de modération.")

        # ── 4. Modules de Protection du Bot ──────────────────────────────────
        settings = await self.bot.db.get_guild_settings(guild.id)
        am_cfg = await self.bot.db.get_automod_config(guild.id)
        ar_cfg = await self.bot.db.get_antiraid_config(guild.id)
        an_cfg = await self.bot.db.get_antinuke_config(guild.id)

        # AutoMod
        if am_cfg.get("enabled"):
            positives.append("Protection **AutoMod** active (Anti-Spam / Liens / Flood).")
        else:
            score -= 12
            warnings.append("Système **AutoMod** désactivé (`/config`).")

        # Anti-Raid
        if ar_cfg.get("enabled"):
            positives.append("Protection **Anti-Raid** active (Détection des vagues de bots).")
        else:
            score -= 12
            warnings.append("Protection **Anti-Raid** désactivée (`/config`).")

        # Anti-Nuke
        if an_cfg.get("enabled"):
            positives.append("Système **Anti-Nuke** actif (Protection destruction de salons/bans de masse).")
        else:
            score -= 12
            warnings.append("Protection **Anti-Nuke** désactivée (`/config`).")

        # Logs
        if settings.get("log_category_id") or settings.get("log_mod_id"):
            positives.append("Traçage des **Logs** configuré et actif.")
        else:
            score -= 8
            warnings.append("Aucun salon de **Logs** configuré pour tracer les actions staff.")

        # Calcul final
        score = max(5, min(100, score))
        if score >= 90:
            grade = "A+"
            grade_badge = "🛡️ Excellent"
            color = Colors.SUCCESS.value
        elif score >= 80:
            grade = "A"
            grade_badge = "🟢 Très bon"
            color = Colors.SUCCESS.value
        elif score >= 65:
            grade = "B"
            grade_badge = "🟡 Bon"
            color = Colors.GOLD.value
        elif score >= 50:
            grade = "C"
            grade_badge = "🟠 Moyen"
            color = Colors.ORANGE.value
        elif score >= 30:
            grade = "D"
            grade_badge = "🔴 Faible"
            color = Colors.ERROR.value
        else:
            grade = "F"
            grade_badge = "💀 Vulnérable"
            color = Colors.ERROR.value

        bar = make_bar(score)

        # ── Construction du Container v2 ──────────────────────────────────────
        cont = discord.ui.Container(accent_color=color)

        header_text = (
            f"# 🛡️ Audit de Sécurité — {guild.name}\n"
            f"> **Score Global :** `{score}/100` — **Note :** **{grade}** ({grade_badge})\n"
            f"> `{bar}`\n"
        )
        cont.add_item(discord.ui.TextDisplay(header_text))
        cont.add_item(discord.ui.Separator())

        # Alertes critiques
        if critical:
            crit_text = "### 🚨 Failles Critiques Détectées\n" + "\n".join(f"- 🔴 {c}" for c in critical)
            cont.add_item(discord.ui.TextDisplay(crit_text))
            cont.add_item(discord.ui.Separator())

        # Avertissements
        if warnings:
            warn_text = "### ⚠️ Points d'Attention & Risques\n" + "\n".join(f"- 🟡 {w}" for w in warnings)
            cont.add_item(discord.ui.TextDisplay(warn_text))
            cont.add_item(discord.ui.Separator())

        # Points forts
        if positives:
            pos_text = "### ✅ Mesures de Sécurité Appliquées\n" + "\n".join(f"- 🟢 {p}" for p in positives[:8])
            cont.add_item(discord.ui.TextDisplay(pos_text))

        return cont

    @app_commands.command(name="security-audit", description="Analyse complète de la sécurité et des failles du serveur")
    @app_commands.default_permissions(manage_guild=True)
    async def security_audit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        container = await self._perform_audit(interaction.guild)
        view = SecurityAuditView(self, interaction.guild)
        view.add_item(container)
        view.add_item(discord.ui.ActionRow(view.refresh))
        await interaction.followup.send(view=view)

    @app_commands.command(name="audit", description="Alias rapide pour lancer l'audit de sécurité")
    @app_commands.default_permissions(manage_guild=True)
    async def audit_alias(self, interaction: discord.Interaction):
        await self.security_audit(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(SecurityAudit(bot))
