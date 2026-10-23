"""For each failed S1b episode: did the agent ask for an ID right before the user
invented one, and had the agent already found the user account (so it could look the
ID up)? Also prints how often each agent ever asks for an ID.

python3 s1b_agent_asked.py
"""

import collections
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from invented_ids import D, invented

ASK = re.compile(
    r"(order|reservation)\s*(id|number|#)|confirmation (code|number)", re.I
)
LOOKUP = {"get_user_details", "find_user_id_by_email", "find_user_id_by_name_zip"}
files = [
    f
    for f in glob.glob(str(D / "*_default_*")) + glob.glob(str(D / "*_base_*"))
    if re.search(r"_(retail|airline|telecom)_(default|base)_", f)
]
asks = collections.Counter()
eps = collections.Counter()
for f in sorted(files):
    model = Path(f).name.split("_")[0]
    d = json.load(open(f))
    tasks = {t["id"]: t for t in d["tasks"]}
    for s in d["simulations"]:
        msgs = s["messages"]
        eps[model] += 1
        if any(
            m["role"] == "assistant" and ASK.search(m.get("content") or "")
            for m in msgs
        ):
            asks[model] += 1
        if s["reward_info"]["reward"] >= 1 or not invented(s, tasks[s["task_id"]]):
            continue
        # first user message with an invented id, and the agent turn before it
        seen = json.dumps(tasks[s["task_id"]]["user_scenario"])
        for i, m in enumerate(msgs):
            if m["role"] == "user" and invented(
                {"messages": msgs[: i + 1]}, tasks[s["task_id"]]
            ):
                break
        prev = next(
            (
                x
                for x in reversed(msgs[:i])
                if x["role"] == "assistant" and x.get("content")
            ),
            {},
        )
        tools_before = {
            tc["name"] for x in msgs[:i] for tc in (x.get("tool_calls") or [])
        }
        print(
            f"{model:28} {s['task_id'][:20]:20}/{s['trial']}  agent_asked_id={bool(ASK.search(prev.get('content') or ''))}"
            f"  user_lookup_done={bool(tools_before & LOOKUP)}"
        )
        print("    AGENT:", (prev.get("content") or "")[:160].replace("\n", " "))
        print("    USER: ", (m.get("content") or "")[:160].replace("\n", " "))
print("\nepisodes where agent ever asks for an order/reservation id, per agent:")
for k in eps:
    print(f"  {k:28} {asks[k]}/{eps[k]} = {asks[k] / eps[k]:.0%}")
