# Empório da Música · customer service agent

Prototype of a text-message assistant ("Lia") for Empório da Música, a fictional musical instrument store in
Campo Grande/MS. It answers recurring questions (catalog, prices, stock, order status, store information) and
applies the store's policy manual, so the human team only gets the cases that need a person.

Built for the Artefact AI Engineer technical case.

**Language:** code and documentation are in English. The agent itself talks to customers in Brazilian
Portuguese, the language of the store's customers, so the conversations, the tool payloads and the prompt are in
Portuguese.

```
Customer: Quanto custa o Takamine GD20? Vi que ele tava com desconto
   [tool] get_product({"name": "Takamine GD20"})
Lia:      O Takamine GD20 Dreadnought Natural está R$ 2.199,00. No PIX, sai por R$ 2.089,05
          (5% de desconto). A promoção que você viu ("Oferta Especial") já encerrou, então o
          preço atual é esse mesmo.
```

Five full transcripts, with every tool call and its result, are in [`examples/`](examples/) (generated with
Maritaca `sabia-4`).

## Quick start

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/) (or plain `pip`).

```bash
git clone https://github.com/anderson-ntlabs/emporio-da-musica-agent && cd emporio-da-musica-agent
uv sync --extra dev            # or: python -m venv .venv && pip install -e ".[dev]"
cp .env.example .env           # then set OPENAI_API_KEY (and the provider, see below)

uv run emporio                 # chat in the terminal
uv run emporio --debug         # same, printing every tool call
uv run emporio --session ana   # keeps the conversation in .sessions/ana.json and resumes it

uv run pytest                  # 44 tests, no API key needed
uv run python scripts/run_examples.py   # regenerates examples/ against the real model
```

### Choosing the model provider

The agent talks to any **OpenAI-compatible Chat Completions endpoint with tool calling**. Pick one in `.env`:

| Provider | `OPENAI_BASE_URL` | `LLM_MODEL` (example) | Notes |
|---|---|---|---|
| OpenAI (default) | *(unset)* | `gpt-4.1-mini` | cheap, reliable tool calling |
| Maritaca AI | `https://chat.maritaca.ai/api` | `sabia-4` | models trained for Brazilian Portuguese |
| Ollama (local, free) | `http://localhost:11434/v1` | `qwen2.5:7b-instruct` | needs a model with tool support |

`EMPORIO_NOW=2026-11-03T10:30:00` freezes the store clock (useful to test opening-hours answers).

## How it works

```
                 ┌──────────────────────────── system prompt ───────────────────────────┐
                 │ persona + hard rules (policy §7, §9) · policy table of contents ·    │
                 │ current date/time in Campo Grande                                    │
                 └──────────────────────────────────────────────────────────────────────┘
 customer ──▶ Agent loop (agent.py) ──▶ LLM ──tool calls──▶ tools.py ──▶ store.py     (CSV data + business rules)
    ▲                                    │                          └──▶ policies.py  (PDF → numbered sections)
    └────────────── reply ◀──────────────┘                          └──▶ payments.py  (installment tiers, PIX)
```

The model decides **what to look up**; deterministic code decides **what is true**. Every price, discount,
stock level and order status the customer sees comes from a tool result, never from the model's memory.

| Tool | What it does | Policy it enforces |
|---|---|---|
| `search_products` | Category / text / price-range search, cheapest first, sellable items only | §7.3 never confirm stock without checking |
| `get_product` | Fuzzy name match ("Takamine GD20"), price, active and expired promotions, alternatives when unavailable | §6.2 promo shown with original price and %, §7.3 |
| `simulate_payment` | PIX value, max interest-free installments, whether payment methods can be combined | §3, §3.1, §6.2 (no PIX discount on promo prices) |
| `read_policy` | Returns a whole manual section by number or title | everything else in the manual |
| `check_order` | Order status, only after the buyer's e-mail or phone matches | §9 (LGPD) |
| `store_hours_now` | Open/closed now, next opening, national holidays | §2, §7.1 out-of-hours notice |
| `register_complaint` | Logs a case for the human team (`complaints.jsonl`) and returns a protocol number | §7.3 complaints, 24 business hours |

## Technical decisions

**Approach: function calling, no framework.** The store's questions split cleanly into structured lookups
(catalog, orders) and a short rulebook. Function calling covers both with one mechanism. I did not use
LangChain/LangGraph: the loop is ~60 lines (`agent.py`), every step is visible, and it is unit-tested with a
scripted fake client. A graph framework earns its keep with branching multi-agent flows, persistence backends and
human-in-the-loop interrupts, none of which this prototype needs yet.

**Typed tools instead of a SQL agent.** A text-to-SQL agent would be flexible, but the `customers` table holds
names, phones and e-mails. With free SQL, the privacy rule of §9 becomes a prompt instruction the model can be
talked out of; with a typed `check_order(order_id, email|phone)` it is a code path. The same goes for pricing:
"never stack the PIX discount on a promotion" is one `if` in `store.py`, not a hope.

