import asyncio
import platform
import time

import discord
from discord.ext import commands

OWNER_COMMANDS = [
    ("+help", "Affiche cette aide (répond uniquement à toi, invisible pour les autres)."),
    ("+servers", "Liste tous les serveurs où le bot est installé."),
    ("+stats", "Statistiques globales du bot (serveurs, membres, latence, uptime)."),
    ("+sync", "Resynchronise les commandes slash globalement (propagation Discord ~1h)."),
    ("+sync here", "Resynchronise les commandes slash instantanément sur CE serveur (pour tester sans attendre)."),
    ("+reload <cog>", "Recharge un cog à chaud sans redémarrer le bot (ex: +reload moderation)."),
    ("+leaveguild <id>", "Fait quitter un serveur précis au bot."),
    ("+dmall <message>", "DM tous les membres du serveur actuel, avec délai anti rate-limit et rapport final."),
    ("+shutdown", "Arrête proprement le bot."),
]


def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds    = divmod(seconds, 86400)
    hours, seconds   = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:    parts.append(f"{days}j")
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


class Owner(commands.Cog):
    """Commandes cachées réservées au propriétaire du bot (préfixe +)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.monotonic()

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="help")
    async def owner_help(self, ctx: commands.Context):
        embed = discord.Embed(title="🔧 Commandes owner", color=discord.Color.dark_grey())
        for name, desc in OWNER_COMMANDS:
            embed.add_field(name=name, value=desc, inline=False)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(embed=embed)

    @commands.command(name="servers")
    async def owner_servers(self, ctx: commands.Context):
        lines = [
            f"{g.id} — {g.name} — {g.member_count} membres — owner: {g.owner}"
            for g in self.bot.guilds
        ]
        text = "\n".join(lines) or "Aucun serveur."
        for i in range(0, len(text), 1900):
            await ctx.send(f"```\n{text[i:i + 1900]}\n```")

    @commands.command(name="stats")
    async def owner_stats(self, ctx: commands.Context):
        embed = discord.Embed(title="📊 Statistiques du bot", color=discord.Color.dark_grey())
        embed.add_field(name="Serveurs",       value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Membres totaux", value=str(sum(g.member_count or 0 for g in self.bot.guilds)), inline=True)
        embed.add_field(name="Latence",        value=f"{round(self.bot.latency * 1000)} ms", inline=True)
        embed.add_field(name="Uptime",         value=_fmt_uptime(time.monotonic() - self.start_time), inline=True)
        embed.add_field(name="discord.py",     value=discord.__version__, inline=True)
        embed.add_field(name="Python",         value=platform.python_version(), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="sync")
    async def owner_sync(self, ctx: commands.Context, scope: str = None):
        if scope == "here":
            if not ctx.guild:
                return await ctx.send("❌ À utiliser dans un serveur.")
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"✅ {len(synced)} commande(s) synchronisée(s) instantanément sur **{ctx.guild.name}**.")
        else:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ {len(synced)} commande(s) synchronisée(s) globalement (propagation Discord ~1h).")

    @commands.command(name="reload")
    async def owner_reload(self, ctx: commands.Context, cog: str):
        ext = f"cogs.{cog}"
        try:
            await self.bot.reload_extension(ext)
        except commands.ExtensionError as e:
            return await ctx.send(f"❌ Échec du rechargement de `{ext}` : `{e}`")
        await ctx.send(f"✅ `{ext}` rechargé.")

    @commands.command(name="leaveguild")
    async def owner_leaveguild(self, ctx: commands.Context, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.send(f"❌ Serveur `{guild_id}` introuvable.")
        name = guild.name
        await guild.leave()
        await ctx.send(f"✅ Le bot a quitté **{name}** (`{guild_id}`).")

    @commands.command(name="shutdown")
    async def owner_shutdown(self, ctx: commands.Context):
        await ctx.send("🛑 Arrêt du bot...")
        await self.bot.close()

    @commands.command(name="dmall")
    async def owner_dmall(self, ctx: commands.Context, *, message: str):
        if not ctx.guild:
            return await ctx.send("❌ À utiliser dans un serveur.")
        members = [m for m in ctx.guild.members if not m.bot]
        await ctx.send(
            f"📨 Envoi à **{len(members)}** membre(s) de **{ctx.guild.name}**...\n"
            f"Délai anti rate-limit activé, ça va prendre environ {round(len(members) * 1.5 / 60, 1)} min."
        )

        sent, failed = 0, 0
        for member in members:
            try:
                await member.send(f"📢 **Message de {ctx.guild.name} :**\n\n{message}")
                sent += 1
            except (discord.Forbidden, discord.HTTPException):
                failed += 1
            await asyncio.sleep(1.5)

        await ctx.send(f"✅ Terminé. **{sent}** envoyé(s), **{failed}** échoué(s) (DM fermés ou autre erreur).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Owner(bot))
