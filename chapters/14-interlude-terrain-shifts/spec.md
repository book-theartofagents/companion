# Spec: Framework timeline analyser and adapter protocol

Paired with Chapter 14, "Interlude: The Terrain Shifts". Demonstrates the two lessons from the chapter: frameworks are mortal, protocols outlast them. Builds a timeline analyser for the first and an adapter pattern for the second.

## Intent

Two outputs in one script:

1. **Survivability report.** Load a CSV of framework events from 2022 to 2026 (launch, acquisition, pivot, deprecation, protocol standardisation). Classify each project's current state. Flag bus-factor-of-one risks. Rank survivors by governance model.
2. **Adapter protocol demo.** A tool-calling interface that runs against two different framework implementations behind the same protocol. Swap the framework, the caller does not notice. This is the MCP pattern in miniature.

## Invariants

- The analyser never hard-codes a framework's API. Every call goes through a protocol.
- Swapping the implementation is a one-line change in configuration. Application code is unchanged.
- Projects with a single maintainer are flagged as bus-factor-of-one. This is a classification, not a judgement.
- Protocol standardisation events are graded separately from framework events. Adoption compounds across implementations.
- The report is data-driven, not opinion-driven. A project's state follows from its events.

## Timeline classifications

| State | Meaning |
|---|---|
| ACTIVE | Project is maintained, no acquisition or pivot event. |
| ACQUIRED | Ownership moved to a vendor. Roadmap now follows vendor strategy. |
| PIVOTED | Project thesis changed publicly. Old users may fit, may not. |
| DEPRECATED | Maintainers named the end. Successor exists. |
| ABSORBED | Consolidated into a successor project by the same org. |
| PROTOCOL | Moved from framework to standard with multi-vendor governance. |

## Success criteria

- Every row in the timeline is classified.
- At least one ACTIVE, one ACQUIRED, one PIVOTED, one ABSORBED, one PROTOCOL event is present.
- Bus-factor-of-one projects are flagged.
- Adapter demo runs against two implementations and returns identical shapes.
- Switching implementations does not require editing call-site code.

## Failure modes covered

- Hard-coding a proprietary framework API (Ch. 14). Rewrite when the framework pivots.
- Treating vendor-backed open source as community-led (Ch. 14). Wrong mental model, wrong planning horizon.
- Missing the acquisition signal (Ch. 14). Project is still open source, roadmap is not.
- Betting on bus-factor-of-one (Ch. 14). Healthy today, brittle tomorrow.

## Test dataset

See `golden-dataset.csv`. One row per framework event. Covers the projects named in the chapter: LangChain, LangGraph, AutoGen, Semantic Kernel, Microsoft Agent Framework, LlamaIndex, DSPy, Ragas, TruLens, Langflow, Aider, Instructor, Rebuff, LLM Guard, MCP.
