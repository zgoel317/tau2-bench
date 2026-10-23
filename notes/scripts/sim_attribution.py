"""Attribute failed episodes to user-simulator behaviours, with overlaps.

For every failed default-mode episode (4 agents x retail/airline/telecom) this records
its failure-mode bucket (classify.py) and these mechanical simulator flags:

  invented_id      a user message states an ID with no source (invented_ids.py)
  stop_on_yes      bucket user_premature_stop: "yes" + ###STOP### in one turn (R8/A10)
  offer_transfer   bucket text_only_transfer: ###TRANSFER### before the tool call (T5)
  fact_never_said  telecom abroad task where the user never says it is abroad (T1 context)
  accepted_shown   R1 only: the agent's last message before the wrong write shows the
                   wrong value, and the user replied yes before the write

python3 sim_attribution.py           # counts + overlaps
"""

import collections
import glob
import json
import re
import subprocess
from pathlib import Path

from classify import (
    DECLINE,
    ROOT,
    WRITES,
    YES,
    classify_db,
    classify_telecom,
    diff_keys,
)
from invented_ids import invented
from stats import SAYS_ABROAD

REPO = Path(__file__).resolve().parents[2]
# the DB the paper runs used (results were committed in 37199f3)
DB = json.loads(
    subprocess.check_output(
        ["git", "-C", str(REPO), "show", "37199f3:data/tau2/domains/retail/db.json"]
    )
)
ITEM = {
    iid: v["options"]
    for p in DB["products"].values()
    for iid, v in p["variants"].items()
}
PAY = {
    pid: pm for u in DB["users"].values() for pid, pm in u["payment_methods"].items()
}


def readable(key, val):
    """Strings a user would see in an agent message for this argument value."""
    if key == "payment_method_id" or key == "payment_id":
        pm = PAY.get(val, {})
        src = pm.get("source", val.split("_")[0])
        words = {
            "gift_card": ["gift card"],
            "paypal": ["paypal"],
            "credit_card": ["credit card", pm.get("last_four", "????")],
        }
        return words.get(src, [str(val)])
    return [str(val).lstrip("#")]


def wrong_values(gold, agent):
    """Readable strings for the agent's wrong argument values."""
    out = []
    for k in diff_keys(agent, gold):
        a, g = agent.get(k), gold.get(k)
        if k == "new_item_ids":
            for ai, gi in zip(a or [], g or []):
                if ai != gi:  # show the option values that differ from the gold item
                    ao, go = ITEM.get(ai, {}), ITEM.get(gi, {})
                    out += [v for o, v in ao.items() if go.get(o) != v]
        elif isinstance(a, (str, int, float)):
            out += readable(k, a)
    return [w for w in out if w]


def r1_exchange(dom, s, task):
    """(shown, accepted, agent_text, user_text) for the first wrong write."""
    msgs = s["messages"]
    gold = [
        a
        for a in task["evaluation_criteria"]["actions"] or []
        if a["name"] in WRITES[dom]
    ]
    for i, m in enumerate(msgs):
        for tc in m.get("tool_calls") or []:
            if m["role"] != "assistant" or tc["name"] not in WRITES[dom]:
                continue
            same = [g["arguments"] for g in gold if g["name"] == tc["name"]]
            if not same or tc["arguments"] in same:
                continue
            g = min(same, key=lambda x: len(diff_keys(x, tc["arguments"])))
            vals = wrong_values(g, tc["arguments"])
            k = max(
                (
                    j
                    for j in range(i)
                    if msgs[j]["role"] == "assistant" and msgs[j].get("content")
                ),
                default=None,
            )
            if k is None:
                return False, False, "", ""
            agent_text = msgs[k]["content"]
            users = [
                x["content"]
                for x in msgs[k + 1 : i]
                if x["role"] == "user" and x.get("content")
            ]
            user_text = " | ".join(users)
            shown = bool(vals) and any(v.lower() in agent_text.lower() for v in vals)
            accepted = (
                bool(users)
                and bool(YES.search(user_text))
                and not DECLINE.search(user_text)
            )
            return shown, accepted, agent_text, user_text
    return False, False, "", ""


def episodes():
    files = sorted(
        f
        for f in glob.glob(ROOT + "*_4trials.json")
        if re.search(r"_(retail|airline|telecom)_(default|base)_", f)
    )
    for f in files:
        dom = re.search(r"_(retail|airline|telecom)_", f).group(1)
        model = Path(f).name.split("_")[0]
        d = json.load(open(f))
        tasks = {t["id"]: t for t in d["tasks"]}
        for s in d["simulations"]:
            if s["reward_info"]["reward"] < 1:
                yield dom, model, s, tasks[s["task_id"]]


def main():
    rows = []
    for dom, model, s, task in episodes():
        bucket = (
            classify_telecom(s, task) if dom == "telecom" else classify_db(dom, s, task)
        )[0]
        flags = set()
        if invented(s, task):
            flags.add("invented_id")
        if bucket == "user_premature_stop":
            flags.add("stop_on_yes")
        if bucket == "text_only_transfer":
            flags.add("offer_transfer")
        if dom == "telecom" and "abroad" in s["task_id"]:
            if not any(
                m["role"] == "user" and SAYS_ABROAD.search(m.get("content") or "")
                for m in s["messages"]
            ):
                flags.add("fact_never_said")
        ex = None
        if bucket == "wrong_arguments":
            ex = r1_exchange(dom, s, task)
            if ex[0] and ex[1]:
                flags.add("accepted_shown")
        rows.append((dom, model, s["task_id"], s["trial"], bucket, flags, ex))

    print(f"failed episodes: {len(rows)}")
    flag_names = [
        "invented_id",
        "stop_on_yes",
        "offer_transfer",
        "fact_never_said",
        "accepted_shown",
    ]
    for fl in flag_names:
        hit = [r for r in rows if fl in r[5]]
        by_bucket = collections.Counter(f"{r[0]}:{r[4]}" for r in hit)
        by_model = collections.Counter(r[1].split("-20")[0] for r in hit)
        print(f"\n{fl}: {len(hit)} failed episodes")
        print("   by bucket:", dict(by_bucket.most_common()))
        print("   by model: ", dict(by_model.most_common()))
    multi = [r for r in rows if len(r[5] & set(flag_names)) > 1]
    print(
        f"\nepisodes with 2+ flags: {len(multi)}",
        collections.Counter(tuple(sorted(r[5])) for r in multi),
    )
    r1 = [r for r in rows if r[4] == "wrong_arguments"]
    print(
        f"\nR1 (retail) shown/accepted:",
        collections.Counter((r[6][0], r[6][1]) for r in r1 if r[0] == "retail"),
    )
    print(
        f"A2 (airline) shown/accepted:",
        collections.Counter((r[6][0], r[6][1]) for r in r1 if r[0] == "airline"),
    )


if __name__ == "__main__":
    main()
