# Running notes for README (fold into Phase 5 Findings / limitations)

Scratch notes captured during development — not polished writeup, just
observations that need to survive until the README gets written so they
aren't rediscovered (or lost) at Phase 5.

## Latency-vs-category confound (found during Phase 2 runner validation)

Insight appears to have two very different response paths:

- **RAG-miss deflection**: when retrieval finds no relevant context, Insight
  returns a short "we don't have information on that" reply in well under
  200ms (observed: 70ms).
- **Engaged generation**: when retrieval finds relevant context (or the
  attack prompt resembles a real query), full llama3 generation runs,
  taking anywhere from ~2s to 90s+ depending on concurrency queueing.

This matters for analysis: **elapsed_ms is not just a performance metric,
it's a weak proxy for whether the attack ever meaningfully engaged the
model at all.** A fast response likely means the attack didn't retrieve
relevant context and got deflected before generation really happened, not
that the attack failed to work against a "loaded gun." Category-level ASR
comparisons should not assume uniform engagement across attacks — this is
a known limitation to name explicitly in the README rather than something
a reader has to infer from the numbers.

## Concurrency ceiling (Phase 2 runner tuning)

Initial baseline run at concurrency_limit=6 / request_timeout_s=30 produced
30/66 timeouts, concentrated in jailbreak and the more elaborate
exfiltration attacks (i.e. missing data biased toward the categories where
attack success is hardest to measure — exactly the ones that matter most).
Root cause: Insight holds a single embedded Qdrant client and local Ollama
generation is effectively single-threaded on the dev machine (M2 Max), so
concurrency past ~2-3 in-flight requests doesn't add throughput, only queue
depth. Fixed by dropping to concurrency_limit=3 / request_timeout_s=90 (see
src/config.py docstring for the same reasoning). Worth naming in the
README as a real constraint of running against a locally-hosted single-GPU
target, not a runner bug.