**Retrieval over the policy manual: section lookup, not embeddings.** The manual has 10 numbered sections
(~2.5k tokens). The system prompt carries its table of contents; the model calls `read_policy("4")` and gets the
whole section. A vector index would add an embedding model and a chunking strategy to solve a problem the
document's own structure already solves, and chunking can split a rule in half (the installment tiers of §3.1 span
four bullets). Past a few dozen documents I would switch to hybrid search (BM25 + embeddings) over the same
section boundaries.

**Model and provider.** The client is the OpenAI SDK pointed at any compatible endpoint, so the provider is a
`.env` change, not a code change. The transcripts in `examples/` were generated with **Maritaca `sabia-4`**, a model
trained for Brazilian Portuguese: the customers write like Brazilians on WhatsApp ("tava", "kkk", "pra"), and the
store's own manual asks for an informal, friendly tone, which is where a Portuguese-native model shows. (I maintain
the `langchain-maritaca` integration, so I also know its tool-calling behaviour well.) The default in
`.env.example` is OpenAI `gpt-4.1-mini`, because it is the key a reviewer is most likely to have. Temperature 0.3:
consistent wording without sounding canned.

**Prompt strategy.** One system prompt (`prompt.py`): persona and tone from §7.1 ("informal but professional,
like a friend who knows music"), the five-step service flow of §7.2, and eleven hard rules mapped to the manual.
Facts stay out of the prompt on purpose: the prompt says *when* to call a tool, the tool says *what* the answer is.
The prompt also states the current date and time in the store's timezone, so "are you open now?" has an answer.

**Interface.** A terminal chat (`emporio`), because the case is about the agent, plus a script that replays fixed
scenarios to produce the transcripts. `Agent.send()` is UI-agnostic: a FastAPI endpoint or a WhatsApp webhook would
wrap the same method.

**Conversation history.** Kept in memory per session and optionally saved to `.sessions/<name>.json`, because
customer service conversations are multi-turn ("and in PIX?" only makes sense after a product was mentioned). The
window sent to the model is capped at the last 12 user turns, cut at a user message so a tool result is never sent
without the call that produced it.

**Failure handling.** Provider errors return a polite fallback with the store phone instead of a stack trace;
malformed tool arguments come back to the model as an error object so it can retry; a turn is capped at 6 tool
rounds.

## Data treatment

The data was audited before writing the agent. Findings and what the code does about each (most are pinned by
tests in `tests/test_store.py`):

| Finding | Treatment |
|---|---|
| 21 of 25 promotions are expired (`is_active=0`), several on products customers will ask about (e.g. Takamine GD20) | only active promotions are applied; expired ones are returned as `promocoes_encerradas` so the agent can say they ended (§7.3) |
| `Ibanez Bass 2X` is `discontinued` but has 13 units in stock; `Kala KA-ABP-CTG` is `coming_soon` with 2 units | "sellable" means `status == active and stock > 0`; the others are shown as unavailable with alternatives |
| `Giannini GF-3D` is active with stock 0 | omitted from searches; `get_product` explains and suggests similar items in the same category |
| Categories 6, 7 and 8 (wind and orchestral strings) exist but have no products, while §1 says the store sells them | searches in those categories say the category has no items at the moment, instead of "we don't sell that" |
| Two customers share `bruno.martins@jmail.com` | order verification checks the e-mail against the customer *of that order*, so the duplicate cannot unlock the other person's orders |
| Orders 3 and 20: `total_brl` differs from the sum of item prices (prices may have changed since) | the order's own total is reported as what was paid; no recomputation |
| Order 3 (delivered, 2025) contains the `coming_soon` ukulele | kept as is; noted here as a data inconsistency to raise with the store |
| The PDF extracts one word per line with pypdf's default mode (Google Docs export) | layout-mode extraction, page headers/footers removed, tables kept as `a \| b` rows |
| Manual inconsistencies: WhatsApp `(67) 3321-4500` in §7 vs `(67) 3341-4444` everywhere else; e-mail written with an accent in §1.2; credit card minimum installment R$ 100 in the table vs tiered minimums in §3.1 | resolved once in `policies.py` as curation notes attached to those sections (store phone, unaccented e-mail, §3.1 tiers), so the agent does not improvise a different answer each time |

### Assumptions

- **Installments (§3.1).** "Up to 3x: no minimum installment (except below R$ 50.00)" is read as *each installment
  must be at least R$ 50*; the R$ 100 in the summary table is the 7x-12x tier.
- **Holidays.** National holidays for 2026-2027, with Carnival and Corpus Christi treated as closed. Municipal
  holidays of Campo Grande are not covered.
- **Purchases.** The assistant informs and guides; it does not sell, reserve stock or approve refunds. Returns and
  complaints are registered for a person to act on (§7.3).
- **Order identity.** Order number plus the buyer's e-mail or phone (last 8 digits) is enough to disclose an order.
  A wrong combination and a non-existent order get the same answer, so the tool cannot be used to enumerate orders.

## Tests

`uv run pytest` runs 44 tests without any API key: the business rules (`test_store.py`), the PDF parsing
(`test_policies.py`) and the agent loop with a scripted fake model (`test_agent.py`: tool results fed back,
provider failure, malformed arguments, history window, session round trip, opening hours around the Finados
holiday).

## What the first real runs showed (and what changed)

The unit tests passed before the agent ever talked to a model; the first transcripts still exposed four problems,
each fixed in its own commit (`git log`), with a regression test where the fix was in code:

| Observed in the transcript | Fix |
|---|---|
| Asked for a WhatsApp number, the model **invented one**, right after reading the policy section that mentions it | store address, phone and e-mail pinned in the system prompt with "never invent contact data" |
| Given order number + e-mail, it answered the return request **without calling `check_order`**, so it missed that order 8 shipped in February and never arrived | prompt rule: call `check_order` as soon as the data is given; the tool now flags shipped orders past their estimate as late, in words the model cannot misread |
| It answered "qual a capital da Austrália?" | out-of-scope rule made explicit: decline even when the answer is known |
| The tool said R$ 408,40 and the model wrote R$ 408,41 (429,90 × 0,95 = 408,405) | money rounded half up in code, so the tool and the model agree; out-of-stock alternatives keep the same string type |

Plus one infrastructure bug: a stale `OPENAI_API_KEY` in the shell shadowed the `.env`, and the provider error was
swallowed, so every reply was the fallback message. Errors are now logged and the example runner refuses to write
a transcript made of fallback replies.

## Known limitations and next steps

- **Small embellishments remain.** In `examples/01` the model says all the steel-string options have a folk body
  shape, which the search result does not state; in `examples/05` it offers to warn about future promotions, which
  it cannot do. Both are the kind of claim an output check would catch (below).

- **No evaluation set yet.** The transcripts in `examples/` are spot checks. Next: 40-60 labelled questions with the
  expected tool calls and facts, scored automatically (tool-call accuracy, groundedness of prices against the
  tool output, refusal correctness), run on every prompt or model change.
- **Business-hours logic** ignores the extended hours of special dates mentioned in §2.
- **Shipping quotes** are out of scope: the manual says freight is computed from CEP, weight and size, and there
  is no data or carrier API for that, so the agent explains the rules (§5) and refers the quote to the team.
- **Complaints** go to a local JSONL file; in production this is a ticket in the store's helpdesk or a message to
  the team's WhatsApp group.
- **Single tenant, single language.** Fine for one store; a chain would need tenant-scoped data and prompts.
- **Guardrails** are prompt rules plus typed tools. With real traffic I would add output checks (every price in the
  reply must appear in a tool result of that turn) and log conversations for review, with PII redaction.

## Use of coding assistants

I built this as a supervised agentic session in **Claude Code** (Anthropic's terminal agent), which is how I work
day to day. I study this way of working, too: my research includes an autoethnography of 800+ of my own Claude
Code sessions. How the work was split:

- **I set the frame**: the goal, the brief's deliverables as acceptance criteria, Python only, a real commit
  history, a time box, and the model provider (Maritaca, for Portuguese-native replies).
- **It proposed, I decided.** The architecture choices above (typed tools instead of a SQL agent, section lookup
  instead of embeddings, no framework, identity check on orders) were proposed by the assistant with the trade-offs
  you read in this README; I accepted or redirected them.
- **Data audit before code.** The first step was profiling the CSVs and reading the whole manual looking for
  contradictions. The "Data treatment" table came out of that pass, and most of it became tests.
- **Small, tested steps.** Each commit is a milestone that passed the tests and lint before it was made.
- **Review where it matters: the real transcripts.** The four defects in "What the first real runs showed" were
  caught by reading actual conversations with the model, not by the unit tests. That review loop, more than the
  typing, is where I think the engineering is.
- The conversations in `examples/` are unedited model output from `scripts/run_examples.py`.

## Project layout

```
src/emporio_agent/
  store.py      data loading, pricing, availability and order rules
  payments.py   installment tiers and PIX (policy §3)
  policies.py   PDF → sections, curation notes
  tools.py      tool schemas, dispatch, store hours
  prompt.py     system prompt
  agent.py      tool-calling loop, provider adapter, history
  cli.py        terminal chat
scripts/run_examples.py   replays the scenarios and writes examples/
data/                     the store's files as provided (CSV names normalized)
examples/                 conversation transcripts
tests/
```
