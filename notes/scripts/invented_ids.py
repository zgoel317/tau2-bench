"""Count user-sim turns that state an identifier the simulator had no source for.

An identifier in a user message is "unsupported" if it appears neither in the task's
user_scenario nor earlier in the visible conversation (agent or user messages, and
the user's own tool results). Default mode, 4 agents, retail/airline/telecom.

python3 invented_ids.py            # counts
python3 invented_ids.py --show     # every flagged turn
"""

import collections
import glob
import json
import re
import sys
from pathlib import Path

D = Path(__file__).resolve().parents[2] / "data/tau2/results/final"
PATTERNS = {
    "order_id": re.compile(r"#?W\d{7}\b"),
    "reservation_id": re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{6}\b"),
    "user_id": re.compile(r"\b[a-z]+_[a-z]+_\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    "long_number": re.compile(r"(?<![\d.$])\d{6,}(?!\d|\.\d)"),
    "phone": re.compile(r"\b\d{3}-\d{3}-\d{4}\b"),
}


def norm(x):
    # "#W9502127", "W9502127" and "9502127" are the same order id
    return re.sub(r"#?w(\d{7})\b", r"\1", x.lower()).lstrip("#")


def invented(s, task):
    """[(kind, token, text)] for identifiers a user message states without a source."""
    seen = norm(json.dumps(task["user_scenario"]))
    hits = []
    for m in s["messages"]:
        text = m.get("content") or ""
        if m["role"] == "user" and text:
            for kind, p in PATTERNS.items():
                for tok in p.findall(text):
                    if norm(tok) not in seen:
                        hits.append((kind, tok, text[:200]))
        # agent messages and the user's own tool results are visible to the user
        if m["role"] in ("user", "assistant") or (
            m["role"] == "tool" and m.get("requestor") == "user"
        ):
            seen += " " + norm(text)
    return hits


def main():
    files = glob.glob(str(D / "*_default_*")) + glob.glob(str(D / "*_base_*"))
    files = [
        f for f in files if re.search(r"_(retail|airline|telecom)_(default|base)_", f)
    ]
    c = collections.Counter()
    flagged = []
    for f in sorted(files):
        name = Path(f).name
        model, domain = (
            name.split("_")[0],
            re.search(r"_(retail|airline|telecom)_", name).group(1),
        )
        d = json.load(open(f))
        tasks = {t["id"]: t for t in d["tasks"]}
        for s in d["simulations"]:
            hits = invented(s, tasks[s["task_id"]])
            c[domain, "episodes"] += 1
            if hits:
                r = s["reward_info"]["reward"]
                c[domain, "flagged"] += 1
                c[domain, "flagged_failed"] += r < 1
                for kind, _ in {(h[0], h[1]) for h in hits}:
                    c[domain, kind] += 1
                flagged.append((model, domain, s["task_id"], s["trial"], r, hits))

    for dom in ("retail", "airline", "telecom"):
        kinds = {k[1]: v for k, v in c.items() if k[0] == dom and k[1] in PATTERNS}
        print(
            f"{dom:8} episodes={c[dom, 'episodes']:5} flagged={c[dom, 'flagged']:4} "
            f"(failed {c[dom, 'flagged_failed']})  by kind={kinds}"
        )
    if "--show" in sys.argv:
        for model, dom, tid, trial, r, hits in flagged:
            print(f"\n{model} {dom} {tid[:80]}/{trial} reward={r}")
            for kind, tok, text in hits:
                print(f"   {kind}={tok!r}: {text!r}")


if __name__ == "__main__":
    main()
