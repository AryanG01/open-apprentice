"""Check an Open Apprentice change receipt against the files, using only the Python standard library.

  python3 scripts/verify_receipt.py receipt.json [story-card.png]

It recomputes (1) the receipt's own hash, (2) the hash of every approved and result string it lists, (3) the story card PNG's hash if
the PNG is given. It proves the record matches the files and has not been edited; it does not prove the card looks right.
Exit code 0 = everything matches, 1 = something does not."""

import hashlib
import json
import sys


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    r = json.load(open(argv[0], encoding="utf-8"))
    problems: list[str] = []
    claimed = r.pop("receipt_sha256", None)
    if hashlib.sha256(canonical(r)).hexdigest() != claimed:
        problems.append("the receipt was edited: its own hash does not match")
    r["receipt_sha256"] = claimed
    for section in ("approved_text", "result_text"):
        for role, v in r.get(section, {}).items():
            if hashlib.sha256(v["text"].encode("utf-8")).hexdigest() != v["sha256"]:
                problems.append(f"{section}.{role}: text and hash disagree")
    for role, v in r.get("result_text", {}).items():
        same = r["approved_text"].get(role, {}).get("text") == v["text"]
        if same != v.get("identical_to_approved"):
            problems.append(f"result_text.{role}: 'identical' flag is wrong")
    if len(argv) > 1:
        png = open(argv[1], "rb").read()
        if hashlib.sha256(png).hexdigest() != r["result"]["png_sha256"]:
            problems.append("the PNG is not the one this receipt describes")
    for p in problems:
        print("MISMATCH:", p)
    if not problems:
        print(
            "OK: the receipt matches", "the files." if len(argv) > 1 else "itself (no PNG given)."
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
