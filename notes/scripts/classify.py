"""Heuristic failure-mode classifier for the tau2-bench paper trajectories.

python3 classify.py [out.json]   # prints per-file counts; optional JSON of example ids per mode
"""

import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../data/tau2/results/final/"
)
WRITES = {
    "retail": {
        "cancel_pending_order",
        "exchange_delivered_order_items",
        "modify_pending_order_address",
        "modify_pending_order_items",
        "modify_pending_order_payment",
        "modify_user_address",
        "return_delivered_order_items",
    },
    "airline": {
        "book_reservation",
        "cancel_reservation",
        "send_certificate",
        "update_reservation_baggages",
        "update_reservation_flights",
        "update_reservation_passengers",
    },
}
AUTH = {
    "find_user_id_by_name_zip",
    "find_user_id_by_email",
    "get_user_details",
    "get_customer_by_phone",
    "get_customer_by_id",
    "get_customer_by_name",
}
REFUSE = re.compile(
    r"unable|cannot|can't|can not|not able|not possible|not eligible|unfortunately|policy|not allowed",
    re.I,
)
# user-sim premature termination: agent asks to confirm, user says yes and ###STOP### in the same turn
ASK = re.compile(r"\?|confirm|proceed|shall I|would you like", re.I)
YES = re.compile(
    r"\b(yes|yeah|yep|please (go ahead|proceed)|go ahead|that[’']?s correct|sounds good|please do)\b",
    re.I,
)
DEFER = re.compile(
    r"reach out|be in touch|get back|be back|come back|check back|once (my|the|it)|when (my|the|it)|later|wait for",
    re.I,
)
DECLINE = re.compile(
    r"prefer not|won[’']?t make|keep (my|the) (current|reservation|order)|not (to )?(proceed|make)|leave it as is|forget about it",
    re.I,
)
# fixed in tau2-bench v1.0.0 (CHANGELOG "Airline task fixes" / "Retail task fixes")
FIXED = {
    "airline": {
        2,
        5,
        7,
        9,
        12,
        13,
        14,
        15,
        16,
        18,
        19,
        21,
        23,
        25,
        27,
        29,
        30,
        32,
        33,
        34,
        35,
        36,
        37,
        38,
        39,
        42,
        43,
        44,
        45,
    },
    "retail": {
        0,
        1,
        2,
        3,
        4,
        8,
        12,
        13,
        15,
        18,
        20,
        21,
        22,
        28,
        29,
        33,
        34,
        54,
        55,
        59,
        62,
        76,
        91,
        98,
        99,
        100,
        107,
    },
}


def tool_calls(msgs, role):
    """[(name, args, ok)] for successful/failed calls made by `role`."""
    out, pending = [], []
    for m in msgs:
        if m["role"] == role and m.get("tool_calls"):
            pending += [(tc["name"], tc["arguments"]) for tc in m["tool_calls"]]
        elif m["role"] == "tool" and pending:
            n, a = pending.pop(0)
            out.append((n, a, not (m.get("content") or "").startswith("Error")))
    return out


def canon(n, a):
    return n + json.dumps(a, sort_keys=True)


def diff_keys(a, b):
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def last_text(msgs, role):
    return next(
        (
            m["content"] or ""
            for m in reversed(msgs)
            if m["role"] == role and m.get("content")
        ),
        "",
    )


def confirm_then_stop(msgs):
    t = [m for m in msgs if m["role"] in ("user", "assistant") and m.get("content")]
    return (
        len(t) >= 2
        and t[-2]["role"] == "assistant"
        and "###STOP###" in t[-1]["content"]
        and ASK.search(t[-2]["content"])
        and YES.search(t[-1]["content"])
        and not DECLINE.search(t[-1]["content"])
    )


