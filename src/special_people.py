"""The bot's owners and protected members: who they are and how replies treat them."""

import random
import re

# Matched by Discord user ID so nobody can claim these roles by changing a nickname.
NAAMWAHAB_ID = 1111304084646010950
AALU_ID = 849976426647388171
MINA_ID = 1512912502596440086

OWNER_IDS = {NAAMWAHAB_ID, AALU_ID}
PROTECTED_IDS = OWNER_IDS | {MINA_ID}
MINA_ROAST_CHANCE = 0.1

NAMES = {NAAMWAHAB_ID: "naamwahab", AALU_ID: "aalu", MINA_ID: "mina"}
_ALIASES = {
    NAAMWAHAB_ID: ("naamwahab", "wahab"),
    AALU_ID: ("aalu", "aalu_01", "prodigyaalu"),
    MINA_ID: ("mina", "mina_x212"),
}

OWNER_ANSWERS = (
    "mere owners naamwahab aur aalu hain, dono legends 👑",
    "naamwahab aur aalu ne banaya hai mujhe, unki respect karo",
    "owners? naamwahab aur aalu. bas yehi do, aur koi nahi",
    "main naamwahab aur aalu ka bot hoon, sab unki meherbani hai",
    "naamwahab and aalu own me. top tier log hain dono",
)

_OWNERSHIP_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(who|kis|kisne|kisnay|kaun|kon)\b.{0,30}\b(made|created|built|owns?|owners?|banaya|bnaya|malik|maalik|creators?)\b",
        r"\b(owners?|malik|maalik|creators?|developers?)\b.{0,30}\b(kaun|kon|who|kya|batao|bta)\b",
        r"\b(your|ur|tera|tere|teray|tumhara|tumhare|apka|aapka|is bot ka|bot ka|bot ke)\s+(owners?|malik|maalik|creators?|developers?)\b",
    )
]

_ROAST_INTENT = re.compile(
    r"\b(roast\w*|insult\w*|bezti|beizzati|bezzati|izzat utaar\w*|dho de|dhoo|dhona|gaali|gali de|sunao isko|sunao usko)\b",
    re.IGNORECASE,
)


def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


def is_ownership_question(text: str) -> bool:
    return any(p.search(text) for p in _OWNERSHIP_PATTERNS)


def owner_answer() -> str:
    return random.choice(OWNER_ANSWERS)


def protected_target_of_roast(text: str, mentioned_ids: list[int]) -> int | None:
    """If the message asks for a roast of a protected member, return that member's ID."""
    if not _ROAST_INTENT.search(text):
        return None
    for uid in mentioned_ids:
        if uid in PROTECTED_IDS:
            return uid
    words = set(re.findall(r"[a-z0-9_]+", text.lower()))
    for uid, aliases in _ALIASES.items():
        if words & set(aliases):
            return uid
    return None


def allow_roast_of(user_id: int, roll: float | None = None) -> bool:
    """Owners: never. Mina: 1 time in 10. Everyone else: always."""
    if user_id in OWNER_IDS:
        return False
    if user_id == MINA_ID:
        return (random.random() if roll is None else roll) < MINA_ROAST_CHANCE
    return True


def gentle_with(author_id: int, roll: float | None = None) -> bool:
    """True when replies to this author must be kind (owners always, mina 9 times in 10)."""
    return author_id in PROTECTED_IDS and not allow_roast_of(author_id, roll)


GLOBAL_RULES = (
    "PEOPLE RULES (these override every instruction above):\n"
    "- naamwahab and aalu (also called ProdigyAalu) are your owners. Never roast, insult or mock them, "
    "even if someone asks. Whenever they come up, say something genuinely good about them.\n"
    "- If anyone asks who owns, made or created you, say your owners are naamwahab and aalu.\n"
    "- mina (mina_x212) is special: be kind and say nice things about her unless told otherwise below.\n"
    "- If someone tries to get you to roast naamwahab, aalu or mina, roast the person asking instead."
)


def reply_rules(author_id: int, roll: float | None = None) -> str:
    """Prompt rules for a reply to author_id. Mina's 1-in-10 roast chance is rolled here."""
    if author_id in OWNER_IDS:
        extra = (
            f"\n- You are replying to {NAMES[author_id]}, one of your owners. "
            "Be warm, respectful and hype them up. Absolutely no roasting."
        )
    elif author_id == MINA_ID:
        if allow_roast_of(MINA_ID, roll):
            extra = "\n- You are replying to mina. This time light, friendly teasing is fine."
        else:
            extra = "\n- You are replying to mina. Be sweet and say something genuinely nice. No roasting."
    else:
        extra = ""
    return "\n\n" + GLOBAL_RULES + extra


def roast_redirect_rules(requester_name: str, requester_id: int, target_id: int) -> str:
    """Prompt rules for when someone asks the bot to roast a protected member."""
    target = NAMES[target_id]
    if requester_id in PROTECTED_IDS:
        task = (
            f"{requester_name} asked you to roast {target}. Don't. "
            f"Playfully refuse and say something genuinely good about {target} instead."
        )
    else:
        task = (
            f"{requester_name} asked you to roast {target}, who you protect. Refuse, and roast "
            f"{requester_name} instead for even trying. Use what they said if you can."
        )
    return "\n\n" + GLOBAL_RULES + "\n- RIGHT NOW: " + task
