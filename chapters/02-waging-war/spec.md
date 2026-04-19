# Spec: Gateway-fronted agent with three cost levers

Paired with Chapter 2, "Waging War". Demonstrates the gateway pattern from LiteLLM and Portkey: context discipline, caching, and fallback sit at the gateway layer, not in application code.

## Intent

Route every agent call through a gateway that trims context to the minimum, structures prompts to hit the provider's cache, and falls back to a cheaper or healthier model when the primary degrades.

## Invariants

- No call sends more than 2000 input tokens. Anything larger must summarise first.
- Every call uses a stable prompt prefix so prompt-caching is possible.
- Primary model failures route to a fallback within 500ms. No user-visible outage.
- Cost attribution is recorded per call, tagged by feature and user.
- Monthly spend per user caps at USD 500. Over budget, the gateway rejects.

## The three levers

| Lever | How this spec honours it |
|---|---|
| Context | `max_input_tokens=2000`; full history summarised before send. |
| Caching | Stable system prompt + deterministic tool list ahead of variable user input. Cache TTL 3600s. |
| Fallback | `claude-opus-4-7` primary, `claude-sonnet-4-7` fallback via Bedrock, `gpt-4o` second fallback. |

## Success criteria

- SQL-shaped questions routed to DuckDB, cost USD 0.01 / query, no LLM call.
- LLM-shaped questions average under 350 input tokens.
- Cache hit rate at steady state: >= 70%.
- Primary-to-fallback failover: <= 500ms at p95.
- No user exceeds monthly budget without a gateway-enforced reject.

## Failure modes covered

- Token black hole: no attribution, spend diffuses (Ch. 2).
- Replay-everything agents: history grows linearly with turns (Ch. 2).
- The prompt cache that wasn't: cache key invalidated by timestamp in prefix (Ch. 2).
- Silent cost drift: nobody notices until finance asks (Ch. 11).

## Test dataset

See `golden-dataset.csv`. Each row is a user question tagged with the expected route, token count, and cache behaviour. The field note in Chapter 2 describes the exact failure this spec prevents.
