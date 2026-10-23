"""Every number in ../failure-modes.md that classify.py does not print.

python3 stats.py
"""

import glob
import json
import os
import re
from collections import Counter, defaultdict

from classify import (
    ASK,
    FIXED,
    ROOT,
    WRITES,
    YES,
    canon,
    classify_db,
    classify_telecom,
    last_text,
    tool_calls,
)

ASK_LOC = re.compile(
    r"abroad|travel|outside (the|your)|international|which country|where are you|your (current )?location|overseas",
    re.I,
)
SAYS_ABROAD = re.compile(
    r"abroad|france|overseas|travel|another country|outside the (us|country)", re.I
)
OFFER_REFUEL = re.compile(
    r"refuel|top.?up|add(ing)? (more |extra |additional )?data|additional data|data (add-on|boost)",
    re.I,
)
TEL_WRITES = {
    "send_payment_request",
    "resume_line",
    "enable_roaming",
    "disable_roaming",
    "refuel_data",
    "suspend_line",
}
USER_TOOLS = {
    "can_send_mms",
    "check_network_status",
    "check_status_bar",
    "check_apn_settings",
    "run_speed_test",
    "reset_apn_settings",
    "set_network_mode_preference",
    "reseat_sim_card",
    "toggle_data",
    "reboot_device",
    "check_network_mode_preference",
    "toggle_data_saver_mode",
}


def files():
    for f in sorted(glob.glob(ROOT + "*_4trials.json")):
        m = re.search(
            r"^(.*?)-20\d\d-?\d\d-?\d\d_(retail|airline|telecom)_(default|base)_",
            os.path.basename(f),
        )
        if m:
            yield m.group(1), m.group(2), json.load(open(f))


def pct(a, b):
    return f"{a}/{b} ({a / b:.0%})" if b else f"{a}/0"


