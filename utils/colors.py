import discord


class Colors:
    """Palette unifiée (teintes officielles Discord) pour tous les embeds du bot."""

    SUCCESS = discord.Color(0x57F287)   # confirmations, unban, unmute, arrivée
    ERROR   = discord.Color(0xED4245)   # kick, ban, refus, suppression
    DANGER  = discord.Color(0x992D22)   # actions les plus sévères (ban auto, clear warnings)
    WARNING = discord.Color(0xE67E22)   # mute, sévérité moyenne
    CAUTION = discord.Color(0xFEE75C)   # warn, sévérité basse
    INFO    = discord.Color(0x5865F2)   # blurple, neutre/informatif
    GOLD    = discord.Color(0xFFD700)   # XP, giveaways, starboard
    NEUTRAL = discord.Color(0x95A5A6)   # gris, secondaire
    INVISIBLE = discord.Color(0x2B2D31) # couleur de fond discord sombre
