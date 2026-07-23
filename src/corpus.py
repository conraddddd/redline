"""Schema and validation for Redline's attack corpus (data/corpus/attacks.json).

Categorization rule
--------------------
The three v1 categories sit on two different axes: direct_prompt_injection and
jailbreak are defined by *mechanism* (how the attack is delivered), while
data_exfiltration is defined by *goal* (what it's trying to get). This causes
real overlap in practice — e.g. a DAN-persona jailbreak used to extract the
system prompt. Priority rule: outcome-defined categories absorb
mechanism-matching attacks, because what matters is the damage an attack
caused, not the shape its delivery took — a jailbreak-shaped attack that leaks
the system prompt is fundamentally an exfiltration incident, not a jailbreak.
This mirrors how security incidents are triaged in practice: by impact, not by
delivery vector. See exfil-004 in the corpus for a worked example, and its
`notes` field for the specific reasoning.

No severity field
------------------
v1 deliberately omits a per-attack severity/CVSS-style score. Inventing a
severity weighting scheme with no defensible basis would be worse than having
no severity field at all; per-category attack-success rate is the metric that
carries weight for v1. Revisit if a later phase needs cross-category
prioritization — see README's "Extending to production" section.

Deterministic-pattern precision
--------------------------------
Several attacks pair a deterministic pattern check with the judge
(detection: "both") specifically because presence of the pattern string is
necessary but not sufficient for success: a correctly-refusing target may
legitimately quote the injected token back at the user while declining it
("I noticed your message included 'HACKED', but I'll disregard that
instruction"). The regex/substring check alone would score that as a
success. The judge pass is what distinguishes compliance from
acknowledgment-and-refusal, and its verdict is the one that counts for
ASR — the deterministic hit is a necessary-but-not-sufficient prefilter,
not the final word.

Exfiltration patterns are especially high-recall/low-specificity by nature
(e.g. "you are a" appears in countless harmless completions unrelated to a
leaked system prompt), so for those attacks the judge is doing real
specificity work, not just tie-breaking an already-strong signal.

Jailbreak success is multi-dimensional
---------------------------------------
Jailbreak success criteria often bundle two distinct compromises — persona
adoption ("became DAN") and harmful-content emission ("gave bypass
instructions") — under one judge call rather than scoring them separately.
v1's reported ASR therefore treats *any* partial compromise (persona-only,
content-only, or both) as a success for that attack. This inflates ASR
relative to a stricter "fully compromised" definition; it's disclosed here
rather than silently baked into the numbers.

Known v1 ceiling
-----------------
All jailbreak attacks and the harder exfiltration attacks (context_leakage,
other_user_data_leakage) are judge-only or judge-primary — there is no
deterministic backstop for their subtler failure modes. That means
qwen2.5:7b's own calibration on jailbreak/subtlety judgments is a ceiling on
how precisely those categories can be measured, not just a scoring detail.
Disclosed v1 limitation, not a blocker — see README's "Extending to
production" section.
"""

import json
from pathlib import Path

CATEGORIES = {"direct_prompt_injection", "jailbreak", "data_exfiltration"}
DETECTION_MODES = {"deterministic", "judge", "both"}

REQUIRED_FIELDS = {
    "id",
    "category",
    "subcategory",
    "prompt",
    "technique_tags",
    "success_criteria",
    "expected_target_behavior",
    "source",
    "notes",
}


def validate_attack(attack: dict) -> list[str]:
    """Return a list of schema errors for a single attack; empty if valid."""
    errors = []

    missing = REQUIRED_FIELDS - attack.keys()
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")

    if attack.get("category") not in CATEGORIES:
        errors.append(f"invalid category: {attack.get('category')!r}")

    criteria = attack.get("success_criteria", {})
    detection = criteria.get("detection")
    if detection not in DETECTION_MODES:
        errors.append(f"invalid success_criteria.detection: {detection!r}")
    if detection in {"deterministic", "both"} and not criteria.get("patterns"):
        errors.append("detection requires patterns but none given")

    return errors


def load_corpus(path: Path) -> list[dict]:
    """Load and validate the attack corpus, raising on any schema violation."""
    attacks = json.loads(path.read_text())

    seen_ids = set()
    errors_by_id = {}
    for attack in attacks:
        attack_id = attack.get("id", "<missing id>")
        errors = validate_attack(attack)
        if attack_id in seen_ids:
            errors.append("duplicate id")
        seen_ids.add(attack_id)
        if errors:
            errors_by_id[attack_id] = errors

    if errors_by_id:
        raise ValueError(f"corpus validation failed: {errors_by_id}")

    return attacks
