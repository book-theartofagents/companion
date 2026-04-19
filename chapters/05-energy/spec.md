# Spec: Narrow, typed, bounded MCP tools

Paired with Chapter 5, "Energy". Demonstrates the Model Context Protocol shape: tools expose pydantic-validated input schemas, return bounded outputs, and names are documentation the model reads on every call.

## Intent

An agent working a support-ticket workflow reaches external systems only through a small set of MCP-shaped tools. Each tool does one thing. Each tool's input is validated by pydantic. Each tool's output is bounded. Selection is driven by query shape; a selector maps intent to the narrowest tool that answers it.

## The five properties of a good tool

| Property | Realised in this spec |
|---|---|
| Narrow scope | `get_order_status(order_id)` returns order status; it does not fetch items, addresses, or the customer's entire history. |
| Typed parameters | Every tool's input is a pydantic model with constrained types (UUID, enum, integer range). |
| Bounded outputs | Every tool response declares `max_rows`; the server enforces it, the client does not hope. |
| Meaningful names | `search_tickets_by_status`, not `api_call_17`. The name carries signal; the description does not have to compensate. |
| Informative errors | `OrderNotFound(order_id=...)` beats `500 internal server error`. The model's next move is informed. |

## Invariants

- Every tool input validates against a pydantic model before the call runs.
- Every tool output is bounded by `max_rows` or by a fixed record shape.
- Tool dispatch is whitelisted. A name not in the registry refuses.
- No tool accepts a free-form SQL or command string. Structure is in parameters, not in a smuggled sentence.
- Tool errors carry enough context for the agent to decide its next move without re-calling the same way.

## Success criteria

- Selection accuracy: 100% on the golden dataset. Each query is answered by the narrowest tool.
- Response size: <= 2000 tokens per tool call. The tool returns summary + pointer, not the full object.
- Schema rejection: unknown tool names or invalid parameters refuse at dispatch, not at runtime.
- Firehose tools: 0 present. If a tool returns a full dataset in one call, the spec rejects it.
- Silent success: 0 tolerated. Every tool raises on failure with a structured error type.

## Failure modes covered

- The firehose: returns the full dataset, pushes filtering to the model (Ch. 5).
- The single-string tool: one free-form `query` parameter the tool re-parses (Ch. 5).
- The silent-success tool: returns `{ok: true}` when the write actually errored (Ch. 5).
- Hallucinated tool call: model emits a tool name outside the registry (Ch. 4 + Ch. 5).

## Test dataset

See `golden-dataset.csv`. Each row is a user question, the tool the selector should pick, the typed parameters the tool should receive, and the expected bounded response shape.
