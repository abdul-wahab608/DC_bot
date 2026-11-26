"""Long-term memory of facts about each user: storage, decay, retrieval and the /memory commands."""

import base64
import math
import re
import struct
import time

import discord
from discord import app_commands

try:
    from api_helpers import fetch_embeddings, fetch_fact_updates
    from logging_config import get_logger
except ImportError:
    from .api_helpers import fetch_embeddings, fetch_fact_updates
    from .logging_config import get_logger

logger = get_logger(__name__)

MAX_FACTS = 30
HALF_LIFE_DAYS = 45
_DAY = 86400

# Backstop for the extraction prompt's "never record" rule.
_SENSITIVE_PATTERN = re.compile(
    r"\b(depress\w*|anxiety|therapy|therapist|suicid\w*|self[- ]harm|disorder|diagnos\w*|"
    r"medication|illness|disease|cancer|pregnan\w*|religio\w*|sect|shia|sunni|ahmadi\w*|"
    r"atheis\w*|politic\w*|pti|pmln|ppp|gay|lesbian|bisexual|sexuality|divorce\w*|"
    r"debt|loan|salary|address|phone)\b",
    re.IGNORECASE,
)


def is_sensitive(text: str) -> bool:
    return bool(_SENSITIVE_PATTERN.search(text))


def encode_vec(vec: list[float]) -> str:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return base64.b64encode(struct.pack(f"<{len(vec)}e", *(x / norm for x in vec))).decode()


def decode_vec(blob: str) -> list[float]:
    raw = base64.b64decode(blob)
    return list(struct.unpack(f"<{len(raw) // 2}e", raw))


def strength(fact: dict, now: float) -> float:
    """1.0 when just learned or confirmed, halving every HALF_LIFE_DAYS; repeated confirmations slow the decay."""
    age_days = max(0.0, now - fact.get("ts", now)) / _DAY
    half_life = HALF_LIFE_DAYS * min(fact.get("seen", 1), 4)
    return 0.5 ** (age_days / half_life)


def apply_fact_updates(facts: list[dict], updates: dict, now: float) -> list[dict]:
    """Merge Gemini's add/replace/confirm decisions into facts (indexes are 1-based). Returns the new list."""
    facts = [dict(f) for f in facts]
    for i in updates.get("confirm", []):
        facts[i - 1]["ts"] = now
        facts[i - 1]["seen"] = facts[i - 1].get("seen", 1) + 1
    for r in updates.get("replace", []):
        if is_sensitive(r["text"]):
            continue
        facts[r["index"] - 1] = {"text": r["text"], "topic": r["topic"], "ts": now, "seen": 1}

    known = {f["text"].lower() for f in facts}
    for a in updates.get("add", []):
        if a["text"].lower() in known or is_sensitive(a["text"]):
            continue
        known.add(a["text"].lower())
        facts.append({"text": a["text"], "topic": a["topic"], "ts": now, "seen": 1})

    if len(facts) > MAX_FACTS:
        facts = sorted(facts, key=lambda f: strength(f, now), reverse=True)[:MAX_FACTS]
    return facts


async def refresh_facts(profile: dict) -> None:
    """Update profile["facts"] from the user's recent messages, then embed any fact without a vector."""
    now = time.time()
    before = [f["text"] for f in profile.get("facts", [])]
    updates = await fetch_fact_updates(before, profile.get("recent_quotes", []))
    facts = apply_fact_updates(profile.get("facts", []), updates, now)

    missing = [f for f in facts if not f.get("vec")]
    if missing:
        vectors = await fetch_embeddings([f["text"] for f in missing])
        if vectors:
            for f, v in zip(missing, vectors):
                f["vec"] = encode_vec(v)

    # A /forget during the awaits above must win over this refresh.
    if [f["text"] for f in profile.get("facts", [])] != before:
        return
    profile["facts"] = facts


def _keyword_score(fact_text: str, msg_words: set[str]) -> float:
    fact_words = set(re.sub(r"[^\w\s]", " ", fact_text.lower()).split())
    return len(fact_words & msg_words) / (len(fact_words) or 1)


