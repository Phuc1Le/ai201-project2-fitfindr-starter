# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
It filters relevant items from listings.json based on the input, which represents the user's preference. Out of the 3 input fields, "max_price" should be definite, which means every item listed must have price less than "max_price". "size" can be a bit flexible, but not too far away.The remaning field "description" should be filtered through the keys "title", "description", "style_tags", "color", ... 
If there is a better filtering strategy (semantic search, ...) suggest it to me before coding.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): the description of the wanted items. it might contain the item's name, color, or other details
- `size` (str): a string of normal sizing, for e.g S, M, L for shirts, US 9 for shoes, ...
- `max_price` (float): a decimal number denoting the upper bound for price

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
Return a list of suitable items. Each item is a dict describing a clothing item, like in listings.json

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
If the inputs are relevant but no listings match the description, suggest "closest" 2 listings that are most related if possible (semantically closest), then return to the agent something like
{
    "status": "closest_match"
} 
If the inputs are relevant but no listings match the price, send the agent something like
{
    "status": "price_too_low",
    "lowest_matching_price": 45
} 
If the inputs are relevant but no listings match the size, send the agent something like
{
    "status": "size_relaxed",
    "items": [...]
} so that it automatically retry with loosened constraints (e.g., remove size filter) and inform the user what was adjusted
If the inputs are completely irrelevant (for e.g asking about fishing gears, or books, ...), reply with "We are a clothing store, find the ${item} in a different store. Actually this can be handled by the LLM outside the tool.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Given a specific item and the user's current wardrobe, suggests at most three complete outfit combinations based on scoring system (of course ones with highest score). The outfit must contain the specified item.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): a dict that describe an item, similar to that in listings.json
- `wardrobe` (dict): a dict with one key "items" and value is a list of item dicts

**What it returns:**
<!-- Describe the return value -->
It should return a string that describe an outfit that spans the "category" key. Here is the definition of category:
"category": "string — one of: tops, bottoms, outerwear, shoes, accessories"
Can do this by determine required categories based on new_item['category']
REQUIRED = {
    "tops": ["bottoms", "shoes"],
    "bottoms": ["tops", "shoes"],
    "shoes": ["tops", "bottoms"],
    "outerwear": ["tops", "bottoms", "shoes"],
    "accessories": ["tops", "bottoms", "shoes"]
}
Also the list must contain the specified item.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
If the list doesn't span all 5 categories, determine if the missing category is removable (accessories, outerwear). If it is, still return the suggested string and something like 
{
    "status": "partial_outfit",
    "missing_optional": ["accessories"]
}
If it's not (tops, bottoms, shoes), reply that you can't make a complete outfit with a missing part and return 
{
    "status": "missing_required_category",
    "missing": ["bottoms"]
} 
 for the agent.
If the wardrobe is empty, return something like this to the agent:
{
    "status": "empty_wardrobe"
}
---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
From an outfit description (this might be the output of suggest_outfit(), or the LLM interpretation of that output) and the new_item the user want to buy (if there is one), generate a short fashion-oriented fit card (1-3 sentences).
The output should highlight the outfit's aesthetic,
key pieces, and overall vibe in a natural social-media style.

Avoid repeating exact phrasing across calls.
**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str): the output string from suggest_outfit()
- `new_item` (dict): a dict that describe an item, similar to that in listings.json

**What it returns:**
<!-- Describe the return value -->
Generates a short, shareable description of a complete outfit — the kind of thing someone would caption an Instagram post with.
**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If the outfit is incomplete, return {
    "status": "incomplete_outfit",
    "missing": [category, for e.g "bottoms"]
} to the agent
---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
If search_listings() run successfully, set selected_item = results[0] and proceed to suggest_outfit(). If suggest_outfit fails, fallback to "What happens if it fails or returns nothing:" in Tools/Tool 2: suggest_outfit. If it succeeds, proceed to create_fit_card with the list of items in outfit or the LLM message of suggest_outfit. If create_fit_card fails, fallback to "What happens if it fails or returns nothing:" in Tools/Tool 3: create_fit_card.
A sequence of tools can start at any tools depends on the user input, not necessarily search_listings --> suggest_outfit --> create_fit_card
---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->
Using the Groq API, each tool call results in a message dict of the form:
{"role": "tool", "tool_call_id": "", "content": ""}
each LLM response results in a message dict of the form:
{"role": "assistant", "tool_calls": [...]} or,
{"role": "assistant", "content": "..."}
Each of these are appended to a "messages" list that can capture the conversation history
The LLM can take the result of previous tool call to input the next tool call
---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | execute based on the cases in Tools/Tool 1 spec |
| suggest_outfit | Wardrobe is empty | execute based on the cases in Tools/Tool 2 spec |
| create_fit_card | Outfit input is missing or incomplete | execute based on the cases in Tools/Tool 3 spec |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

---
User query
    │
    ▼
Planning Loop ───────────────────────────────────────────┐
    │                                                    │
    ├─► search_listings(description, size, max_price)    │
    │       │ results=[]                                 │
    │       ├──► [ERROR] → return the tool result to agent                │
    │       │                                            │
    │       │ results=[item, ...]                        │
    │       ▼                                            │
    │   Session: selected_item = results[0]              │
    │       │                                            │
    ├─► suggest_outfit(selected_item, wardrobe)          │
    │       │    
            ├──► [ERROR] → return the result to agent for it to decide which tools to take next     │                                            │
    │   Session: outfit_suggestion = "..."               │
    │       │                                            │
    └─► create_fit_card(outfit_suggestion, selected_item)│
            │                                            │
        Session: fit_card = "..."                        │
            │                                            └─ error path returns here
            ▼
        Return session
## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll give Claude the tool specs in Tools spec, Tool 1 to implement load_listings(), then to create testcases, debug tests
Next, I'll give claude the Tool 2 spec to implement suggest_outfit using data_loader get_wardrobe functions, then write some debug tests for testing
Finally, give claude Tool 3 spec to implement create_fit_card() function and ask it to decide what kind of input it wants for the "outfit" input, whether a string or a list of items
**Milestone 4 — Planning loop and state management:**
I'll give claude the Planning loop and Architecture spec, and the example planning loop from the lab for it to build a clean planning loop and state management. Then I'll add print statements to see tool calls, messages.
---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
search_listings("vintage graphic tee", size="M", max_price=30.0) returns 3 matching listings sorted by relevance.
**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
 FitFindr picks the top result: "Faded Band Tee — $22, Depop, Good condition." Call suggest_outfit(new_item=<band tee>, wardrobe=<user's wardrobe>) returns: "Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape."
**Step 3:**
<!-- Continue until the full interaction is complete -->
create_fit_card(outfit=<suggestion>, new_item=<band tee>) returns: "thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"
**Final output to user:**
<!-- What does the user actually see at the end? -->
Here is a fit card you can post on your socials: "thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"
