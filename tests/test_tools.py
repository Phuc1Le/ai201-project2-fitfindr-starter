"""
Integration tests for all three FitFindr tools.

Run from the project root:
    pytest tests/test_tools.py -v

Tests marked with LLM make a real Groq API call and require GROQ_API_KEY in .env.
Failure-mode tests never call the LLM and run instantly.
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card, check_price
from utils.data_loader import get_example_wardrobe

# ── Shared fixtures ───────────────────────────────────────────────────────────

FULL_WARDROBE = get_example_wardrobe()

WARDROBE_MINIMAL = {                          # tops + bottoms + shoes only
    "items": [i for i in FULL_WARDROBE["items"]
              if i["category"] in ("tops", "bottoms", "shoes")]
}

WARDROBE_NO_SHOES = {
    "items": [i for i in FULL_WARDROBE["items"] if i["category"] != "shoes"]
}

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

OUTFIT_STR = (
    "Outfit 1: Graphic tee with baggy dark-wash jeans and black combat boots — "
    "classic 90s grunge energy, effortlessly worn-in.\n\n"
    "Outfit 2: Same tee tucked into wide-leg khakis with chunky white sneakers "
    "for a cleaner streetwear take."
)

# ── search_listings ───────────────────────────────────────────────────────────
def test_search():
    result = search_listings("designer ballgown", size="XXS", max_price=100)
    print(result)
    assert len(result) > 0
def test_search_returns_list():
    result = search_listings("vintage graphic tee", max_price=50)
    assert isinstance(result, list)
    assert len(result) > 0

def test_search_all_items_under_max_price():
    result = search_listings("jacket", max_price=40)
    assert isinstance(result, list)
    assert all(item["price"] <= 40 for item in result)

def test_search_results_sorted_by_relevance():
    # First result should score higher than last
    result = search_listings("denim vintage streetwear", max_price=100)
    assert isinstance(result, list) and len(result) >= 2

def test_search_shoe_size_flex():
    # US 8 should match both US 8 and US 8.5
    result = search_listings("platform shoes", size="US 8", max_price=100)
    assert isinstance(result, list)
    assert any("8" in item["size"] for item in result)

# Failure: price ceiling below all listings
def test_search_price_too_low():
    result = search_listings("vintage tee", max_price=5)
    assert isinstance(result, dict)
    assert result["status"] == "price_too_low"
    assert "lowest_matching_price" in result
    assert result["lowest_matching_price"] > 5

# Failure: description has zero keyword overlap with any listing
def test_search_no_results():
    result = search_listings("deep sea fishing rod", max_price=200)
    assert isinstance(result, dict)
    assert result["status"] == "no_results"

def test_search_size_relaxed():
    # Woolrich flannel only exists in XL — XS is 4 steps away
    result = search_listings("woolrich flannel", size="XS", max_price=100)
    assert isinstance(result, dict)
    assert result["status"] == "size_relaxed"
    assert isinstance(result["items"], list)
    assert len(result["items"]) > 0

# ── suggest_outfit ────────────────────────────────────────────────────────────
def test_suggest_full_wardrobe():                                         # LLM
    result = suggest_outfit(GRAPHIC_TEE, FULL_WARDROBE)
    assert isinstance(result, str)
    assert len(result) > 0

def test_suggest_partial_outfit():                                        # LLM
    # Minimal wardrobe has no outerwear or accessories → partial_outfit
    result = suggest_outfit(GRAPHIC_TEE, WARDROBE_MINIMAL)
    assert isinstance(result, dict)
    assert result["status"] == "partial_outfit"
    assert "missing_optional" in result
    assert isinstance(result["missing_optional"], list)
    assert "outfits" in result and len(result["outfits"]) > 0

# Failure: wardrobe has no items at all
def test_suggest_empty_wardrobe():
    result = suggest_outfit(GRAPHIC_TEE, {"items": []})
    assert isinstance(result, dict)
    assert result["status"] == "empty_wardrobe"

# Failure: required category (shoes) missing from wardrobe
def test_suggest_missing_required_category():
    result = suggest_outfit(GRAPHIC_TEE, WARDROBE_NO_SHOES)
    assert isinstance(result, dict)
    assert result["status"] == "missing_required_category"
    assert "shoes" in result["missing"]

# ── create_fit_card ───────────────────────────────────────────────────────────

def test_fit_card_returns_string():                                       # LLM
    result = create_fit_card(OUTFIT_STR, GRAPHIC_TEE)
    assert isinstance(result, str)
    assert len(result) > 0

def test_fit_card_mentions_item_name():                                   # LLM
    result = create_fit_card(OUTFIT_STR, GRAPHIC_TEE)
    assert isinstance(result, str)
    # Caption should reference the item or its price/platform somewhere
    lower = result.lower()
    assert any(word in lower for word in ["graphic", "tee", "depop", "24"])

def test_fit_card_no_price_or_platform():                                 # LLM
    # Item missing optional fields — should still generate a caption
    bare_item = {
        "title": "Mystery Vintage Piece",
        "category": "tops",
        "style_tags": ["vintage"],
        "colors": ["black"],
    }
    result = create_fit_card(OUTFIT_STR, bare_item)
    assert isinstance(result, str)
    assert len(result) > 0

# Failure: empty outfit string
def test_fit_card_empty_outfit():
    result = create_fit_card("", GRAPHIC_TEE)
    assert isinstance(result, dict)
    assert result["status"] == "incomplete_outfit"
    assert "missing" in result

# Failure: whitespace-only outfit string
def test_fit_card_whitespace_outfit():
    result = create_fit_card("   \n\t  ", GRAPHIC_TEE)
    assert isinstance(result, dict)
    assert result["status"] == "incomplete_outfit"

# ── check_price ───────────────────────────────────────────────────────────────

def test_check_price_returns_verdict():
    result = check_price(GRAPHIC_TEE)
    assert isinstance(result, dict)
    assert result["verdict"] in ("great_deal", "fair", "overpriced", "no_comparables")
    assert result["item_price"] == GRAPHIC_TEE["price"]

def test_check_price_has_median_when_comparables_found():
    result = check_price(GRAPHIC_TEE)
    if result["verdict"] != "no_comparables":
        assert "median_comparable_price" in result
        assert "comparable_count" in result
        assert result["comparable_count"] >= 2
        assert "price_range" in result

def test_check_price_excludes_self():
    # The item itself should never be counted as its own comparable
    result = check_price(GRAPHIC_TEE)
    if result["verdict"] != "no_comparables":
        # comparable_count must be drawn from other listings only
        assert result["comparable_count"] < 40

# Failure: item with no style tags → no shared tags with any listing
def test_check_price_no_comparables():
    bare_item = {"id": "test_bare", "category": "tops", "style_tags": [], "price": 20.0}
    result = check_price(bare_item)
    assert result["verdict"] == "no_comparables"
    assert result["comparable_count"] == 0
