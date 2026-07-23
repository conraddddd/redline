"""Attack runner: hits a target LLM-application endpoint with each attack in
the corpus and records the raw response for later scoring (Phase 3).

Concurrency model
------------------
asyncio + httpx.AsyncClient rather than threading: the bottleneck here is
Ollama generation latency, not CPU, so cooperative IO concurrency is the
right primitive. An asyncio.Semaphore bounds how many requests are in
flight at once; a slow attack only occupies its own semaphore slot, so it
can't starve the rest of the batch the way a fixed thread pool with a
hung worker would.

Failure handling
------------------
Each attack gets one retry on timeout/connection error/non-2xx status,
then gives up and records the failure (ok=False, error=<message>) rather
than raising — one bad attack must never abort the whole run. The
per-request timeout is what bounds a hung Ollama call; without it a
single stuck generation could occupy a semaphore slot indefinitely.

Reachability is checked once at startup (a real smoke-test POST, since
the target contract exposes no dedicated health endpoint), not per
request, so a misconfigured TARGET_URL fails immediately instead of
burning through the whole corpus as timeouts before anyone notices.

Output shape
------------
Results are wrapped in a `meta` + `results` envelope rather than written
as a bare list, so a run's condition/target/corpus-count travel with the
data instead of being inferred from the filename. Rows stay lean (just
attack_id + category, not the full corpus entry) — Phase 3 loads
data/corpus/attacks.json independently and joins on attack_id, so the
two files can't drift out of sync with each other.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.config import settings
from src.corpus import load_corpus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("redline.runner")

CORPUS_PATH = Path("data/corpus/attacks.json")
RESULTS_DIR = Path("data/results")


def preflight_check(target_url: str, timeout_s: float = 5.0) -> None:
    """Fail fast if the target endpoint isn't reachable, before running the batch.

    Deliberately synchronous (plain httpx.post, not AsyncClient): this is a
    single one-shot call made before the event loop or semaphore exist, so
    there's no concurrency to coordinate — reaching for async here would
    just be asyncio.run() overhead around a single blocking call.
    """
    try:
        response = httpx.post(target_url, json={"query": "ping"}, timeout=timeout_s)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Target unreachable at {target_url}: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Target at {target_url} returned {response.status_code} on smoke test "
            f"(expected 200): {response.text[:200]}"
        )


async def run_attack(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, attack: dict) -> dict:
    attack_id = attack["id"]
    attack_category = attack["category"]

    async with semaphore:
        request_ts = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        error = None

        for attempt in (1, 2):
            try:
                response = await client.post(
                    settings.target_url,
                    json={"query": attack["prompt"]},
                    timeout=settings.request_timeout_s,
                )

                if response.status_code == 200:
                    # Measured from the first attempt, not just the final one, so
                    # elapsed_ms captures the cost of any retry (including the
                    # forced backoff below) rather than hiding it.
                    elapsed_ms = round((time.monotonic() - start) * 1000)
                    return {
                        "attack_id": attack_id,
                        "attack_category": attack_category,
                        "request_ts": request_ts,
                        "response_text": response.json().get("draft"),
                        "elapsed_ms": elapsed_ms,
                        "http_status_code": response.status_code,
                        "ok": True,
                        "error": None,
                    }

                error = f"unexpected status {response.status_code}: {response.text[:200]}"

            except httpx.HTTPError as exc:
                error = f"{type(exc).__name__}: {exc}"

            if attempt == 1:
                logger.warning("attack %s attempt 1 failed (%s), retrying", attack_id, error)
                await asyncio.sleep(settings.retry_delay_s)

        elapsed_ms = round((time.monotonic() - start) * 1000)
        logger.warning("attack %s failed after retry: %s", attack_id, error)
        return {
            "attack_id": attack_id,
            "attack_category": attack_category,
            "request_ts": request_ts,
            "response_text": None,
            "elapsed_ms": elapsed_ms,
            "http_status_code": None,
            "ok": False,
            "error": error,
        }


async def run_all(attacks: list[dict]) -> list[dict]:
    semaphore = asyncio.Semaphore(settings.concurrency_limit)
    async with httpx.AsyncClient() as client:
        tasks = [run_attack(client, semaphore, attack) for attack in attacks]
        return await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Redline attack runner")
    parser.add_argument(
        "--guarded",
        action="store_true",
        help="Label this run as 'guarded' (guardrail applied). Default: baseline.",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=CORPUS_PATH,
        help="Path to the attack corpus JSON file.",
    )
    args = parser.parse_args()
    condition = "guarded" if args.guarded else "baseline"

    attacks = load_corpus(args.corpus)
    logger.info("loaded %d attacks from %s", len(attacks), args.corpus)

    logger.info("checking target reachability at %s", settings.target_url)
    try:
        preflight_check(settings.target_url)
    except RuntimeError as exc:
        logger.error(str(exc))
        sys.exit(1)

    started_at = datetime.now(timezone.utc).isoformat()
    results = asyncio.run(run_all(attacks))
    finished_at = datetime.now(timezone.utc).isoformat()

    n_ok = sum(1 for r in results if r["ok"])
    logger.info("run complete: %d/%d succeeded", n_ok, len(results))

    output = {
        "meta": {
            "condition": condition,
            "target_url": settings.target_url,
            "corpus_path": str(args.corpus),
            "corpus_count": len(attacks),
            "concurrency_limit": settings.concurrency_limit,
            "started_at": started_at,
            "finished_at": finished_at,
        },
        "results": results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"run_{timestamp}_{condition}.json"
    out_path.write_text(json.dumps(output, indent=2))
    logger.info("wrote results to %s", out_path)


if __name__ == "__main__":
    main()
