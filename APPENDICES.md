# Appendices

## A. Evaluation Metrics Reference

### Faithfulness
Measures how grounded the agent's response is in the provided context. High faithfulness means the response is supported by evidence from the data sources.

*High value*: Response directly quotes or paraphrases from source data
*Low value*: Response contains hallucinations or unsupported claims

### Answer Correctness
Measures factual accuracy of the response against ground truth.

*High value*: Response matches the expected answer exactly
*Low value*: Response contains factual errors

### Token Usage
Measures computational cost of LLM calls.

*Optimal*: Uses minimum tokens necessary for accurate answer
*Wasteful*: Uses excessive tokens for simple queries

### Cache Hit Rate
Measures efficiency of memory reuse.

*High value*: Similar queries reuse cached results
*Low value*: Every query triggers new computation

### Route Distribution
Measures proper tool selection.

*Optimal*: Uses SQL for structured data, LLM for reasoning, cache for repeated queries
*Poor*: Uses LLM for everything, or SQL when reasoning is needed

## B. Guardrail Configuration Schema

```yaml
# guardrail-config.yaml schema
max_tokens_per_call: 500  # Maximum tokens per LLM call
min_cache_hit_rate: 0.7   # Minimum acceptable cache hit rate
max_avg_tokens: 350       # Maximum average tokens per LLM call
min_faithfulness: 0.9     # Minimum acceptable faithfulness score
min_answer_correctness: 0.9  # Minimum acceptable answer correctness score
min_sql_route_rate: 0.8   # Minimum percentage of queries that should use SQL

# Allowed data sources
allowed_sources:
  - "sales_data_q1_2026"
  - "product_catalog"
  - "customer_transactions"
  - "metric_definitions"

# Disallowed response patterns
forbidden_phrases:
  - "I don't know"
  - "Based on my analysis"
  - "It's probably"
  - "I think"
  - "I cannot say for sure"
```

## C. Proefballon Integration (planned)

Planned integration with the Proefballon platform is tracked in `LATER.md`. Nothing is wired up in this version of the companion. When the integration lands, each chapter's implementation becomes deployable as an ephemeral experiment with feedback capture and a synthesised learning on expiry.

## D. Sun Tzu Chapter Mapping

Exact mapping used by the book. Principles here must match the ones in `book/outline.md` and the book's Map page.

| Chapter | Sun Tzu | Agent Principle |
|---|---|---|
| 1 | Laying Plans | Spec-Driven Design |
| 2 | Waging War | Token Economics |
| 3 | Attack by Stratagem | Composability |
| 4 | Tactical Dispositions | Schema as Defence |
| 5 | Energy | Tool Design |
| 6 | Weak Points and Strong | Observability |
| 7 | Manoeuvring | Adaptive Orchestration |
| 8 | Variation in Tactics | Multi-Agent Patterns |
| 9 | The Army on the March | Deployment and Ops |
| 10 | Terrain | Enterprise Terrain |
| 11 | The Nine Situations | Failure Modes |
| 12 | The Attack by Fire | When Not to Use AI |
| 13 | The Use of Spies | Feedback Loops |
| 14 | Interlude: Terrain Shifts | Framework evolution |
| 15 | Epilogue | The Victorious Agent |

## E. Glossary

- **OpenSpec**: Specification-driven development where specs drive design, which produces agents, which produce traces, which inform evaluation, which update specs.
- **Proefballon**: An ephemeral experiment: agent-built from a one-paragraph intent, deployed to a throwaway preview URL with TTL, feedback widget injected, learning synthesised when it expires.
- **Commons**: Cross-app shared space for ideas, learnings, patterns, and decisions. The institutional memory.
- **BYOK**: Bring Your Own Key: customers provide their own AI API keys with hierarchical resolution (project → team → tenant → managed fallback).
- **Three decisions**: Promote (graduate to production via full OpenSpec), Pivot (new hypothesis, new experiment), Compost (discard code, keep learning).