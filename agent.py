"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os

import httpx
from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card, check_price

load_dotenv(override=True)


# ── Constants ─────────────────────────────────────────────────────────────────

MAX_TOOL_ROUNDS = 10

SYSTEM_PROMPT = """You are FitFindr, an enthusiastic thrift fashion stylist assistant.
Your job is to help users find clothing items and style complete outfits from thrift listings.

You have three tools:

1. search_listings — search for items by description, size, and price ceiling.
   Call this first whenever the user asks about finding a specific item.
   The result includes a price verdict (great_deal / fair / overpriced) — share it with the user.

2. suggest_outfit — suggest outfit combinations using the found item and the user's wardrobe.
   Call this after search_listings has found a result.

3. create_fit_card — generate a short social media caption for the outfit.
   Call this after suggest_outfit has produced an outfit description.

Typical sequence: search_listings → suggest_outfit → create_fit_card.

When check_price returns a verdict, share it with the user naturally:
- great_deal:     Tell them it's priced well below similar items — a good find.
- fair:           Tell them the price is in line with comparable listings.
- overpriced:     Note it's above the typical range and let them decide.
- no_comparables: Tell them there aren't enough similar listings to compare.

Once search_listings has returned a result, do NOT call search_listings again — even if the item
is not a perfect match. If you try to call it again you will get status "already_searched", which
means you must call suggest_outfit next. The user can refine their search in a new query.

If the user's message is too vague to identify a specific item (e.g., "I want another listing",
"show me something", "find me stuff"), do NOT guess a description. Instead, ask them what
they're looking for — what item, style, or category they have in mind.

When a tool returns a status dict, handle it as follows:
- price_too_low:            Tell the user the lowest available price and ask if they want to raise their budget.
                            Do NOT automatically retry search_listings with a different price — wait for the user.
- size_relaxed:             Tell the user the size filter was loosened, then continue to suggest_outfit and create_fit_card as normal.
- no_results:               Tell the user nothing matched and ask them to rephrase.
- partial_outfit:           Note the missing optional categories, then proceed to create_fit_card using result["outfits"].
- missing_required_category: Tell the user a complete outfit isn't possible without that category.
- empty_wardrobe:           The wardrobe is empty, so you can't mix-and-match, but still give the user
                            general styling advice for the item — what it pairs well with, what aesthetic
                            it fits, what pieces they could look for. Do NOT call create_fit_card afterward.

Always be friendly, casual, and fashion-forward.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_listings",
            "description": (
                "Search thrift clothing listings by description, optional size, and optional price ceiling. "
                "Parse these values from the user's message. Call this when the user wants to search for an item."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Keywords describing the item (e.g. 'vintage graphic tee', 'black denim jacket').",
                    },
                    "size": {
                        "type": "string",
                        "description": "Size string (e.g. 'M', 'US 9', 'W30'). Omit if the user did not specify one.",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Price ceiling in USD. Omit if the user did not specify one.",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_outfit",
            "description": (
                "Suggest outfit combinations using the top item from search results and the user's wardrobe. "
                "Call this after search_listings has found a result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "Brief note on why you are calling this now (e.g. 'found a vintage tee, ready to suggest outfit').",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_fit_card",
            "description": (
                "Generate a short social-media caption for the outfit. "
                "Call this after suggest_outfit has produced an outfit description."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "Brief note on why you are calling this now (e.g. 'outfit ready, generating caption').",
                    }
                },
                "required": [],
            },
        },
    },
]


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    # University/corporate networks run an HTTPS inspection proxy whose CA cert
    # fails strict SSL validation. The API key is the auth mechanism, not the TLS chain.
    return Groq(api_key=api_key, http_client=httpx.Client(verify=False))


# ── Session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    messages      → the LLM's working memory; sent to Groq on every round
    everything else → structured fields for the caller (Gradio, tests, CLI)
    """
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": query},
        ],
        "query":             query,
        "wardrobe":          wardrobe,
        "search_results":    [],
        "selected_item":     None,
        "outfit_suggestion": None,
        "fit_card":          None,
        "price_verdict":     None,
        "size_relaxed":      False,
        "empty_wardrobe":    False,
        "reply":             None,
        "error":             None,
    }


# ── Tool dispatch ─────────────────────────────────────────────────────────────