async def relevant_facts(profile: dict, message: str, k: int = 3) -> list[str]:
    """Top-k facts most related to the message: by meaning when embeddings work, else by shared words."""
    facts = profile.get("facts", [])
    if not facts:
        return []
    now = time.time()
    query = await fetch_embeddings([message]) if message.strip() else None
    qvec = None
    if query:
        qvec = decode_vec(encode_vec(query[0]))
    msg_words = set(re.sub(r"[^\w\s]", " ", message.lower()).split())

    def score(f: dict) -> float:
        if qvec and f.get("vec"):
            relevance = sum(a * b for a, b in zip(qvec, decode_vec(f["vec"])))
        else:
            relevance = _keyword_score(f["text"], msg_words)
        # Recency only breaks near-ties: relevance gaps between facts are often under 0.1.
        return relevance + 0.05 * strength(f, now)

    return [f["text"] for f in sorted(facts, key=score, reverse=True)[:k]]


def memory_paused(profile: dict | None) -> bool:
    return bool(profile and profile.get("opted_out"))


def _age_label(ts: float, now: float) -> str:
    days = int((now - ts) // _DAY)
    return "today" if days <= 0 else f"{days}d ago"


def setup_memory_commands(bot, profiles: dict, store, min_messages: int) -> None:
    """Register /memory, /forget and /rememberme. Changes are saved to disk immediately."""

    @bot.tree.command(name="memory", description="See what the bot remembers about you (only you can see it)")
    async def memory(interaction: discord.Interaction):
        profile = profiles.get(str(interaction.user.id))
        if memory_paused(profile):
            await interaction.response.send_message(
                "I'm not remembering anything about you. Use `/rememberme` to turn it back on.", ephemeral=True
            )
            return
        if not profile:
            await interaction.response.send_message("I don't know anything about you yet.", ephemeral=True)
            return

        now = time.time()
        count = profile.get("message_count", 0)
        lines = [f"**Messages seen:** {count}"]
        if count < min_messages:
            lines.append(f"Personal replies start after {min_messages} messages.")
        facts = profile.get("facts", [])
        if facts:
            lines.append("**What I remember:**")
            lines += [f"`{i}.` {f['text']} ({_age_label(f.get('ts', now), now)})" for i, f in enumerate(facts, 1)]
            lines.append("Use `/forget fact:<number>` to remove one, or `/forget` to wipe everything.")
        else:
            lines.append("No facts saved yet.")
        await interaction.response.send_message("\n".join(lines)[:1990], ephemeral=True)

    @bot.tree.command(name="forget", description="Delete one remembered fact, or everything the bot knows about you")
    @app_commands.describe(fact="Fact number from /memory. Leave empty to delete everything and stop remembering.")
    async def forget(interaction: discord.Interaction, fact: int | None = None):
        user_id = str(interaction.user.id)
        profile = profiles.get(user_id)
        if fact is not None:
            facts = (profile or {}).get("facts", [])
            if not 1 <= fact <= len(facts):
                await interaction.response.send_message("No fact with that number. Check `/memory`.", ephemeral=True)
                return
            removed = facts.pop(fact - 1)
            await store.save(profiles)
            await interaction.response.send_message(f"Forgot: {removed['text']}", ephemeral=True)
            return

        profiles[user_id] = {"opted_out": True}
        await store.save(profiles)
        logger.info("user memory wiped", extra={"user_id": user_id})
        await interaction.response.send_message(
            "Done. I deleted everything I knew about you and won't learn more. "
            "Use `/rememberme` if you change your mind.",
            ephemeral=True,
        )

    @bot.tree.command(name="rememberme", description="Let the bot learn about you again after /forget")
    async def rememberme(interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if not memory_paused(profiles.get(user_id)):
            await interaction.response.send_message("I'm already remembering you.", ephemeral=True)
            return
        del profiles[user_id]
        await store.save(profiles)
        await interaction.response.send_message("Okay, I'll start learning about you again.", ephemeral=True)
