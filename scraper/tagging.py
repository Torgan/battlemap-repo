"""Heuristic tagging from a post's title + body text.

Returns tags, grid type, dimensions, and a templated description. Cheap, deterministic,
free. No image understanding — it works off the words in the post.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# category -> {tag_name: [keywords...]}.  Keywords are matched as whole-ish words.
KEYWORD_MAP: dict[str, dict[str, list[str]]] = {
    "terrain": {
        "forest": ["forest", "woods", "woodland", "grove", "jungle", "treeline"],
        "cave": ["cave", "cavern", "grotto", "underdark", "cavern"],
        "dungeon": ["dungeon", "crypt", "tomb", "catacomb", "lair", "vault"],
        "mountain": ["mountain", "cliff", "peak", "highland", "canyon", "gorge", "hill", "hilltop"],
        "swamp": ["swamp", "marsh", "bog", "fen", "mire", "wetland"],
        "desert": ["desert", "dune", "wasteland", "sand", "oasis", "badlands"],
        "snow": ["snow", "ice", "frozen", "tundra", "arctic", "winter", "glacier", "icy"],
        "coast": ["beach", "coast", "shore", "island", "cove", "bay", "cliffside", "lagoon"],
        "water": ["river", "lake", "ocean", "sea", "waterfall", "underwater", "pond", "stream", "harbor", "harbour", "dock", "docks", "port"],
        "grassland": ["plains", "grassland", "meadow", "field", "fields", "prairie", "moor"],
        "volcano": ["volcano", "lava", "magma", "volcanic"],
        "underground": ["underground", "tunnel", "tunnels", "mine", "mineshaft", "cellar"],
    },
    "setting": {
        "tavern": ["tavern", "inn", "pub", "alehouse", "bar"],
        "city": ["city", "town", "village", "market", "marketplace", "street", "plaza", "slum", "district"],
        "castle": ["castle", "keep", "fortress", "citadel", "palace", "stronghold", "rampart", "bastion"],
        "temple": ["temple", "shrine", "church", "cathedral", "sanctuary", "monastery", "chapel", "altar"],
        "ship": ["ship", "boat", "galleon", "vessel", "deck", "pirate", "frigate", "sloop", "barge"],
        "ruins": ["ruin", "ruins", "abandoned", "derelict", "overgrown", "decayed"],
        "house": ["house", "manor", "mansion", "cottage", "estate", "villa", "homestead", "cabin"],
        "camp": ["camp", "campsite", "encampment", "warcamp", "bandit camp"],
        "farm": ["farm", "farmstead", "barn", "orchard", "vineyard", "ranch", "windmill", "mill"],
        "sewer": ["sewer", "sewers", "drain"],
        "library": ["library", "archive", "study"],
        "prison": ["prison", "jail", "dungeon cell", "cell block", "gaol"],
        "graveyard": ["graveyard", "cemetery", "mausoleum", "necropolis", "crypt"],
        "arena": ["arena", "colosseum", "coliseum", "pit"],
        "laboratory": ["laboratory", "lab", "alchemist", "workshop", "forge", "smithy"],
        "throne": ["throne", "throne room", "court"],
        "bridge": ["bridge", "crossing", "viaduct"],
        "garden": ["garden", "courtyard", "greenhouse"],
    },
    "feature": {
        "scifi": ["sci-fi", "scifi", "spaceship", "starship", "space station", "cyberpunk", "futuristic", "android"],
        "modern": ["modern", "contemporary", "warehouse", "office", "rooftop", "subway", "parking"],
        "magical": ["magical", "arcane", "wizard tower", "enchanted", "fey", "feywild", "portal", "rune", "runes"],
        "tower": ["tower", "spire", "lighthouse", "ziggurat", "obelisk"],
        "battlefield": ["battlefield", "siege", "warzone", "ruined wall"],
        "horror": ["horror", "haunted", "cursed", "blood", "eldritch", "nightmare", "undead"],
        "monster": ["dragon", "mind flayer", "illithid", "beholder", "lich", "demon", "devil", "kraken", "giant", "goblin", "orc", "troll", "hag", "vampire", "skeleton", "dragon's"],
    },
}

# Precompile a word-boundary matcher per tag so e.g. "bar" doesn't match "barn"
# and "ice" doesn't match "service".
_TAG_MATCHERS: list[tuple[str, str, re.Pattern]] = [
    (tag_name, category,
     re.compile(r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")\b", re.I))
    for category, mapping in KEYWORD_MAP.items()
    for tag_name, kws in mapping.items()
]

DIM_RE = re.compile(r"\b(\d{1,3})\s*[x×X]\s*(\d{1,3})\b")
GRIDLESS_RE = re.compile(r"grid[\s-]*less|no\s*grid|gridless", re.I)
GRID_RE = re.compile(r"\bgrid(ded|s)?\b", re.I)

_GRID_WORD = {"grid": "gridded", "gridless": "gridless", "unknown": ""}


@dataclass
class TagResult:
    tags: list[tuple[str, str]] = field(default_factory=list)  # (name, category)
    grid_type: str = "unknown"   # grid | gridless | unknown
    dimensions: str | None = None
    description: str | None = None


def heuristic_tags(title: str, body: str | None = None, flair: str | None = None) -> TagResult:
    text = f"{title} {body or ''} {flair or ''}"
    result = TagResult()

    for tag_name, category, matcher in _TAG_MATCHERS:
        if matcher.search(text):
            result.tags.append((tag_name, category))

    # Grid (only look at title/flair for grid words; bodies often mention "grid" generically)
    grid_text = f"{title} {flair or ''}".lower()
    if GRIDLESS_RE.search(grid_text):
        result.grid_type = "gridless"
    elif GRID_RE.search(grid_text):
        result.grid_type = "grid"

    # Dimensions like 30x20 (prefer the title)
    m = DIM_RE.search(title) or DIM_RE.search(body or "")
    if m:
        result.dimensions = f"{m.group(1)}x{m.group(2)}"

    return result


def build_description(
    title: str,
    tags: list[tuple[str, str]],
    dimensions: str | None,
    grid_type: str,
    subreddit: str,
    author: str | None,
) -> str:
    """A short, factual templated description from the metadata we have."""
    grid_word = _GRID_WORD.get(grid_type, "")
    size = dimensions or ""
    descriptor = " ".join(p for p in [size, grid_word] if p).strip()
    lead = f"A {descriptor} battlemap" if descriptor else "A battlemap"

    feature_tags = [name for name, cat in tags if cat != "grid"]
    if feature_tags:
        lead += " featuring " + ", ".join(feature_tags[:5])

    attribution = (
        f" Shared by u/{author} on r/{subreddit}." if author else f" From r/{subreddit}."
    )
    return lead + "." + attribution
