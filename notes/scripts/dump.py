"""Compact dump of one paper trajectory.

python3 dump.py <file-prefix> <task_id> <trial> [maxchars]
e.g. python3 dump.py gpt-4.1-2025-04-14_retail_default 20 0
"""

import glob
import json
import os
import sys

ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../data/tau2/results/final/"
)
prefix, tid, trial = sys.argv[1], sys.argv[2], int(sys.argv[3])
mx = int(sys.argv[4]) if len(sys.argv) > 4 else 300
d = json.load(open(glob.glob(ROOT + prefix + "*_4trials.json")[0]))
s = next(x for x in d["simulations"] if x["task_id"] == tid and x["trial"] == trial)
t = next(x for x in d["tasks"] if x["id"] == tid)
ri = s["reward_info"]
print(
    "REWARD", ri["reward"], ri.get("reward_breakdown"), "END", s["termination_reason"]
)
print("SCENARIO:", json.dumps(t["user_scenario"]["instructions"])[:1500])
ec = t["evaluation_criteria"]
print(
    "GOLD:",
    [
        (a["requestor"][0], a["name"], a["arguments"])
        for a in ec["actions"] or []
        if not a["name"].startswith(
            ("get_", "find_", "search", "calc", "list", "think")
        )
    ],
)
print("COMM:", ec.get("communicate_info"), "| NL:", ec.get("nl_assertions"))
print(
    "ENV:",
    [
        (c["env_assertion"]["func_name"], c["env_assertion"]["arguments"], c["met"])
        for c in ri.get("env_assertions") or []
    ],
)
for m in s["messages"]:
    r = m["role"][:4].upper()
    if m["role"] == "tool":
        print(f"    [tool] {(m.get('content') or '')[:160]}")
        continue
    if m.get("content"):
        print(f"{r}: {m['content'][:mx]}".replace("\n", " "))
    for tc in m.get("tool_calls") or []:
        print(f"  {r} -> {tc['name']}({json.dumps(tc['arguments'])[:200]})")
