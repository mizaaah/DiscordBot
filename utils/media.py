import re
import logging
import aiohttp

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


async def resolve_media_url(url: str) -> str:
    """
    Résout les URLs de médias (notamment les pages de partage Klipy, Tenor, Giphy)
    en liens directs vers les fichiers média (GIF, WebP, MP4, PNG, etc.) exploitables
    par les composants Discord MediaGallery / Embeds.
    """
    if not url or not isinstance(url, str):
        return url

    url = url.strip()

    # Si c'est déjà un lien direct vers une image/vidéo
    clean_url = url.split("?")[0].lower()
    if clean_url.endswith((".gif", ".png", ".jpg", ".jpeg", ".webp", ".mp4")):
        return url

    # ── 1. Résolution Klipy (ex: https://klipy.com/gifs/stars-sky-9) ─────────
    klipy_match = re.search(r"klipy\.com/(gifs|stickers|memes|watch)/([a-zA-Z0-9_\-]+)", url, re.IGNORECASE)
    if klipy_match:
        media_type = klipy_match.group(1).lower()
        if media_type == "watch":
            media_type = "gifs"
        slug = klipy_match.group(2)
        api_url = f"https://klipy.com/api/proxy/{media_type}/{slug}"

        try:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/json"
            }
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(api_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        file_info = data.get("data", {}).get("file", {})
                        
                        # Priorité au GIF direct (HD > MD > SM) puis WebP / MP4
                        direct = (
                            file_info.get("hd", {}).get("gif", {}).get("url")
                            or file_info.get("md", {}).get("gif", {}).get("url")
                            or file_info.get("sm", {}).get("gif", {}).get("url")
                            or file_info.get("hd", {}).get("webp", {}).get("url")
                            or file_info.get("md", {}).get("webp", {}).get("url")
                            or file_info.get("hd", {}).get("mp4", {}).get("url")
                        )
                        if direct:
                            logger.info(f"Klipy URL '{url}' résolue avec succès -> '{direct}'")
                            return direct
        except Exception as e:
            logger.warning(f"Échec de la résolution Klipy pour '{url}': {e}")

    # ── 2. Résolution Tenor / Giphy (extraction og:image de la page HTML) ─────
    if "tenor.com" in url or "giphy.com" in url:
        try:
            headers = {"User-Agent": USER_AGENT}
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        og_match = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
                        if not og_match:
                            og_match = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', html, re.IGNORECASE)
                        if og_match:
                            direct = og_match.group(1).replace("&amp;", "&")
                            logger.info(f"Media URL '{url}' résolue via og:image -> '{direct}'")
                            return direct
        except Exception as e:
            logger.warning(f"Échec de la résolution HTML pour '{url}': {e}")

    # Fallback : retourner l'URL d'origine
    return url