def _dispatch_tool(name: str, args: dict, session: dict) -> dict | list:
    """
    Route a tool call to the matching Python function, supply session state
    where needed, and write results back into the session dict.

    Returns a JSON-serializable value that becomes the tool message content.
    """
    if name == "search_listings":
        if session["selected_item"]:
            return {
                "status": "already_searched",
                "message": "A search was already run this session. Call suggest_outfit to continue.",
            }
        result = search_listings(**args)
        if isinstance(result, list):
            session["search_results"] = result
            session["selected_item"] = result[0] if result else None
            # Run price check automatically — no LLM round needed for a deterministic op.
            item = result[0]
            verdict_data = check_price(item)
            session["price_verdict"] = verdict_data
            verdict_label = {
                "great_deal":    "great deal",
                "fair":          "fair price",
                "overpriced":    "above average price",
                "no_comparables": "no comparable listings to assess price",
            }.get(verdict_data["verdict"], "")

            # Return a lean summary — full item dicts stored in session, not in messages.
            summary = (
                f"{item['title']} — ${item['price']:.2f}, "
                f"size {item.get('size', 'N/A')}, {item.get('platform', '')}. "
                f"Price verdict: {verdict_label}"
            )
            if verdict_data.get("median_comparable_price"):
                summary += f" (median comparable: ${verdict_data['median_comparable_price']:.2f})"
            return {"found": len(result), "top_item": summary}
        elif isinstance(result, dict):
            status = result.get("status")
            if status == "price_too_low":
                session["error"] = (
                    f"Price too low. Lowest available price is ${result['lowest_matching_price']:.2f}."
                )
            elif status == "no_results":
                session["error"] = result.get("message", "No matching items found.")
            elif status == "size_relaxed":
                items = result.get("items", [])
                session["search_results"] = items
                session["selected_item"] = items[0] if items else None
                session["size_relaxed"] = True
                item = items[0]
                verdict_data = check_price(item)
                session["price_verdict"] = verdict_data
                verdict_label = {
                    "great_deal":     "great deal",
                    "fair":           "fair price",
                    "overpriced":     "above average price",
                    "no_comparables": "no comparable listings to assess price",
                }.get(verdict_data["verdict"], "")
                summary = (
                    f"{item['title']} — ${item['price']:.2f}, "
                    f"size {item.get('size', 'N/A')}, {item.get('platform', '')}. "
                    f"Price verdict: {verdict_label}"
                )
                if verdict_data.get("median_comparable_price"):
                    summary += f" (median comparable: ${verdict_data['median_comparable_price']:.2f})"
                return {"status": "size_relaxed", "top_item": summary}
        return result

    elif name == "suggest_outfit":
        if not session["selected_item"]:
            return {"status": "error", "message": "No item selected — call search_listings first."}
        result = suggest_outfit(session["selected_item"], session["wardrobe"])
        if isinstance(result, str):
            session["outfit_suggestion"] = result
        elif isinstance(result, dict):
            if "outfits" in result:
                session["outfit_suggestion"] = result["outfits"]
            elif result.get("status") == "empty_wardrobe":
                session["empty_wardrobe"] = True
        return result

    elif name == "create_fit_card":
        if not session["outfit_suggestion"]:
            return {"status": "error", "message": "No outfit suggestion yet - call suggest_outfit first."}
        result = create_fit_card(session["outfit_suggestion"], session["selected_item"])
        if isinstance(result, str):
            session["fit_card"] = result
        return result

    else:
        return {"status": "error", "message": f"Unknown tool: {name}"}


# ── LLM call with retry ───────────────────────────────────────────────────────

def _call_llm(client: Groq, messages: list, tools: list, max_retries: int = 3):
    """
    Call the Groq chat API, retrying once on tool_use_failed.
    That error is an intermittent model generation failure, not a logic error.
    Re-raises on any other error or if all retries are exhausted.
    """
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        except Exception as e:
            if "rate_limit_exceeded" in str(e):
                raise  # no point retrying — quota is exhausted
            retryable = "tool_use_failed" in str(e) or "Connection error" in str(e)
            if attempt < max_retries - 1 and retryable:
                continue
            print(f"[_call_llm] {type(e).__name__}: {e}")
            raise


# ── Planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    session = _new_session(query, wardrobe)
    client  = _get_groq_client()

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = _call_llm(client, session["messages"], TOOLS)
        except Exception as e:
            print(f"[run_agent] {type(e).__name__}: {e}")
            session["error"] = "Could not process your request. Please try rephrasing."
            break

        message = response.choices[0].message

        # Omit content entirely when None/empty — Groq rejects "" alongside tool_calls
        assistant_msg: dict = {"role": "assistant"}
        if message.content:
            assistant_msg["content"] = message.content
        if message.tool_calls:
            print(message.tool_calls)
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        session["messages"].append(assistant_msg)

        # No tool calls → LLM produced its final text response
        if not message.tool_calls:
            session["reply"] = message.content or ""
            break

        for tool_call in message.tool_calls:
            name   = tool_call.function.name
            args   = json.loads(tool_call.function.arguments)
            result = _dispatch_tool(name, args, session)
            print(result)
            session["messages"].append({
                "role":         "tool",
                "tool_call_id": tool_call.id,
                "content":      json.dumps(result),
            })

        # Hard failure set during dispatch — stop immediately so the LLM
        # cannot retry or continue the pipeline on a bad result.
        if session["error"]:
            break

    else:
        session["error"] = f"Agent did not finish within {MAX_TOOL_ROUNDS} tool rounds."

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $50",
        wardrobe=get_empty_wardrobe(),
    )
    print(f"Error:   {session['error']}")
    print(f"Found:   {session['selected_item']}")
    print(f"Outfit:  {session['outfit_suggestion']}")
    print(f"Fit card:{session['fit_card']}")
    print(f"Reply:\n{session['reply']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="polo shirt size M under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"selected_item    : {session2['selected_item']}")
    print(f"outfit_suggestion: {session2['outfit_suggestion']}")
    print(f"fit_card         : {session2['fit_card']}")
    print(f"error            : {session2['error']}")
