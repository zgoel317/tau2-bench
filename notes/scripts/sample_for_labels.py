"""Print the random samples that were hand-labelled in simulator-priorities.md.

python3 sample_for_labels.py r1   # 20 of the 127 retail R1 episodes where the wrong value was shown and accepted (seed 1)
python3 sample_for_labels.py r2   # 20 of the 94 retail R2 episodes (seed 2)
python3 sample_for_labels.py a5   # 12 of the 34 airline A5 episodes (seed 2)
python3 sample_for_labels.py r6   # all 25 retail R6 episodes (no sampling)
python3 sample_for_labels.py r2 --full   # the r2 sample with whole conversations (used for the final labels)
"""

import collections
import random
import sys

import sim_attribution as sa
from classify import WRITES, classify_db, diff_keys


def r1():
    rows = []
    for dom, model, s, task in sa.episodes():
        if dom == "retail" and classify_db(dom, s, task)[0] == "wrong_arguments":
            ex = sa.r1_exchange(dom, s, task)
            if ex[0] and ex[1]:
                rows.append((model, s, task, ex))
    print(len(rows), "shown and accepted")
    for model, s, task, ex in random.Random(1).sample(rows, 20):
        gold = [
            a
            for a in task["evaluation_criteria"]["actions"]
            if a["name"] in WRITES["retail"]
        ]
        writes = [
            (tc["name"], tc["arguments"])
            for m in s["messages"]
            if m["role"] == "assistant"
            for tc in m.get("tool_calls") or []
            if tc["name"] in WRITES["retail"]
        ]
        diffs = []
        for n, a in writes:
            same = [g["arguments"] for g in gold if g["name"] == n]
            if same and a not in same:
                g = min(same, key=lambda x: len(diff_keys(x, a)))
                for k in diff_keys(a, g):
                    if k == "new_item_ids":
                        diffs.append(
                            (
                                k,
                                [
                                    (sa.ITEM.get(x), sa.ITEM.get(y))
                                    for x, y in zip(a[k], g[k])
                                    if x != y
                                ],
                            )
                        )
                    else:
                        diffs.append((k, a.get(k), g.get(k)))
        print(f"\n### {model.split('-20')[0]} retail {s['task_id']}/{s['trial']}")
        print("  SCEN:", task["user_scenario"]["instructions"]["reason_for_call"][:600])
        print("  DIFF agent vs gold:", str(diffs)[:500])
        print("  USER:", ex[3][:200])


def partial(dom, seed, n):
    """Episodes where only some gold writes happened: scenario, missing writes, last user turns."""
    key = "order_id" if dom == "retail" else "reservation_id"
    rows = [
        (m, s, t)
        for d, m, s, t in sa.episodes()
        if d == dom and classify_db(d, s, t)[0] == "incomplete_multi_step"
    ]
    print(len(rows), "episodes")
    for model, s, task in random.Random(seed).sample(rows, n):
        gold = [
            (a["name"], a["arguments"].get(key))
            for a in task["evaluation_criteria"]["actions"]
            if a["name"] in WRITES[dom]
        ]
        done = [
            (tc["name"], tc["arguments"].get(key))
            for m in s["messages"]
            if m["role"] == "assistant"
            for tc in m.get("tool_calls") or []
            if tc["name"] in WRITES[dom]
        ]
        missing = list(
            (collections.Counter(gold) - collections.Counter(done)).elements()
        )
        print(
            f"\n### {model.split('-20')[0]} {dom} {s['task_id']}/{s['trial']}  MISSING={missing}"
        )
        print("  SCEN:", task["user_scenario"]["instructions"]["reason_for_call"][:450])
        if "--full" in sys.argv:
            conversation(s)
        else:
            users = [
                m["content"]
                for m in s["messages"]
                if m["role"] == "user" and m.get("content")
            ]
            print("  USER LAST 3:", " || ".join(u[:170] for u in users[-3:]))


def conversation(s, last=None):
    """Every user/agent message, plus the agent's non-read tool calls."""
    lines = []
    for m in s["messages"]:
        if m["role"] in ("user", "assistant") and m.get("content"):
            lines.append(f"  {m['role'][0].upper()}: {m['content'][:260]!r}")
        for tc in m.get("tool_calls") or []:
            if m["role"] == "assistant" and not tc["name"].startswith(
                ("get_", "find_")
            ):
                lines.append(f"  CALL {tc['name']} {str(tc['arguments'])[:120]}")
    print("\n".join(lines[-last:] if last else lines))


def r6():
    """All R6 episodes (no write, user ended the call), with the end of each conversation."""
    for dom, model, s, task in sa.episodes():
        if dom == "retail" and classify_db(dom, s, task)[0] == "ended_without_acting":
            print(f"\n### {model.split('-20')[0]} retail {s['task_id']}/{s['trial']}")
            print(
                "  SCEN:",
                task["user_scenario"]["instructions"]["reason_for_call"][:350],
            )
            conversation(s, last=10)


if __name__ == "__main__":
    {
        "r1": r1,
        "r2": lambda: partial("retail", 2, 20),
        "a5": lambda: partial("airline", 2, 12),
        "r6": r6,
    }[sys.argv[1]]()