def main():
    modes = defaultdict(lambda: defaultdict(Counter))  # dom -> mode -> model -> n
    sizes = Counter()
    fix = Counter()
    rx = Counter()  # retail/airline extras
    tel = Counter()
    slices_n, slices_p = Counter(), Counter()
    spur = Counter()
    fracs = []  # share of gold steps matched, per transfer_missed_* episode
    subs = defaultdict(
        Counter
    )  # (dom, mode) -> sub-label counts (arg keys, tool names, ...)
    for model, dom, d in files():
        tasks = {t["id"]: t for t in d["tasks"]}
        for s in d["simulations"]:
            t, r, msgs = tasks[s["task_id"]], s["reward_info"]["reward"], s["messages"]
            sizes[dom, "n"] += 1
            sizes[dom, model, "fail"] += r < 1
            calls = tool_calls(msgs, "assistant")
            if dom != "telecom":
                k = "fixed" if int(s["task_id"]) in FIXED[dom] else "other"
                fix[dom, k, "n"] += 1
                fix[dom, k, "fail"] += r < 1
                if r == 1:
                    continue
                c, sub = classify_db(dom, s, t)
                modes[dom][c][model] += 1
                for lab in filter(None, sub.split(",")):
                    subs[dom, c][lab] += 1
                subs[dom, c]["task " + s["task_id"]] += 1
                if (
                    c == "user_premature_stop"
                ):  # did the user already say yes to an earlier confirmation, with no write since?
                    tt = [
                        x
                        for x in msgs
                        if x["role"] in ("user", "assistant") and x.get("content")
                    ]
                    i = msgs.index(tt[-3])
                    rx[dom, "user_premature_stop", "agent_reasked_after_yes"] += bool(
                        tt[-3]["role"] == "user"
                        and YES.search(tt[-3]["content"])
                        and ASK.search(tt[-4]["content"])
                        and not any(
                            n in WRITES[dom]
                            for x in msgs[i:]
                            for n in [tc["name"] for tc in x.get("tool_calls") or []]
                        )
                    )
                modes[dom][c]["on_fixed_tasks"] += k == "fixed"
                gold = [
                    a
                    for a in t["evaluation_criteria"]["actions"] or []
                    if a["name"] in WRITES[dom]
                ]
                w = {canon(n, a) for n, a, ok in calls if ok and n in WRITES[dom]}
                if c == "extra_write":
                    rx[dom, "extra_write"] += 1
                    rx[dom, "extra_write_gold_exact"] += all(
                        canon(a["name"], a["arguments"]) in w for a in gold
                    )
                if c == "unwarranted_transfer":
                    u = 0
                    for m in msgs:
                        if m["role"] == "user" and m.get("content"):
                            u += 1
                        if m["role"] == "assistant" and any(
                            tc["name"] == "transfer_to_human_agents"
                            for tc in m.get("tool_calls") or []
                        ):
                            rx[dom, model, "transfer_by_user_turn2"] += u <= 2
                            break
                continue
            # ---- telecom
            m = re.match(r"\[(\w+)\](.*)\[PERSONA:(\w+)\]", s["task_id"])
            for key in [
                ("intent", m.group(1)),
                ("persona", m.group(3)),
                ("n_issues", len(m.group(2).split("|"))),
                ("abroad", "abroad" in s["task_id"]),
                ("model x intent", model, m.group(1)),
            ]:
                slices_n[key] += 1
                slices_p[key] += r
            gold = {a["name"] for a in t["evaluation_criteria"]["actions"] or []}
            sp = {n for n, a, ok in calls if ok and n in TEL_WRITES and n not in gold}
            for n in sp:
                spur[model, n] += 1
            spur[model, "agent_called_user_tool"] += any(
                n in USER_TOOLS for n, _, _ in calls
            )
            ac = s["reward_info"].get("action_checks") or []
            missed = {x["action"]["name"] for x in ac if not x["action_match"]}
            text = " ".join(
                x["content"] or "" for x in msgs if x["role"] == "assistant"
            )
            if "abroad" in s["task_id"]:
                ask = next(
                    (
                        i
                        for i, x in enumerate(msgs)
                        if x["role"] == "assistant"
                        and x.get("content")
                        and ASK_LOC.search(x["content"])
                    ),
                    None,
                )
                disc = next(
                    (
                        i
                        for i, x in enumerate(msgs)
                        if x["role"] == "user"
                        and x.get("content")
                        and SAYS_ABROAD.search(x["content"])
                    ),
                    None,
                )
                g = (
                    "pass"
                    if r == 1
                    else "fail_roaming_missed"
                    if missed & {"toggle_roaming", "enable_roaming"}
                    else "fail_other"
                )
                tel["abroad", g, "n"] += 1
                tel["abroad", g, "agent_mentions_roaming"] += (
                    "roam" in text.lower()
                    or "enable_roaming" in {n for n, _, _ in calls}
                )
                tel["abroad", g, "agent_asks_location"] += ask is not None
                tel["abroad", g, "abroad_surfaces"] += disc is not None
                tel["abroad", g, "user_volunteers_first"] += disc is not None and (
                    ask is None or disc < ask
                )
                tel["abroad_by_model", model, "n"] += 1
                tel["abroad_by_model", model, "pass"] += r
                tel["abroad_by_model", model, "agent_asks_location"] += ask is not None
            if r == 1:
                continue
            c, sub = classify_telecom(s, t)
            modes[dom][c][model] += 1
            for lab in filter(None, sub.split(",")):
                subs[dom, c][lab] += 1
            if c.startswith("transfer_missed"):
                tel["transfer_missed_*", "text_only"] += "###TRANSFER###" in last_text(
                    msgs, "user"
                ) and not any(n == "transfer_to_human_agents" for n, _, _ in calls)
                fracs.append(sum(x["action_match"] for x in ac) / len(ac))
            if "refuel_data" in missed:
                tel["missed refuel_data", "n"] += 1
                tel["missed refuel_data", "agent_called_get_data_usage"] += any(
                    n == "get_data_usage" for n, _, _ in calls
                )
                tel["missed refuel_data", "agent_offered_refuel"] += bool(
                    OFFER_REFUEL.search(text)
                )
                tel["missed refuel_data", "agent_refueled_wrong_amount_or_line"] += any(
                    n == "refuel_data" for n, _, ok in calls if ok
                )
            if "grant_app_permission" in missed:
                ucalls = {n for n, _, _ in tool_calls(msgs, "user")}
                tel["missed grant_app_permission", "n"] += 1
                tel["missed grant_app_permission", "agent_mentions_permission"] += (
                    "permission" in text.lower()
                )
                tel[
                    "missed grant_app_permission", "user_ran_check_app_permissions"
                ] += "check_app_permissions" in ucalls

    models = ["claude-3-7-sonnet", "gpt-4.1", "gpt-4.1-mini", "o4-mini"]
    print("== episodes / failures")
    for dom in ["retail", "airline", "telecom"]:
        print(
            f"  {dom}: {sizes[dom, 'n']} episodes, failed "
            + ", ".join(f"{m}={sizes[dom, m, 'fail']}" for m in models)
            + f", total={sum(sizes[dom, m, 'fail'] for m in models)}"
        )
    print("\n== mode x model (failed episodes)")
    for dom, mm in modes.items():
        tot = sum(sum(v[m] for m in models) for v in mm.values())
        print(f"  [{dom}] " + " | ".join(models))
        for c, v in sorted(mm.items(), key=lambda x: -sum(x[1][m] for m in models)):
            n = sum(v[m] for m in models)
            fx = f"  on_fixed_tasks={v['on_fixed_tasks']}" if dom != "telecom" else ""
            print(
                f"    {c:28s} "
                + " ".join(f"{v[m]:4d}" for m in models)
                + f"  total={n} ({n / tot:.0%}){fx}"
            )
    print("\n== sub-labels per mode (all models; an episode can carry several)")
    for (dom, c), v in sorted(subs.items()):
        print(
            f"  {dom} {c}: {dict(Counter({k: n for k, n in v.items() if not k.startswith('task ')}).most_common(10))}"
        )
        if dom != "telecom":
            print(
                f"      hot tasks: {[(k[5:], n) for k, n in v.most_common() if k.startswith('task ')][:6]}"
            )
    print("\n== task-spec overlay (tasks changed in v1.0.0)")
    for dom in ["retail", "airline"]:
        nf, of = fix[dom, "fixed", "fail"], fix[dom, "other", "fail"]
        print(
            f"  {dom}: {len(FIXED[dom])} fixed tasks; share of failures {pct(nf, nf + of)}; pass^1 fixed "
            f"{1 - nf / fix[dom, 'fixed', 'n']:.2f} vs other {1 - of / fix[dom, 'other', 'n']:.2f}"
        )
    print("\n== retail/airline extras")
    for k, v in sorted(rx.items()):
        print(f"  {k}: {v}")
    print("\n== telecom")
    for k, v in sorted(tel.items(), key=str):
        print(f"  {k}: {v:.0f}" if isinstance(v, float) else f"  {k}: {v}")
    print(
        f"  gold steps matched in {len(fracs)} transfer_missed_* episodes: mean {sum(fracs) / len(fracs):.2f}, "
        f"median {sorted(fracs)[len(fracs) // 2]:.2f}"
    )
    print("  pass^1 by slice:")
    for k in sorted(slices_n, key=str):
        print(f"    {k}: n={slices_n[k]} pass={slices_p[k] / slices_n[k]:.2f}")
    print(
        "  unrequested agent writes (episodes, successful call, tool not in gold) and agent calls to user-device tools:"
    )
    for k, v in sorted(spur.items()):
        print(f"    {k}: {v}")

    print(
        "\n== telecom ablations (paper Fig. 4 modes): pass^1 overall / on 'abroad' tasks"
    )
    for f in sorted(glob.glob(ROOT + "*_telecom_*_4trials.json")):
        m = re.search(
            r"^(gpt-4.1|o4-mini)-20\d\d-\d\d-\d\d_telecom_([\w-]+)_gpt",
            os.path.basename(f),
        )
        if not m:
            continue
        sims = json.load(open(f))["simulations"]
        ab = [x["reward_info"]["reward"] for x in sims if "abroad" in x["task_id"]]
        print(
            f"  {m.group(1):8s} {m.group(2):10s} {sum(x['reward_info']['reward'] for x in sims) / len(sims):.2f} / {sum(ab) / len(ab):.2f}"
        )


if __name__ == "__main__":
    main()
