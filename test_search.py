"""Quick manual tests for search_listings()."""

from tools import search_listings


def show(label, result):
    print(f"\n{'='*50}")
    print(f"TEST: {label}")
    print(f"{'='*50}")
    if isinstance(result, list):
        print(f"Found {len(result)} item(s):")
        for item in result:
            print(f"  [{item['size']:20}] ${item['price']:5.2f}  {item['title']}")
    else:
        print(f"Status response: {result}")


# 1. Normal search — should return denim items
show(
    "Search for denim jacket, size M, under $50",
    search_listings("denim jacket", size="M", max_price=50),
)

# 2. Price too low — nothing costs $5
show(
    "Price too low ($5 max)",
    search_listings("vintage tee", max_price=5),
)

# 3. Size relaxed — Woolrich flannel is XL only, asking for XS (4 steps away)
show(
    "Size relaxed — Woolrich flannel is XL, asking for XS",
    search_listings("woolrich flannel", size="XS", max_price=100),
)

# 4. No results — nonsense description, no keyword overlap
show(
    "No results — description matches nothing ('sparkly wizard robe')",
    search_listings("sparkly wizard robe", max_price=100),
)

# 5. No size filter — broader results
show(
    "Cottagecore tops, no size filter, under $40",
    search_listings("cottagecore floral", max_price=40),
)

# 6. Shoe size flex — US 8 should match US 7 and US 8.5 listings
show(
    "Shoes around US 8",
    search_listings("platform shoes", size="US 8", max_price=100),
)
