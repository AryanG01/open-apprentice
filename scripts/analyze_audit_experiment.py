"""Summarise a teaching-trial directory: the primary metric is the share of COMMITTED rules (INTENT_READY) that are wrong."""

import glob
import json
import sys
from collections import Counter


def summarise(d: str) -> dict:
    ts = [json.load(open(f)) for f in glob.glob(f"{d}/learn-*.json")]
    ready = [t for t in ts if t["final_state"] == "INTENT_READY" and not t["error"]]
    wrong = [t for t in ready if t["recovered_latent_on_heldout"] is False]
    right = [t for t in ready if t["recovered_latent_on_heldout"]]
    return {
        "trials": len(ts),
        "errors": sum(1 for t in ts if t["error"]),
        "committed": len(ready),
        "correct": len(right),
        "wrong": len(wrong),
        "abstained": sum(1 for t in ts if t["final_state"] == "UNRESOLVED"),
        "wrong_share_of_committed": round(len(wrong) / len(ready), 3) if ready else None,
        "tokens": sum(t["tokens"] for t in ts),
        "by_concept": {
            c: Counter(
                ("right" if t["recovered_latent_on_heldout"] else "wrong")
                for t in ready
                if t["concept"] == c
            )
            for c in ("badge", "spacing")
        },
    }


if __name__ == "__main__":
    for d in sys.argv[1:]:
        print(d, json.dumps(summarise(d), default=dict))
