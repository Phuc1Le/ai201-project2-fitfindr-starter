# FitFindr

A thrift fashion assistant powered by a Groq LLM agent loop and a Gradio UI. Describe what you're looking for, and FitFindr finds a secondhand listing, suggests outfits using your wardrobe, and writes a social-media caption you can post.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── tools.py                   # Three agent tools (search, outfit, fit card)
├── agent.py                   # Planning loop and state management
├── app.py                     # Gradio interface
├── tests/
│   └── test_tools.py          # pytest integration tests
└── planning.md                # Design spec
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Then open the localhost URL shown in your terminal (usually `http://localhost:7860`, but check your terminal — the port may differ).

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.

Your implementation files go in this same directory. There's no required file structure for your agent code — organize it however makes sense for your design.

---

## Tool Inventory

### Tool 1: `search_listings`

**Purpose:** Finds secondhand listings from `listings.json` that match the user's description, optional size, and optional price ceiling.

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `description` | `str` | Yes | Keywords describing the item (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | No | Size string (e.g. `"M"`, `"US 9"`, `"W30"`). `None` skips size filtering. |
| `max_price` | `float \| None` | No | Price ceiling in USD. `None` skips price filtering. |

**Outputs:**

- **Success:** `list[dict]` — matching listings sorted by relevance (best match first).
- **Failure:** one of three status dicts (see Error Handling section).

**Scoring strategy:** Each listing is scored by keyword overlap between the query tokens and the listing's fields, with field weights: title ×3, style\_tags ×2, colors ×2, category ×2, brand ×2, description ×1. Items scoring 0 are dropped entirely.

---

### Tool 2: `suggest_outfit`

**Purpose:** Given the top search result and the user's wardrobe, suggests up to 2 complete outfit combinations that include the new item.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | The thrifted listing the user is considering |
| `wardrobe` | `dict` | `{"items": [...]}` — a list of wardrobe item dicts |

**Outputs:**

- **Full wardrobe:** `str` — 2 outfit descriptions written by the LLM, naming specific wardrobe pieces.
- **Missing optional categories:** `{"status": "partial_outfit", "missing_optional": [...], "outfits": str}`
- **Failure:** `{"status": "missing_required_category", "missing": [...]}` or `{"status": "empty_wardrobe"}`

**Outfit logic:** Required categories are determined by the new item's category (e.g. buying a top requires bottoms + shoes). The top 2 wardrobe candidates per required category are scored by style-tag overlap and color compatibility, then passed to the LLM to pick the best 2 outfits. Optional categories (outerwear, accessories) are included only if they exist in the wardrobe.

---

### Tool 3: `create_fit_card`

**Purpose:** Writes a 1–3 sentence Instagram-style caption for a completed outfit, mentioning the thrifted item's name, price, and platform naturally.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | Outfit suggestion string from `suggest_outfit()` |
| `new_item` | `dict` | The thrifted listing (for name, price, platform) |

**Outputs:**

- **Success:** `str` — a casual OOTD caption.
- **Failure:** `{"status": "incomplete_outfit", "missing": []}` if `outfit` is empty or whitespace-only.

---

## Planning Loop

The agent uses a **ReAct-style loop** driven by Groq's tool-calling API. On every round the full message history is sent to the LLM; the LLM either calls a tool or returns a final text response.

**Typical sequence:**

```
User query
    │
    ▼
Round 1 — LLM calls search_listings(description, [size], [max_price])
               ↓ lean summary appended to messages
Round 2 — LLM calls suggest_outfit(context)
               ↓ outfit string or status dict appended to messages
Round 3 — LLM calls create_fit_card(context)
               ↓ caption appended to messages
Round 4 — LLM produces final text response → loop ends
```

The loop is capped at `MAX_TOOL_ROUNDS = 10`. If the LLM returns a response with no tool calls, the loop exits immediately. The LLM decides when to call each tool based on the tool results it sees in the message history — for example, if `suggest_outfit` returns `{"status": "empty_wardrobe"}`, the system prompt tells the LLM to skip `create_fit_card` and give general styling advice instead.

---

## State Management

The agent uses a **hybrid approach**: a `messages` list for LLM working memory, and a `session` dict for structured data the Gradio UI needs.

```python
session = {
    "messages":          [...],   # full conversation history — sent to Groq every round
    "query":             str,     # original user query
    "wardrobe":          dict,    # user's wardrobe (never sent to LLM directly)
    "search_results":    list,    # all results from search_listings
    "selected_item":     dict,    # top result — used by suggest_outfit and create_fit_card
    "outfit_suggestion": str,     # from suggest_outfit — displayed in outfit panel
    "fit_card":          str,     # from create_fit_card — displayed in fit card panel
    "reply":             str,     # LLM's final text message
    "error":             str,     # set on hard failures (price_too_low, no_results)
}
```

**Why hybrid?** The Gradio UI has three separate output panels. A pure messages-only approach returns one text blob that can't be cleanly split across panels. The session holds the structured data the UI needs; the messages list holds what the LLM needs. `_dispatch_tool` writes to both after every tool call.

**Token efficiency:** `_dispatch_tool` returns lean summaries to the LLM (e.g. `"Found 3 items. Top: Graphic Tee — $24.00, size L, depop"`) rather than full item dicts. Full data stays in the session for the UI. This cuts per-run token cost by roughly 60%.

---

## Error Handling

### `search_listings`

| Failure | Status | Agent behavior |
|---------|--------|----------------|
| All listings exceed `max_price` | `price_too_low` | LLM reports the lowest available price and asks if the user wants to raise their budget |
| No keyword overlap with any listing | `no_results` | LLM says nothing matched and asks the user to rephrase |
| No size match but description matches | `size_relaxed` | LLM informs user the size filter was loosened; pipeline continues with relaxed results |

**Concrete example — `price_too_low`:** Searching `"designer ballgown size XXS"` with `max_price=5` returned `{"status": "price_too_low", "lowest_matching_price": 22.0}`. The LLM responded: *"The cheapest matching item I found is $22.00 — want to raise your budget?"*

**Concrete example — `no_results`:** Searching `"deep sea fishing rod"` returned `{"status": "no_results"}` because zero listings scored above 0. Earlier in development, this path returned the top-2 items by score even when all scores were 0, sending the LLM arbitrary irrelevant results. Changed to a clean `no_results` status instead.

---

### `suggest_outfit`

| Failure | Status | Agent behavior |
|---------|--------|----------------|
| Wardrobe has no items | `empty_wardrobe` | LLM gives general styling advice for the item; does NOT call `create_fit_card` |
| Wardrobe missing a required category | `missing_required_category` | LLM tells user a complete outfit isn't possible without that category |
| Optional categories absent | `partial_outfit` | LLM notes the missing optional items, then proceeds to `create_fit_card` |

**Concrete example — `empty_wardrobe`:** With an empty wardrobe and a graphic tee, `suggest_outfit` returned `{"status": "empty_wardrobe"}`. The LLM then replied with styling advice: *"That vintage graphic tee pairs well with high-waisted jeans, cargo pants, or a flowy skirt. Look for chunky sneakers or platform boots to complete the look."*

---

### `create_fit_card`

| Failure | Status | Agent behavior |
|---------|--------|----------------|
| `outfit` is empty or whitespace-only | `incomplete_outfit` | LLM notes the fit card couldn't be generated; does not retry |

**Concrete example:** Passing `outfit=""` returned `{"status": "incomplete_outfit", "missing": []}` without making any LLM call. The guard runs before the API call so it costs zero tokens.

---

## Spec Reflection

**What changed from the original spec:**

1. **`search_listings` no-results behavior.** The spec called for returning "closest 2 listings" when nothing matches. When all scores are 0, sorting by score returns arbitrary items — there's no meaningful "closest match." Changed to `{"status": "no_results"}` instead, which gives the LLM an honest signal.

2. **`suggest_outfit` outfit generation.** The spec said "top 3 outfits ranked by keyword matching score." Changed to: score wardrobe items per required category, take the top 2 per category as candidates, then have the LLM write the best 2 outfits from those candidates. This produces more natural-sounding outfit descriptions than pure score-ranked selection.

3. **Tool schemas for `suggest_outfit` and `create_fit_card`.** These tools take no LLM-supplied arguments (the agent reads them from the session). Empty parameter schemas caused `llama-3.3-70b-versatile` to produce malformed tool calls. Added an optional `context: str` parameter to both so the LLM has something concrete to fill in, eliminating the errors.

4. **Session + messages hybrid.** The spec described a pure messages-driven approach. A session dict was added alongside the messages list so the Gradio UI's three separate output panels can be populated independently, which a single text response cannot cleanly support.

---

## Stretch Features

### Price comparison tool

Every time an item is found after calling `search_listings`, `check_price` tool is called to compare the price of that item to similar items of the same category and returns a `verdict` dict. The verdict can either be `overpriced`, `fair`, or `great deal`. It is then appended to the search result in `search_listing` panel.
**Example:** Searching for "flowy midi skirt under $40" return this in "Top listing found" panel:

90s Silk Slip Dress — Floral, Midi Length

─────────────────────────────────────────

Price:     $30.00
Platform:  Depop
Size:      M
Condition: Good
Colors:    ivory, dusty pink, green
Tags:      90s, vintage, feminine, floral, cottagecore

Delicate 90s slip dress in a muted floral print. Midi length, adjustable straps. Light snag on the side seam — not visible when worn.

Price verdict: Fair price — median comparable is $32.00

### Retry with loosened constraints

If `search_listings` finds description matches but none in the requested size, it automatically retries without the size filter and returns the results under `{"status": "size_relaxed", "items": [...]}`. The agent treats this as a soft failure — `selected_item` is still set and the outfit pipeline continues — while the LLM informs the user that the size filter was loosened and shows what was found.

**Example:** Searching for `"woolrich flannel size XS"` finds the flannel by description but the only listing is XL (4 steps away, outside the ±1 step flex). `search_listings` drops the size constraint, returns the XL listing under `size_relaxed`, and the LLM responds: *"I couldn't find your exact size, so I loosened the size filter — here's what came up."* The outfit suggestion then proceeds normally with the relaxed result.

---

## AI Usage

### Instance 1: Implementing `search_listings`

**Input given to Claude:** The Tool 1 section of `planning.md` — inputs, return values, all three failure modes (`price_too_low`, `size_relaxed`, closest-match/no-results) — plus the instruction to read the function docstring in `tools.py`.

**What Claude produced:** The full implementation including `_tokenize` (stopword removal), `_size_matches` (named-size ±1 step flex, US shoe ±0.5, waist ±1 inch, One Size wildcard), `_score_listing` with field weights, and the main function with price → description → size filter ordering.

**What I changed:** I discovered a bug in Claude's `price_too_low` error path. Testing `"designer ballgown size XXS under $5"` returned `price_too_low` with a lowest price of $22, but re-running with `max_price=22` returned `no_results`. I traced the contradiction to the `or listings` fallback in the `price_too_low` path: when the description matches zero listings, `relevant` is empty and silently falls back to all 40 listings, so the $22 figure was the cheapest item in the entire dataset — unrelated to ballgowns. I fixed it by removing the fallback so that an empty `relevant` returns `no_results` immediately, and `price_too_low` only fires when the description genuinely matches items that are all over budget.

---

### Instance 2: Building the agent planning loop

**Input given to Claude:** The Planning Loop and State Management sections of `planning.md`, the architecture diagram, the three tool signatures, and the lab project's example planning loop as reference for the messages structure.

**What Claude produced:** The full `agent.py` — `_new_session`, `_dispatch_tool`, `_call_llm` with retry logic for `tool_use_failed` errors, and the `run_agent` loop. It proposed the hybrid session+messages architecture explaining why a pure messages approach can't feed three separate Gradio panels cleanly.

**What I changed:** During testing, `suggest_outfit` and `create_fit_card` had completely empty parameter schemas, and `llama-3.3-70b-versatile` consistently generated malformed tool calls (`<function=suggest_outfit(...)>` instead of proper JSON) when trying to call them. Claude's initial design did not anticipate this. After diagnosing the root cause (the model struggles when there's nothing to write in the arguments), I worked with Claude to add an optional `context: str` parameter to both tool schemas. This gave the model something concrete to fill in and eliminated the `tool_use_failed` errors on those tools.
