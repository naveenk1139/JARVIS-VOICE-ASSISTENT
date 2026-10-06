"""Opening websites, web searches, maps and music."""

from __future__ import annotations

import os
import re
from pathlib import Path

from ..models import Match, Response
from ..services.youtube import search_url
from .base import Skill

#: Friendly name -> URL. Extend freely; keys are matched against the utterance.
SITES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "gmail": "https://mail.google.com",
    "amazon": "https://www.amazon.in",
    "flipkart": "https://www.flipkart.com",
    "wikipedia": "https://en.wikipedia.org",
    "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "instagram": "https://www.instagram.com",
    "whatsapp": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "hacker news": "https://news.ycombinator.com",
    "hackernews": "https://news.ycombinator.com",
    "arena": "https://arena.ai",
}

_DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


class WebSkill(Skill):
    name = "web"
    description = "Open websites, run web searches, look up maps and play local music."
    priority = 50
    examples = (
        "Open YouTube",
        "Search for ISRO Chandrayaan",
        "Search YouTube for lo-fi beats",
        "Where is Cubbon Park on the map?",
        "Play music",
    )
    patterns = (
        r"^(?P<youtube>search youtube for|youtube search for|find on youtube|play on youtube)\s+(?P<query>.+)$",
        r"^(?P<youtube>youtube)\s+(?P<query>.+)$",
        r"^(?P<open>open|launch|go to|take me to)\s+(?P<site>[a-z0-9 .'-]+?)\s*(?:website|site|dot com|\.com)?$",
        r"^(?P<search>search|google|look ?up)\s+(?:for\s+|about\s+)?(?P<query>.+?)(?:\s+on google|\s+online)?$",
        r"^(?P<maps>map|directions to|navigate to|where is)\s+(?P<place>.+?)(?:\s+on the map|\s+on maps?)?$",
        r"^(?P<music>play (?:some )?music|play a song|play my playlist)\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        groups = match.groups

        if "youtube" in groups:
            query = match.group("query").strip()
            return Response.link(
                f"Opening YouTube results for {query}.",
                url=search_url(query),
                data={"query": query, "site": "youtube"},
            )
        if "maps" in groups:
            place = match.group("place").strip(" ?.!,")
            url = "https://www.google.com/maps/search/" + place.replace(" ", "+")
            return Response.link(f"Showing {place} on Google Maps.", url=url, data={"place": place})
        if "search" in groups:
            query = match.group("query").strip(" ?.!,")
            url = "https://www.google.com/search?q=" + query.replace(" ", "+")
            return Response.link(f"Here is what I found for {query}.", url=url, data={"query": query})
        if "music" in groups:
            return self._play_music()

        site = match.group("site").strip(" ,.").lower()
        return self._open_site(site)

    # ----------------------------------------------------------------- helpers
    def _open_site(self, site: str) -> Response:
        url = SITES.get(site)
        if url is None:
            if _DOMAIN.match(site):
                url = site if site.startswith("http") else f"https://{site}"
            else:
                for key, candidate in SITES.items():
                    if key in site or site in key:
                        url = candidate
                        break
        if url is None:
            query = site.replace(" ", "+")
            return Response.link(
                f"I do not know {site} by heart, so here is a search for it.",
                url=f"https://www.google.com/search?q={query}",
                data={"query": site, "fallback": True},
            )
        return Response.link(f"Opening {site}.", url=url, data={"site": site})

    def _play_music(self) -> Response:
        music_dir = (self.ctx.config.music_dir or "").strip()
        if not music_dir:
            return Response.error(
                "Set JARVIS_MUSIC_DIR to a folder of audio files and I will play it. "
                "This is only possible in the desktop app, not in the browser.",
                data={"setting": "JARVIS_MUSIC_DIR"},
            )
        folder = Path(os.path.expanduser(music_dir))
        if not folder.is_dir():
            return Response.error(f"The music folder {folder} does not exist.")
        tracks = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"})
        if not tracks:
            return Response.error(f"No audio files found in {folder}.")
        return Response.ok(
            f"I found {len(tracks)} tracks. The desktop app can start playback; "
            f"in the browser, open one of these files manually: {tracks[0].name}",
            data={"tracks": [str(t) for t in tracks[:20]], "desktop_only": True},
        )
