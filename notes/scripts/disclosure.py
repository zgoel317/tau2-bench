"""How the "abroad" fact surfaces in telecom abroad tasks (default mode, 4 models).

Each episode is put in one bucket:
  volunteered            user says it before the agent asks
  asked->disclosed_next  agent asks a location question; the next user message says it
  asked->never           agent asks; the user never says it
  never_surfaced         nobody asks, nobody says it
An "ask" is a sentence ending in '?' that matches ASK_LOC (stricter than stats.py,
which matches any mention).
"""

import collections
import glob
import json
import re
from pathlib import Path

from stats import ASK_LOC, SAYS_ABROAD

D = Path(__file__).resolve().parents[2] / "data/tau2/results/final"


def is_ask(text):
    return any(ASK_LOC.search(q) for q in re.findall(r"[^.!?\n]*\?", text))


c = collections.Counter()


def said(m):
    return m["role"] == "user" and SAYS_ABROAD.search(m["content"])


examples = []
for f in sorted(
    glob.glob(str(D / "*_telecom_default_*")) + glob.glob(str(D / "*_telecom_base_*"))
):
    model = Path(f).name.split("_")[0]
    for s in json.load(open(f))["simulations"]:
        if "abroad" not in s["task_id"]:
            continue
        ms = [
            m
            for m in s["messages"]
            if m.get("content") and m["role"] in ("assistant", "user")
        ]
        disc = next((i for i, m in enumerate(ms) if said(m)), None)
        ask = next(
            (
                i
                for i, m in enumerate(ms)
                if m["role"] == "assistant" and is_ask(m["content"])
            ),
            None,
        )
        if disc is not None and (ask is None or disc < ask):
            k = "volunteered"
        elif ask is not None:
            nxt = next((m for m in ms[ask + 1 :] if m["role"] == "user"), None)
            k = "asked->disclosed_next" if nxt and said(nxt) else "asked->never"
            if k == "asked->never":
                examples.append(
                    (
                        model,
                        s["task_id"],
                        s["trial"],
                        ms[ask]["content"][:200],
                        (nxt or {}).get("content", "")[:200],
                    )
                )
        else:
            k = "never_surfaced"
        c[k, "n"] += 1
        c[k, "pass"] += s["reward_info"]["reward"]
        c["all", "n"] += 1

for k in ["volunteered", "asked->disclosed_next", "asked->never", "never_surfaced"]:
    n = c[k, "n"]
    print(
        f"{k:24} n={n:4} ({n / c['all', 'n']:.0%})  pass^1={c[k, 'pass'] / max(n, 1):.2f}"
    )
for e in examples:
    print("\n", e)
