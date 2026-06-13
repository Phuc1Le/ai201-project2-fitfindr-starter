"""Manual tests for create_fit_card()."""

from tools import create_fit_card

# ── Fixtures ──────────────────────────────────────────────────────────────────

GRAPHIC_TEE = {
    "id": "lst_006",
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge", "streetwear", "band tee"],
    "colors": ["black"],
    "price": 24.00,
    "platform": "depop",
    "condition": "good",
    "size": "L",
}

DENIM_JACKET = {
    "id": "lst_007",
    "title": "Denim Jacket — Light Wash, Cropped",
    "category": "outerwear",
    "style_tags": ["denim", "vintage", "classic", "streetwear"],
    "colors": ["light blue"],
    "price": 42.00,
    "platform": "poshmark",
    "condition": "excellent",
    "size": "S",
}

OUTFIT_GRUNGE = (
    "Outfit 1: Pair the bootleg graphic tee with baggy dark-wash jeans and black combat boots "
    "for a lived-in 90s grunge look. Throw the vintage black denim jacket on top to lock in "
    "that effortlessly cool energy.\n\n"
    "Outfit 2: Same tee tucked slightly into wide-leg khakis with chunky white sneakers — "
    "a cleaner streetwear take that still feels vintage."
)

OUTFIT_DENIM = (
    "Outfit 1: The cropped denim jacket over a white ribbed tank and baggy dark jeans "
    "is a timeless streetwear combo. Finish with chunky white sneakers.\n\n"
    "Outfit 2: Layer the jacket open over a grey crewneck with wide-leg khakis and "
    "black combat boots for a relaxed, oversized silhouette."
)

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

# 1. Normal case — grunge tee with a full outfit description
show(
    "Graphic tee + full grunge outfit",
    create_fit_card(OUTFIT_GRUNGE, GRAPHIC_TEE),
)

# 2. Normal case — denim jacket, different item and outfit → different caption
show(
    "Denim jacket + full streetwear outfit",
    create_fit_card(OUTFIT_DENIM, DENIM_JACKET),
)

# 3. Same inputs called twice — should produce different phrasing (temperature=0.9)
print(f"\n{'='*55}")
print("TEST: Same inputs, two calls — check phrasing varies")
print(f"{'='*55}")
a = create_fit_card(OUTFIT_GRUNGE, GRAPHIC_TEE)
b = create_fit_card(OUTFIT_GRUNGE, GRAPHIC_TEE)
print(f"Call 1:\n{a}\n")
print(f"Call 2:\n{b}\n")
print(f"Identical: {a == b}")

# 4. Empty outfit string → incomplete_outfit
show(
    "Empty outfit string",
    create_fit_card("", GRAPHIC_TEE),
)

# 5. Whitespace-only outfit → incomplete_outfit
show(
    "Whitespace-only outfit",
    create_fit_card("   \n  ", GRAPHIC_TEE),
)

# 6. Item missing price and platform — caption should still generate
show(
    "Item with no price or platform",
    create_fit_card(OUTFIT_GRUNGE, {
        "title": "Mystery Vintage Piece",
        "category": "tops",
        "style_tags": ["vintage"],
        "colors": ["black"],
    }),
)