def classify_db(dom, s, task):
    ri, msgs = s["reward_info"], s["messages"]
    if s["termination_reason"] != "user_stop":
        return "step_cap", ""
    db_ok = ri["db_check"]["db_match"] if ri.get("db_check") else True
    if db_ok:
        return "info_not_conveyed", ""
    gold = [
        a
        for a in task["evaluation_criteria"]["actions"] or []
        if a["name"] in WRITES[dom]
    ]
    calls = tool_calls(msgs, "assistant")
    w = [(n, a) for n, a, ok in calls if ok and n in WRITES[dom]]
    transferred = any(n == "transfer_to_human_agents" for n, _, _ in calls)
    last_u = last_text(msgs, "user")
    gn, an = Counter(a["name"] for a in gold), Counter(n for n, _ in w)
    if (
        gold
        and an != gn
        and all(an[k] <= gn[k] for k in an)
        and confirm_then_stop(msgs)
    ):
        return "user_premature_stop", ",".join(sorted((gn - an).keys()))
    if not w and gold:
        if transferred or "###TRANSFER###" in last_u:
            return "unwarranted_transfer", ""
        if not any(ok and n in AUTH for n, _, ok in calls):
            return "auth_dead_end", ""
        if "###OUT-OF-SCOPE###" in last_u:
            return "user_out_of_scope", ""
        if REFUSE.search(last_text(msgs, "assistant")):
            return "wrongful_refusal", ""
        sub = (
            "declined"
            if DECLINE.search(last_u)
            else "deferred"
            if DEFER.search(last_u)
            else "other"
        )
        return "ended_without_acting", sub
    if w and not gold:
        return "unwarranted_write", ",".join(sorted({n for n, _ in w}))
    G, A = (
        Counter(canon(a["name"], a["arguments"]) for a in gold),
        Counter(canon(n, a) for n, a in w),
    )
    if G == A:
        return "same_writes_db_differs", ""
    if gn == an:
        keys = set()
        for g in gold:
            same = [a for n, a in w if n == g["name"]]
            keys |= set(
                diff_keys(
                    min(same, key=lambda a: len(diff_keys(a, g["arguments"]))),
                    g["arguments"],
                )
            )
        return "wrong_arguments", ",".join(sorted(keys))
    if all(an[k] <= gn[k] for k in an):
        return "incomplete_multi_step", ",".join(sorted((gn - an).keys()))
    if all(gn[k] <= an[k] for k in gn):
        return "extra_write", ",".join(sorted((an - gn).keys()))
    return "wrong_action_type", f"{'+'.join(sorted(gn))}->{'+'.join(sorted(an))}"


def classify_telecom(s, task):
    ri, msgs = s["reward_info"], s["messages"]
    if s["termination_reason"] != "user_stop":
        return "step_cap", ""
    gold = task["evaluation_criteria"]["actions"] or []
    unfixable = any(a["name"] == "transfer_to_human_agents" for a in gold)
    calls = tool_calls(msgs, "assistant")
    user_transfer = "###TRANSFER###" in last_text(msgs, "user")
    transferred = (
        any(n == "transfer_to_human_agents" for n, _, _ in calls) or user_transfer
    )
    env_ok = all(c["met"] for c in ri.get("env_assertions") or [])
    if unfixable:  # gold = transfer only; failures never contain the transfer tool call
        if not env_ok:
            return "broke_state_before_transfer", ",".join(
                sorted({n for n, _, ok in calls if ok and not n.startswith("get_")})
            )
        return ("text_only_transfer", "") if user_transfer else ("never_escalated", "")
    misses = [
        c["action"]["name"]
        for c in ri.get("action_checks") or []
        if not c["action_match"]
    ]
    if (
        transferred
    ):  # escalated with gold steps still undone; label by the first missing family
        m = set(misses)
        fam = (
            "roaming"
            if m & {"toggle_roaming", "enable_roaming"}
            else "refuel"
            if "refuel_data" in m
            else "app_permission"
            if "grant_app_permission" in m
            else "other_step"
        )
        return "transfer_missed_" + fam, ",".join(sorted(m))
    # user said ###STOP### while an assertion still fails
    return "user_stop_unresolved", ",".join(sorted(set(misses))) or "all_steps_done"


def main():
    out = {}
    files = sorted(
        f
        for f in glob.glob(ROOT + "*_4trials.json")
        if re.search(r"_(retail|airline|telecom)_(default|base)_", f)
    )
    for f in files:
        dom = re.search(r"_(retail|airline|telecom)_", f).group(1)
        d = json.load(open(f))
        tasks = {t["id"]: t for t in d["tasks"]}
        sims = d["simulations"]
        cats, sub, ex, fx = (
            Counter(),
            defaultdict(Counter),
            defaultdict(list),
            Counter(),
        )
        for s in sims:
            if s["reward_info"]["reward"] == 1:
                continue
            t = tasks[s["task_id"]]
            c, x = (
                classify_telecom(s, t) if dom == "telecom" else classify_db(dom, s, t)
            )
            cats[c] += 1
            for k in filter(None, x.split(",")):
                sub[c][k] += 1
            ex[c].append((s["task_id"], s["trial"]))
            fx[c] += dom in FIXED and int(s["task_id"]) in FIXED[dom]
        name = os.path.basename(f).replace("_gpt-4.1-2025-04-14_4trials.json", "")
        nf = sum(cats.values())
        print(f"\n=== {name}: {len(sims)} sims, {nf} failed")
        for c, v in cats.most_common():
            fixed = f" fixed_tasks={fx[c]}" if dom in FIXED else ""
            print(
                f"  {c:30s} {v:4d} ({v / nf:.0%}){fixed}  sub={dict(sub[c].most_common(5))}  ex={ex[c][:3]}"
            )
        out[name] = {c: ex[c] for c in cats}
    if len(sys.argv) > 1:
        json.dump(out, open(sys.argv[1], "w"), indent=1)


if __name__ == "__main__":
    main()
