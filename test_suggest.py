"""Manual tests for suggest_outfit()."""

from tools import suggest_outfit
from utils.data_loader import get_example_wardrobe

FULL_WARDROBE = get_example_wardrobe()

# ── Fixtures ──────────────────────────────────────────────────────────────────

GRAPHIC_TEE = {
    "id": "lst_006", "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge", "streetwear", "band tee"],
    "colors": ["black"], "condition": "good",
}

DENIM_JACKET = {
    "id": "lst_007", "title": "Denim Jacket — Light Wash, Cropped",
    "category": "outerwear",
    "style_tags": ["denim", "vintage", "classic", "streetwear"],
    "colors": ["light blue"], "condition": "excellent",
}

PLATFORM_SHOES = {
    "id": "lst_009", "title": "Platform Mary Janes — Black Patent",
    "category": "shoes",
    "style_tags": ["y2k", "goth", "platform", "90s"],
    "colors": ["black"], "condition": "good",
}

LEATHER_BELT = {
    "id": "lst_014", "title": "Leather Belt — Brown, Braided",
    "category": "accessories",
    "style_tags": ["vintage", "western", "classic", "earth tones"],
    "colors": ["brown"], "condition": "excellent",
}

# Wardrobe missing shoes → required category absent
WARDROBE_NO_SHOES = {
    "items": [i for i in FULL_WARDROBE["items"] if i["category"] != "shoes"]
}

# Wardrobe with only tops + bottoms + shoes (no outerwear or accessories)
WARDROBE_MINIMAL = {
    "items": [i for i in FULL_WARDROBE["items"]
              if i["category"] in ("tops", "bottoms", "shoes")]
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def show(label, result):
    print(f"\n{'='*55}")
    print(f"TEST: {label}")
    print(f"{'='*55}")
    if isinstance(result, dict):
        print(f"Status : {result.get('status')}")
        for k, v in result.items():
            if k != "status":
                print(f"{k:10}: {v}")
    else:
        print(result)

# ── Tests ─────────────────────────────────────────────────────────────────────

# 1. Full wardrobe + new top → expects outfit string (LLM response)
show(
    "Full wardrobe, new item is a top (graphic tee)",
    suggest_outfit(GRAPHIC_TEE, FULL_WARDROBE),
)

# 2. Full wardrobe + new item is outerwear → outerwear already covered; needs tops+bottoms+shoes
show(
    "Full wardrobe, new item is outerwear (denim jacket)",
    suggest_outfit(DENIM_JACKET, FULL_WARDROBE),
)

# 3. Minimal wardrobe (no outerwear, no accessories) + new top
#    → partial_outfit with missing_optional
show(
    "Minimal wardrobe (no outerwear/accessories), new top",
    suggest_outfit(GRAPHIC_TEE, WARDROBE_MINIMAL),
)

# 4. Wardrobe missing shoes + new top → missing_required_category
show(
    "Wardrobe has no shoes, new item is a top",
    suggest_outfit(GRAPHIC_TEE, WARDROBE_NO_SHOES),
)

# 5. Empty wardrobe → empty_wardrobe
show(
    "Empty wardrobe",
    suggest_outfit(GRAPHIC_TEE, {"items": []}),
)

# 6. New item is shoes → requires tops + bottoms from wardrobe
show(
    "Full wardrobe, new item is shoes (platform Mary Janes)",
    suggest_outfit(PLATFORM_SHOES, FULL_WARDROBE),
)

# 7. New item is accessories → requires tops + bottoms + shoes
show(
    "Full wardrobe, new item is an accessory (leather belt)",
    suggest_outfit(LEATHER_BELT, FULL_WARDROBE),
)
