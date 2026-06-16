"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:     The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        A tuple of three strings:
            (listing_text, outfit_suggestion, fit_card)
        Each string maps to one of the three output panels in the UI.
    """
    print(f"[handle_query] query={user_query!r} wardrobe={wardrobe_choice!r}")

    # 1. Guard empty query
    if not user_query or not user_query.strip():
        return "Please enter a search query.", "", ""

    # 2. Select wardrobe
    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    # 3. Run agent — catch unexpected crashes so Gradio always gets a string back
    try:
        session = run_agent(user_query.strip(), wardrobe)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Unexpected error: {e}", "", ""

    # 4. Error case — use LLM's friendly reply if available, fall back to internal msg
    if session["error"]:
        return session["reply"] or session["error"], "", ""

    # 5. Format the top listing into a readable card
    item = session["selected_item"]
    if item:
        tags   = ", ".join(item.get("style_tags") or [])
        colors = ", ".join(item.get("colors") or [])
        lines  = [
            item["title"],
            "─" * len(item["title"]),
            f"Price:     ${item['price']:.2f}",
            f"Platform:  {(item.get('platform') or '').capitalize()}",
            f"Size:      {item.get('size', 'N/A')}",
            f"Condition: {(item.get('condition') or 'N/A').capitalize()}",
            f"Colors:    {colors}",
        ]
        if item.get("brand"):
            lines.append(f"Brand:     {item['brand']}")
        if tags:
            lines.append(f"Tags:      {tags}")
        if item.get("description"):
            lines += ["", item["description"]]

        verdict_data = session.get("price_verdict")
        if verdict_data:
            v = verdict_data["verdict"]
            if v == "great_deal":
                label = f"Great deal — median comparable is ${verdict_data['median_comparable_price']:.2f}"
            elif v == "fair":
                label = f"Fair price — median comparable is ${verdict_data['median_comparable_price']:.2f}"
            elif v == "overpriced":
                label = f"Above average — median comparable is ${verdict_data['median_comparable_price']:.2f}"
            else:
                label = "Not enough comparable listings to assess price"
            lines += ["", f"Price verdict: {label}"]

        listing_text = "\n".join(lines)
    else:
        # No item found — LLM probably asked for clarification; show its reply here
        listing_text = session["reply"] or "No item found."

    # Fall back to LLM reply only when no item was found (empty_wardrobe path).
    # If an item was found but suggest_outfit wasn't called, keep the panel empty.
    outfit_text = session["outfit_suggestion"] or (session["reply"] if not item else "") or ""
    fit_card_text = session["fit_card"] or ""

    return listing_text, outfit_text, fit_card_text


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
