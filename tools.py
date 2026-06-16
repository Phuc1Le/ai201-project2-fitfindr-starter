"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv(override=True)


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── search_listings helpers ───────────────────────────────────────────────────

_SIZE_ORDER = ["xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl"]

_STOPWORDS = {
    "a", "an", "the", "is", "in", "at", "of", "for", "and", "or",
    "but", "with", "from", "on", "to", "by", "it", "be", "as", "up",
    "no", "so", "do", "if", "its", "just", "not", "this", "that",
}


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}


def _expand_named_sizes(sz: str) -> set[str]:
    """Pull standard size labels (s/m/l/xl…) out of a composite size string."""
    return {p for p in re.split(r"[\s/()\-]+", sz.lower()) if p in _SIZE_ORDER}


def _size_matches(query: str, listing_size: str, flex: int = 1, shoe_flex: float = 0.5) -> bool:
    ql = query.lower().strip()
    ll = listing_size.lower().strip()

    if "one size" in ll:
        return True
    if ql == ll:
        return True

    # US shoe sizes
    us_q = re.match(r"us\s*(\d+\.?\d*)", ql)
    us_l = re.match(r"us\s*(\d+\.?\d*)", ll)
    if us_q and us_l:
        return abs(float(us_q.group(1)) - float(us_l.group(1))) <= shoe_flex

    # Bare number (e.g. "8") against a US-formatted listing (e.g. "US 8")
    num_q = re.match(r"^(\d+\.?\d*)$", ql)
    if num_q and us_l:
        return abs(float(num_q.group(1)) - float(us_l.group(1))) <= shoe_flex

    # Waist sizes — allow ±1 inch
    w_q = re.match(r"w(\d+)", ql)
    w_l = re.match(r"w(\d+)", ll)
    if w_q and w_l:
        return abs(int(w_q.group(1)) - int(w_l.group(1))) <= 1

    # Named sizes with ±flex steps
    q_sizes = _expand_named_sizes(ql) or {ql}
    l_sizes = _expand_named_sizes(ll) or {ll}

    if q_sizes & l_sizes:
        return True

    for qs in q_sizes:
        if qs not in _SIZE_ORDER:
            continue
        qi = _SIZE_ORDER.index(qs)
        for ls in l_sizes:
            if ls in _SIZE_ORDER and abs(qi - _SIZE_ORDER.index(ls)) <= flex:
                return True

    return False


def _score_listing(tokens: set[str], listing: dict) -> int:
    """Keyword overlap score. Higher field weights for more specific matches."""
    score = 0
    score += 3 * len(tokens & _tokenize(listing["title"]))

    tag_tokens: set[str] = set()
    for tag in listing.get("style_tags", []):
        tag_tokens |= _tokenize(tag)
    score += 2 * len(tokens & tag_tokens)

    color_tokens: set[str] = set()
    for color in listing.get("colors", []):
        color_tokens |= _tokenize(color)
    score += 2 * len(tokens & color_tokens)

    score += 2 * len(tokens & _tokenize(listing.get("category", "")))

    if listing.get("brand"):
        score += 2 * len(tokens & _tokenize(listing["brand"]))

    score += len(tokens & _tokenize(listing["description"]))
    return score


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    print("Tool search_listing used\n")
    listings = load_listings()
    tokens = _tokenize(description)

    # 1. Hard price filter
    if max_price is not None:
        price_ok = [l for l in listings if l["price"] <= max_price]
        if not price_ok:
            # Check if the description matches anything at all (ignoring price).
            # If not, the problem is the description, not the budget.
            scored_all = [(l, _score_listing(tokens, l)) for l in listings]
            relevant = [l for l, s in scored_all if s > 0]
            if not relevant:
                return {"status": "no_results", "message": "No items match that description."}
            return {
                "status": "price_too_low",
                "lowest_matching_price": min(l["price"] for l in relevant),
            }
    else:
        price_ok = listings

    # 2. Score by description
    scored = [(l, _score_listing(tokens, l)) for l in price_ok]
    desc_matched = [(l, s) for l, s in scored if s > 0]

    if not desc_matched:
        return {"status": "no_results", "message": "No items match that description."}

    # 3. Soft size filter — exact match first, flex match second (triggers size_relaxed)
    if size is not None:
        size_exact = [(l, s) for l, s in desc_matched if _size_matches(size, l["size"], flex=0, shoe_flex=0.0)]
        if size_exact:
            result_pairs = size_exact
        else:
            size_flex = [(l, s) for l, s in desc_matched if _size_matches(size, l["size"])]
            items = [l for l, _ in sorted(size_flex or desc_matched, key=lambda x: x[1], reverse=True)]
            return {"status": "size_relaxed", "items": items}
    else:
        result_pairs = desc_matched

    result_pairs.sort(key=lambda x: x[1], reverse=True)
    return [l for l, _ in result_pairs]


