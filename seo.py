"""
seo.py — Per-platform SEO package generator.

Generates optimised title, description, tags, and hashtags for:
  YouTube, TikTok, Instagram, Facebook, X (Twitter)
"""

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
    Builds platform-specific SEO packages.
    Platform algorithms differ significantly:
      - YouTube   → keyword-rich title + long description + tags CSV
      - TikTok    → punchy title + 3–5 relevant hashtags
      - Instagram → caption + up to 30 hashtags
      - Facebook  → conversational copy + 3 hashtags
      - X         → ≤280 chars tweet text + 2–3 hashtags
    """

    def generate(self, game_name: str, video_title: str = "") -> dict[str, SEOPackage]:
        game   = game_name.strip()
        g_slug = game.replace(" ", "")          # e.g. "OneStateRP"
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
        # Enforce 280-char limit
        if len(x_text) > 280:
            x_text = x_text[:277] + "…"

        packages["x"] = SEOPackage(
            title       = x_text,
            description = x_text,
            hashtags    = [f"{g_slug}MOD", "MobileGaming", "GameMod"],
        )

        log.info(f"SEO packages generated for: {list(packages.keys())}")
        return packages
