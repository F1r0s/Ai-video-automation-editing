"""
seo.py — AI-Powered SEO Package Generator (Groq / Llama 3).

Generates optimised title, description, tags, and hashtags for:
  YouTube, TikTok, Instagram, Facebook, X (Twitter)

Uses Groq's Llama 3.1 model for intelligent, unique-per-game SEO.
Falls back to template-based generation if API is unavailable.
"""

import json
import logging
from dataclasses import dataclass, field

log = logging.getLogger("seo")


@dataclass
class SEOPackage:
    title:       str
    description: str
    tags:        list[str]  = field(default_factory=list)
    hashtags:    list[str]  = field(default_factory=list)

    def hashtag_string(self) -> str:
        return " ".join(f"#{t.replace(' ', '')}" for t in self.hashtags)

    def tags_csv(self) -> str:
        return ",".join(self.tags)


class SEOGenerator:
    """
    AI-powered SEO package generator using Groq Llama 3.
    Falls back to templates if the API key is missing or the call fails.
    """

    def __init__(self, groq_key: str = ""):
        self.groq_key = groq_key
        self.groq_client = None
        if groq_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=groq_key)
            except Exception as e:
                log.warning(f"Groq client init failed: {e}")

    def generate(self, game_name: str, video_title: str = "") -> dict[str, SEOPackage]:
        """Generate SEO packages. Tries AI first, falls back to templates."""
        if self.groq_client:
            try:
                result = self._generate_ai(game_name)
                log.info("SEO generated via AI (Groq Llama 3)")
                return result
            except Exception as e:
                log.warning(f"AI SEO generation failed, using templates: {e}")
        return self._generate_templates(game_name)

    # ── AI-Powered Generation ─────────────────────────────────────────────────

    def _generate_ai(self, game_name: str) -> dict[str, SEOPackage]:
        """Use Groq Llama 3 to generate unique, optimized SEO per platform."""
        game = game_name.strip()

        prompt = f"""You are an expert social media SEO strategist for mobile gaming content.
Generate optimized SEO packages for a promotional video about "{game}" MOD/hack.

Return a valid JSON object with this EXACT structure (no extra text, ONLY JSON):
{{
  "youtube": {{
    "title": "YouTube title max 100 chars, keyword-rich, include emoji",
    "description": "YouTube description 3-5 paragraphs with emojis CTA disclaimer max 500 chars",
    "tags": ["tag1", "tag2", "up to 15 tags relevant to {game}"],
    "hashtags": ["HashTag1", "HashTag2", "4-6 hashtags WITHOUT the # symbol"]
  }},
  "tiktok": {{
    "title": "TikTok title punchy max 80 chars emoji",
    "description": "TikTok caption short viral tone max 150 chars",
    "tags": [],
    "hashtags": ["FYP", "ForYouPage", "6-8 hashtags WITHOUT #"]
  }},
  "instagram": {{
    "title": "Instagram title short max 60 chars",
    "description": "Instagram caption engaging with line breaks max 300 chars",
    "tags": [],
    "hashtags": ["up to 25 relevant hashtags WITHOUT #"]
  }},
  "facebook": {{
    "title": "Facebook title conversational max 80 chars",
    "description": "Facebook post copy conversational urgent max 250 chars",
    "tags": [],
    "hashtags": ["3 hashtags WITHOUT #"]
  }},
  "x": {{
    "title": "Tweet text max 250 chars including hashtags punchy",
    "description": "Same as title for X",
    "tags": [],
    "hashtags": ["2-3 hashtags WITHOUT #"]
  }}
}}

Rules:
- Make titles UNIQUE and catchy, not generic
- Use trending keywords for 2025 mobile gaming
- Include power words: FREE, Unlimited, Working, NEW, Secret
- Hashtags must be WITHOUT the # symbol
- YouTube description: game features, CTA, disclaimer
- TikTok: viral hook-driven tone
- Instagram: many targeted hashtags for discovery
- X: must stay under 280 chars total
- Focus ONLY on "{game}" — do not mention other games
- All content in English"""

        completion = self.groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )

        raw = completion.choices[0].message.content.strip()
        log.info(f"AI SEO response: {len(raw)} chars")

        data = json.loads(raw)

        packages = {}
        for platform in ["youtube", "tiktok", "instagram", "facebook", "x"]:
            p = data.get(platform, {})
            packages[platform] = SEOPackage(
                title=p.get("title", f"{game} MOD 2025"),
                description=p.get("description", f"Check out {game} MOD!"),
                tags=p.get("tags", []),
                hashtags=p.get("hashtags", []),
            )

        log.info(f"AI SEO packages generated for: {list(packages.keys())}")
        return packages

    # ── Template Fallback ─────────────────────────────────────────────────────

    def _generate_templates(self, game_name: str) -> dict[str, SEOPackage]:
        """Fallback template-based generation (no API needed)."""
        game   = game_name.strip()
        g_slug = game.replace(" ", "")
        g_mod  = f"{game} MOD"

        packages: dict[str, SEOPackage] = {}

        # ── YouTube ───────────────────────────────────────────────────────────
        yt_title = (
            f"{g_mod} 2025 — FREE Download | Unlimited Money & Resources 🔥"
        )
        yt_desc = f"""🎮 {g_mod} — Unlock Everything for FREE in 2025!

In this video we show you the latest working mod for {game}.
✅ Unlimited Money / Gold
✅ Unlimited Resources
✅ No Ban / Anti-cheat bypass
✅ iOS & Android compatible

👇 Get the MOD here 👇
[Link in description / Pinned Comment]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 Subscribe for daily MOD updates!
👍 Like if this helped you
💬 Comment your username for a shoutout
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ DISCLAIMER: This video is for educational purposes only.
All trademarks belong to their respective owners.

#shorts #{g_slug}MOD #{g_slug} #GameMod #MobileGaming
"""
        yt_tags = [
            g_mod, game, f"{game} cheats", f"{game} hack",
            "mobile game mod", "free mod apk", "android mod",
            "ios mod", "unlimited money", "game cheat 2025",
            f"{game} unlimited resources", "mod menu",
            "mobile gaming", "gaming shorts", "free download",
        ]
        packages["youtube"] = SEOPackage(
            title       = yt_title,
            description = yt_desc,
            tags        = yt_tags,
            hashtags    = [f"{g_slug}MOD", g_slug, "Shorts", "GameMod"],
        )

        # ── TikTok ────────────────────────────────────────────────────────────
        tt_title = f"🔥 {g_mod} — FREE Unlimited Everything! 👇"
        tt_desc  = (
            f"Get the working {g_mod} now! Tap the link in bio 🔗 "
            f"No ban, no root needed. Works on iOS & Android ✅"
        )
        packages["tiktok"] = SEOPackage(
            title       = tt_title,
            description = tt_desc,
            hashtags    = [
                f"{g_slug}MOD", g_slug, "GameMod", "MobileGaming",
                "FYP", "ForYouPage", "GameHack", "AndroidMod",
            ],
        )

        # ── Instagram ─────────────────────────────────────────────────────────
        ig_caption = (
            f"🎮 {g_mod} — Unlimited everything, no ban! 🔥\n\n"
            f"Link in bio to get the FREE mod now 👇\n"
            f"Works on Android & iOS ✅\n\n"
        )
        ig_hashtags = [
            g_slug, f"{g_slug}MOD", "MobileGaming", "GameMod", "ModAPK",
            "AndroidGaming", "iOSGaming", "GameHack", "FreeDownload",
            "Gaming", "GamerLife", "MobileGame", "GameCheat", "Reels",
            "InstagramReels", "Viral", "FYP", "Trending", "2025Gaming",
            "UnlimitedMoney", "UnlimitedGems", "GamePlay", "Gamer",
            "GamersOfInstagram", "GamingCommunity",
        ]
        packages["instagram"] = SEOPackage(
            title       = f"{g_mod} — FREE Unlimited!",
            description = ig_caption,
            hashtags    = ig_hashtags,
        )

        # ── Facebook ──────────────────────────────────────────────────────────
        fb_desc = (
            f"🚨 The {g_mod} is live and WORKING in 2025! 🚨\n\n"
            f"Unlimited money, gems, and resources — no root, no ban. "
            f"Grab it while it's still available! Link in the first comment 👇\n\n"
            f"📲 Works on Android & iOS"
        )
        packages["facebook"] = SEOPackage(
            title       = f"{g_mod} 2025 — Still Working! 🔥",
            description = fb_desc,
            hashtags    = [g_slug, "GameMod", "MobileGaming"],
        )

        # ── X (Twitter) ──────────────────────────────────────────────────────
        x_text = (
            f"🔥 {g_mod} just dropped — unlimited everything, no ban! "
            f"Grab it free 👇 "
            f"#{g_slug}MOD #MobileGaming #GameMod"
        )
        if len(x_text) > 280:
            x_text = x_text[:277] + "…"

        packages["x"] = SEOPackage(
            title       = x_text,
            description = x_text,
            hashtags    = [f"{g_slug}MOD", "MobileGaming", "GameMod"],
        )

        log.info(f"Template SEO packages generated for: {list(packages.keys())}")
        return packages