# ── Tool 4: check_price ──────────────────────────────────────────────────────

def check_price(item: dict) -> dict:
    """
    Compare an item's price against similar listings in the dataset.

    Args:
        item: A listing dict (the item to evaluate).

    Returns:
        {
            "verdict":                  "great_deal" | "fair" | "overpriced" | "no_comparables",
            "item_price":               float,
            "median_comparable_price":  float   (omitted for no_comparables),
            "comparable_count":         int,
            "price_range":              [min, max] (omitted for no_comparables),
        }

    Comparables are listings with the same category and at least one shared style tag,
    excluding the item itself. A minimum of 2 comparables is required for a verdict.
    Thresholds: < 80 % of median → great_deal, ≤ 110 % → fair, > 110 % → overpriced.
    """
    print("Tool check_price used\n")
    listings = load_listings()
    category  = item.get("category", "")
    item_tags = set(item.get("style_tags", []))
    item_price = item.get("price", 0.0)
    item_id    = item.get("id")

    comparables = [
        l for l in listings
        if l.get("category") == category
        and l.get("id") != item_id
        and set(l.get("style_tags", [])) & item_tags
    ]

    if len(comparables) < 2:
        d = {
            "verdict": "no_comparables",
            "item_price": item_price,
            "comparable_count": len(comparables),
        }
        print(d)
        return d

    prices = sorted(l["price"] for l in comparables)
    median = prices[len(prices) // 2]

    if item_price < median * 0.8:
        verdict = "great_deal"
    elif item_price <= median * 1.1:
        verdict = "fair"
    else:
        verdict = "overpriced"

    d = {
        "verdict": verdict,
        "item_price": item_price,
        "median_comparable_price": median,
        "comparable_count": len(comparables),
        "price_range": [prices[0], prices[-1]],
    }
    print(d)
    return d


# ── suggest_outfit helpers ────────────────────────────────────────────────────

_REQUIRED_CATEGORIES = {
    "tops":        ["bottoms", "shoes"],
    "bottoms":     ["tops", "shoes"],
    "shoes":       ["tops", "bottoms"],
    "outerwear":   ["tops", "bottoms", "shoes"],
    "accessories": ["tops", "bottoms", "shoes"],
}
_ALWAYS_OPTIONAL = {"outerwear", "accessories"}
_NEUTRAL_COLORS = {
    "black", "white", "grey", "gray", "cream", "tan", "beige",
    "navy", "ecru", "off-white", "natural", "ivory",
}


def _item_name(item: dict) -> str:
    """Wardrobe items use 'name'; listings use 'title'."""
    return item.get("name") or item.get("title", "Unknown item")


def _compat_score(new_item: dict, candidate: dict) -> int:
    """Score how well a wardrobe item pairs with the new item."""
    score = 0
    new_tags = set(new_item.get("style_tags", []))
    cand_tags = set(candidate.get("style_tags", []))
    score += 2 * len(new_tags & cand_tags)

    new_colors = {c.lower() for c in new_item.get("colors", [])}
    cand_colors = {c.lower() for c in candidate.get("colors", [])}
    if new_colors & cand_colors:
        score += 1
    if cand_colors & _NEUTRAL_COLORS or new_colors & _NEUTRAL_COLORS:
        score += 1

    return score


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    print("Tool suggest_outfit used\n")
    items = wardrobe.get("items", [])
    if not items:
        return {"status": "empty_wardrobe"}

    new_cat = new_item.get("category", "")
    required_from_wardrobe = _REQUIRED_CATEGORIES.get(new_cat, [])

    # Group wardrobe items by category
    by_cat: dict[str, list] = {}
    for item in items:
        by_cat.setdefault(item.get("category", ""), []).append(item)

    # Hard check: required categories must exist in wardrobe
    missing_required = [c for c in required_from_wardrobe if not by_cat.get(c)]
    if missing_required:
        return {"status": "missing_required_category", "missing": missing_required}

    # Score every wardrobe item against the new item
    scored_by_cat = {
        cat: sorted(cat_items, key=lambda i: _compat_score(new_item, i), reverse=True)
        for cat, cat_items in by_cat.items()
    }
    # Required pools: top 2 per required category → vary outfits across these
    req_pools = [scored_by_cat[cat][:2] for cat in required_from_wardrobe]

    print("\n── req_pools ──")
    for cat, pool in zip(required_from_wardrobe, req_pools):
        print(f"  [{cat}]")
        for item in pool:
            print(f"    score={_compat_score(new_item, item)}  {_item_name(item)}")

    # Optional items: best 1 per available optional category (excluding new_item's own cat)
    opt_items = [
        scored_by_cat[cat][0]
        for cat in _ALWAYS_OPTIONAL
        if cat != new_cat and scored_by_cat.get(cat)
    ]

    print("\n── opt_items ──")
    for item in opt_items:
        print(f"  [{item.get('category')}] score={_compat_score(new_item, item)}  {_item_name(item)}")

    # Build prompt: LLM selects best 2 outfits and writes descriptions
    new_name = _item_name(new_item)

    req_section = "\n".join(
        f"  {cat.capitalize()}: "
        + ", ".join(f'"{_item_name(i)}"' for i in pool)
        for cat, pool in zip(required_from_wardrobe, req_pools)
    )
    opt_section = "\n".join(
        f"  {item.get('category', '').capitalize()}: \"{_item_name(item)}\""
        for item in opt_items
    ) or "  (none available)"

    print("\n── prompt candidates ──")
    print(f"  new item : {new_name}")
    print(f"  required :\n{req_section}")
    print(f"  optional :\n{opt_section}")

    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": (
                "You are an enthusiastic thrift fashion stylist.\n\n"
                f'The user is considering: "{new_name}" '
                f"(style: {', '.join(new_item.get('style_tags', []))})\n\n"
                "Pick the best 2 outfits from these wardrobe candidates.\n"
                "Each outfit MUST include the new item + one pick from each required group.\n"
                "Add optional items only if they genuinely elevate the look.\n\n"
                f"Required (pick ONE per group):\n{req_section}\n\n"
                f"Optional (include only if it works):\n{opt_section}\n\n"
                "Write 2 outfit descriptions (2–3 sentences each, numbered, "
                "name the specific pieces, keep it casual and stylish)."
            ),
        }],
        temperature=0.7,
    )
    outfit_string = response.choices[0].message.content.strip()

    # Determine which optional categories are absent from the wardrobe entirely
    missing_optional = [
        cat for cat in _ALWAYS_OPTIONAL
        if cat != new_cat and not scored_by_cat.get(cat)
    ]

    if missing_optional:
        return {
            "status": "partial_outfit",
            "missing_optional": missing_optional,
            "outfits": outfit_string,
        }

    return outfit_string


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    print("Tool create_fit_card used\n")
    if not outfit or not outfit.strip():
        # Can't detect which categories are missing from a free-text string,
        # so missing is left empty — the agent should avoid calling this tool
        # if suggest_outfit returned a non-string status.
        return {"status": "incomplete_outfit", "missing": []}

    item_name = _item_name(new_item)
    price = new_item.get("price")
    platform = new_item.get("platform")
    style_tags = new_item.get("style_tags", [])

    item_line = item_name
    if price:
        item_line += f" (${price:.2f}"
        item_line += f" on {platform})" if platform else ")"

    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": (
                "Write a 1–3 sentence Instagram caption for this thrift outfit.\n\n"
                f"Key thrifted piece: {item_line}"
                + (f"\nStyle: {', '.join(style_tags)}" if style_tags else "")
                + f"\n\nOutfit:\n{outfit}\n\n"
                "Rules:\n"
                "- Sound like a real OOTD post, not a product description\n"
                "- Mention the item name, price, and platform once each, naturally\n"
                "- Capture the specific vibe — be concrete, not generic\n"
                "- No filler phrases like 'slaying', 'serving looks', 'super cute'\n"
                "- Max 3 sentences"
            ),
        }],
        temperature=0.9,
    )
    return response.choices[0].message.content.strip()
