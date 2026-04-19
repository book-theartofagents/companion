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

## C. Proefballon Integration

The companion repository is designed to integrate with Proefballon:

1. Each chapter's implementation can be deployed as an ephemeral experiment
2. Feedback widgets are injected into preview URLs
3. Learnings are automatically synthesized when experiments expire
4. Results are stored in the Commons knowledge layer

## D. Sun Tzu Chapter Mapping

| Chapter | Sun Tzu Principle | Companion Implementation |
|--------|-------------------|--------------------------|
| 1 | Laying Plans | Spec-driven design |
| 2 | Waging War | Use terrain to your advantage (choose right tool) |
| 3 | Attack by Stratagem | Optimize for context efficiency |
| 4 | Tactical Dispositions | Design for feedback loops |
| 5 | Energy | Minimize wasted effort |
| 6 | Weak Points and Strong | Exploit vulnerabilities, avoid strengths |
| 7 | Manoeuvring | Adapt to changing conditions |
| 8 | Variation in Tactics | Flexible response strategies |
| 9 | Army on the March | Efficient resource movement |
| 10 | Terrain | Match tools to context |
| 11 | Nine Situations | Context-aware decision making |
| 12 | Attack by Fire | Use leverage for maximum impact |
| 13 | Use of Spies | Information gathering and validation |
| 14 | Interlude: Terrain Shifts | Adapt when context changes |
| 15 | Epilogue | Knowledge compounds across products |

## E. Glossary

- **OpenSpec**: Specification-driven development where specs drive design, which produces agents, which produce traces, which inform evaluation, which update specs.
- **Proefballon**: An ephemeral experiment: agent-built from a one-paragraph intent, deployed to a throwaway preview URL with TTL, feedback widget injected, learning synthesised when it expires.
- **Commons**: Cross-app shared space for ideas, learnings, patterns, and decisions. The institutional memory.
- **BYOK**: Bring Your Own Key: customers provide their own AI API keys with hierarchical resolution (project → team → tenant → managed fallback).
- **Three decisions**: Promote (graduate to production via full OpenSpec), Pivot (new hypothesis, new experiment), Compost (discard code, keep learning).