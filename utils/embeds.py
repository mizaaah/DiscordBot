import discord
from utils.colors import Colors


def error_embed(description: str, title: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=Colors.ERROR)


def success_embed(description: str, title: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=Colors.SUCCESS)


def warning_embed(description: str, title: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=Colors.WARNING)


def info_embed(description: str, title: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=Colors.INFO)
