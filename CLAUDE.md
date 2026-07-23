# Redline — LLM Red-Teaming & Guardrail Evaluation Harness

## Owner context
Portfolio project #2 by Conrad Asante — CS + cybersecurity background (CEH),
building an AI engineering CV. Companion to `insight-assistant` (a locally-deployed
evaluated RAG customer-support assistant on his GitHub), which is Redline's primary
demo target.

**Explain design decisions as you go — Conrad needs to defend every line in an
interview.** He learns by understanding, not by pasting.

## What Redline is
A target-agnostic tool that:
1. Hits any LLM application HTTP endpoint with a curated battery of adversarial
   prompts.
2. Scores which attacks succeeded (deterministic checks + LLM-as-judge).
3. Measures the effect of a simple guardrail layer via before/after evaluation.

The CV story: *"I built a RAG system, then red-teamed it."* Insight's `/draft`
endpoint is the demo target. Redline itself is a general tool.

## Attack categories (v1)
- **Direct prompt injection** — ignore-previous-instructions, role overrides,
  delimiter escapes, system-prompt spoofs
- **Jailbreak** — role-play framings, hypothetical scenarios, DAN-style, character
  fictional framings
- **Data exfiltration** — attempts to extract system prompt, retrieved context,
  or KB contents

Out of scope for v1: indirect injection (KB poisoning), output manipulation,
multimodal. Named in "Extending to production."

## Stack (decided — don't change without discussion)
- Python 3.14
- Ollama for both target (llama3, via Insight) and judge (qwen2.5:7b — same
  calibrated judge Conrad used in Insight's Phase 4b)
- HTTP client (httpx) for hitting the target endpoint
- JSON everything — attack corpus, results, config

Reuses Insight's proven patterns: JSON-schema-constrained judge output,
deterministic + LLM-judge dual scoring, per-category aggregates + illustrative
subsets.

## Guardrail scope (v1)
- Regex patterns for known attack fragments
- Input length limits
- Embedding-similarity check against known-attack embeddings (reuse
  mxbai-embed-large via Ollama, same as Insight)

No LLM-classifier fallback in v1. Named for v2.

## Target contract
Target endpoint accepts POST with `{query: str}` and returns `{draft: str, ...}`.
Insight's `/draft` fits directly. Runner must be configurable to hit any URL
matching this contract via `.env` or CLI arg.

## Metrics
- Attack-success rate (ASR) per category, baseline vs guarded
- Per-attack detail (which prompts hit, which missed)
- Category-level ASR delta after guardrail

## Five-day roadmap
1. **Attack corpus curation** — 60–100 categorized attacks in JSON, sourced
   from OWASP examples, Garak's test suite, HackAPrompt, promptfoo templates,
   published research. Each attack: `{id, category, prompt, success_criteria,
   source}`.
2. **Attack runner** — module that reads corpus, hits target endpoint per
   attack, records raw responses. Parameterized target URL.
3. **Scoring layer** — deterministic checks (regex, substring match against
   known leak patterns) + qwen2.5:7b judge with per-category rubric. Structured
   JSON judge output, same discipline as Insight's answer_eval.
4. **Guardrail** — pre-filter module (regex + length + embedding similarity).
   Before/after eval run.
5. **README + writeup + CV bullet + push.**

## Conventions carried from Insight
- `.env` + pydantic-settings for config
- Absolute imports (`from src.<mod> import ...`); run via `python -m src.<mod>`
- Per-experiment JSON output persisted to `data/results/`
- README leads with results section; negative results reported honestly
- Commit at each phase boundary with descriptive messages
- `.gitignore` `.venv/`, `.env`, `.claude/`, `data/results/*.json` (or keep — TBD)

## Interview-defensibility standards
Every design decision must have a *why* Conrad can articulate. Same standard
as Insight: explain rubric choices, judge-model choice, category definitions,
guardrail approach. Reasoning goes in module docstrings, not comments.

## What "done" means for v1
A public GitHub repo with:
- The three-category attack corpus (60–100 prompts, categorized, sourced)
- Working runner pointed at Insight's `/draft`
- Baseline + guarded ASR numbers per category in a README results table
- A prose "Findings" section (why certain attacks worked, why the guardrail
  helped or didn't, honest negative results)
- An "Extending to production" section covering indirect injection, LLM
  classifier guardrail, KB poisoning, multimodal