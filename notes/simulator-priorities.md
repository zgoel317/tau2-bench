# Which simulator limitations matter most

**Scope.** This assignment is about the **user simulator**: the LLM that plays the customer. The simulator's problems fall into two groups:

- **S1, what the simulator says:** it doesn't mention decisive facts, invents facts, or asks for things its own instructions contradict.
- **S2, when the simulator ends the conversation:** it ends before its requests have been carried out.

I also sorted all 131 open GitHub issues; the ones that aren't S1/S2 are in [Other](#other-every-open-issue-not-in-s1-or-s2).

## Counting rule: only failures the simulator started

**A failure counts toward S1 or S2 only if the simulator made the first mistake. If the agent made the first mistake, the failure is excluded, even if the simulator then went along with it.**

Agent-started failures I excluded include:
- the agent proposes the wrong item and the simulator says yes;
- the agent wrongly says an item isn't in the order, so the simulator drops it;
- the agent opens the wrong order, or says it made a change it never made;
- the agent demands an order ID it could have looked up, and the simulator leaves to find it.

[What was excluded](#what-the-counting-rule-excluded) lists every behaviour and episode removed this way.

**Correction to an earlier version of this doc.** The R2 sample was first labelled from only the last three user messages, which gave 15 of 20 as the simulator's fault. Re-reading the full conversations showed that in most of them the agent made the first mistake. All labels below come from full conversations.

## How to read the labels

There are two kinds of labels:

- **Failure modes** (T1, R8, …) are *outcome* buckets from [failure-modes.md](failure-modes.md). A script sorts every failed episode into exactly one, based on what went wrong.
- **Simulator behaviours** (S1a, S2b, …) are *causes*. Each counted episode is assigned to the behaviour behind the simulator's **first** mistake, so no episode is counted twice within the hand-labelled behaviours.

| Code | Domain | Failure mode (outcome) | Failed episodes |
|---|---|---|---|
| **T1** | telecom | The user is abroad and needs roaming on. Roaming never got fixed, and the agent transferred the user. | 738 |
| **T5** | telecom | The task requires a transfer to a human. The simulator ended the call as "transferred", but the agent never made the transfer tool call. | 42 |
| **R1** | retail | The agent made the right kind of change with a wrong argument (wrong item variant, order or payment method). | 176 |
| **R2** | retail | Only some of the requested changes were made. | 94 |
| **R6** | retail | No change was made. The user ended the call to look something up, or just left. | 25 |
| **R8** | retail | The user said "yes" and ended the call in the same message, so the agent's pending change never happened. | 16 |
| **A5** | airline | Only some of the requested changes were made. | 34 |
| **A10** | airline | The airline equivalent of R8 (2 cases) plus one unrelated case. | 3 |

**Data:** the paper's June 2025 runs (`data/tau2/results/final/`): 4 agent models, `gpt-4.1` as the simulator, 4,448 episodes, **1,920 failed**. I got counts three ways:

- exact by script: S1a, S1b, S2a, S2b;
- exact by reading every episode: all 25 R6 failures;
- estimated from a hand-labelled random sample of 20, for R1 and R2, which are too large to read in full.

See [How the estimates work](#how-the-estimates-work), [How these numbers were produced](#how-these-numbers-were-produced), and the [Appendix](#appendix-hand-labels).

## The math: failures per behaviour

| | Behaviour | Where it comes from | Failed episodes |
|---|---|---|---|
| **S1a** | Doesn't reliably mention a decisive fact | Exact: telecom abroad tasks where the user never says it is abroad | **697** |
| **S1b** | Invents IDs | Exact: a user message gives an ID that's in neither the scenario nor anything shown earlier | **17** |
| **S1c** | Asks for the wrong thing on its own | R1: 1 of 20 sampled → ≈6 (95% CI 1–30). R2: 2 of 20 sampled → ≈9 (CI 3–28). R6: 1 (read in full). | **≈16** (floor 4) |
| | **S1 without S1a** | 17 + 16 | **≈33** (floor 21) |
| | **S1 with S1a** | 697 + 33 | **≈730** |
| **S2a** | Says "yes" and hangs up in the same turn | Exact: classifier bucket `user_premature_stop` | **18** |
| **S2b** | Treats an offer to transfer as the transfer | Exact: classifier bucket `text_only_transfer` | **42** ⚠ see note |
| **S2c** | Ends the call with part of its request never carried out | R2: 4 of 20 sampled → ≈19 (CI 8–39). R6: 5 (read in full). | **≈24** (floor 9) |
| | **S2 total** | 18 + 42 + 24 | **≈84** (floor 69) |

**Overlaps:** S1b overlaps S2a in 2 episodes (an invented ID, then yes-and-hang-up). Both mistakes are the simulator's, so these 2 are counted in both groups. The hand-labelled behaviours (S1c, S2c) assign each episode to one behaviour only.

**Bottom line:**
- With S1a, S1 dominates (~730 vs ~84).
- Without S1a, S2 is about 2.5× S1 (~84 vs ~33).

**⚠ Judgment calls under the counting rule:**
- **S2b.** The agent *asks* "would you like me to transfer you?" before calling the transfer tool. The telecom policy has no rule to get confirmation before a transfer (retail and airline require confirmation only for database writes). It also doesn't forbid asking. It only says: *"To transfer, first make a tool call to transfer_to_human_agents, and then send the message…"*.

  Asking is therefore not clearly a mistake, and S2b stays counted. If it were counted as the agent's first mistake, **S2 would fall to ~42, slightly above S1 (~33)**.
- **S1a.** The agent also never asked where the user was. It stays counted because the simulator's mentioning the fact at random is the source of the noise, but it could be argued either way.

## How the estimates work

**Why some counts need hand-labelling.** A script can find the candidate episodes, but it can't tell who made the first mistake. That takes reading the conversation. R6 is small (25), so every episode was read. R1 (176) and R2 (94) are large, so a fixed-seed random sample of 20 from each was read in full and the share was scaled up.

**Steps for each sample:**

1. Pick the candidate pool.
   - R1: the 127 episodes where the agent's last message before the wrong write shows the wrong value and the user replied yes. If the simulator asked for the wrong thing, it would show up here.
   - R2: all 94 episodes.
2. Draw 20 at random. The seed is fixed, so the same 20 come out every time.
3. Read each conversation in full and label it by the first mistake:
   - **S1c:** the simulator, with no wrong input from the agent, asked for the wrong thing.
   - **S2c:** the simulator ended the call with items undone, without the agent having caused it.
   - **Agent:** the agent made the first mistake.
   - **Unclear:** the conversation doesn't show who made the first mistake.
4. Scale up: share in the sample × pool size.
5. Uncertainty: a 95% Wilson interval on the share, times the pool size. The Wilson interval stays within 0–100% and is reliable at small samples.

| Sample | Labels | Scaled estimate | 95% CI |
|---|---|---|---|
| R1 (20 of 127) | S1c 1 · Agent 19 | S1c: 5% × 127 ≈ **6** | 0.9%–23.6% → 1–30 |
| R2 (20 of 94) | S2c 4 · S1c 2 · Agent 14 | S2c: 20% × 94 ≈ **19**; S1c: 10% × 94 ≈ **9** | S2c 8.1%–41.6% → 8–39; S1c 3–28 |
| R6 (all 25) | S2c 5 · S1b 2 · S1c 1 · Unclear 2 · Agent 15 | Exact: S2c **5**, S1c **1** (the S1b 2 are already in the script count) | none needed |
| A5 (12 of 34) | S1/S2 0 · Unclear 5 · Agent or task bug 7 | 0 | — |

The floor is the count confirmed by reading alone (S1c 4, S2c 9). It treats every unread episode as not the simulator's fault, so it's a lower bound.

**Caveats:**
- Samples of 20 give wide intervals.
- Episodes cluster by task (tasks 71 and 112 account for 8 of the 20 R2 episodes), so the real uncertainty is wider still.
- Labels are my judgment from the full conversation.
- Reading all 127 + 94 candidates would replace the estimates with exact counts.

## S1. What the simulator says

| | Behaviour | What goes wrong | Seen in | Real example (re-read in the result files) | Count |
|---|---|---|---|---|---|
| **S1a** | **Doesn't reliably mention a decisive fact** | The simulator knows a fact that decides the task ("you are abroad in France"). It mentions it unprompted only some of the time, even after an identical agent greeting. If it never comes up, the agent rarely asks, and the task fails. When the agent *does* ask directly, the simulator answers (36 of 38 times). | T1 | `claude telecom [mobile_data_issue]bad_network_preference\|user_abroad_roaming_enabled_off[PERSONA:Hard]`, same agent and same task. **Trial 0:** the first message says *"I'm currently in France"*, and it passes. **Trial 3:** France is never mentioned, and it fails. | **697.** Of 1,024 abroad episodes, the fact never came up in 71% (pass rate 0.04) vs 26% volunteered (0.64). |
| **S1b** | **Invents information** | Asked for something it doesn't have (usually an order ID), the simulator makes one up instead of saying it doesn't know. | Spread over 7 buckets: R6 4, R2 4, unwarranted transfer 3, R8 2, R1 2, other 2 | `gpt-4.1-mini retail 94/2`: *"here it is: 8745632"*. No such order exists. | **17** (exact). o4-mini 11, gpt-4.1-mini 6. Often the agent had asked for an ID it could have looked up, but making one up is the simulator's own mistake. |
| | ↳ reported, not in the paper data | Inventions that aren't IDs: a passenger count (#172), a date of birth to fit the persona (#492), a new goal once the real one is impossible (#494) | Issues | #172: asked how many passengers, the simulator says two; the gold has one. Verified that task 35's scenario never gives a count. | Not counted |
| **S1c** | **Asks for the wrong thing on its own** | The agent has said nothing wrong, but the simulator asks for the wrong thing, and the agent does exactly what it's told. This happens in three ways: **(a) guesses** an order number it can't know instead of describing the order; **(b) misreads its own instructions**, e.g. which order to cancel; **(c) skips a scripted step**, e.g. a planned change of mind at confirmation. | R1, R2, R6 (and issue #496) | **(a)** `claude retail 71/1`: the agent lists order numbers only; the simulator, which was never given them, picks *"order #W7032009"*, the wrong one. **(b)** `gpt-4.1 retail 59/2`: its instructions say #W2702727 gets a new address and the *other* order may be cancelled, but its first message calls #W2702727 the delayed order and then cancels it. **(c)** `claude retail 72/1`: told to switch to PayPal and modify only the backpack when asked to confirm, it says *"use the gift card… proceed with the changes as you listed"*. | **≈16** (floor 4) |

## S2. When the simulator ends the conversation

| | Behaviour | What goes wrong | Seen in | Real example (re-read in the result files) | Count |
|---|---|---|---|---|---|
| **S2a** | **Says "yes" and hangs up in the same turn** | Asked to confirm, the simulator confirms and ends the call in one message. The agent never gets a turn to make the change. | R8, A10 | `gpt-4.1-mini retail 102/0`: after three earlier yeses, the agent asks again: *"Please confirm with a 'yes'"*. The simulator replies *"Yes. Go ahead. Thanks.###STOP###"*, and nothing is changed. | **18.** In 10 of them the agent had asked again after a yes. Asking again isn't a mistake; hanging up is. |
| **S2b** | **Treats an offer to transfer as the transfer** ⚠ | When the agent *asks* whether the user wants a human, the simulator says yes and ends the call as transferred. The agent never makes the tool call the grader checks. | T5 | `gpt-4.1 telecom [service_issue]airplane_mode_on\|break_apn_settings\|lock_sim_card_pin[PERSONA:None]/0`: *"Would you like me to transfer you…"* → *"Yes, please transfer me…###TRANSFER###"*. | **42.** gpt-4.1 25, gpt-4.1-mini 11, claude 6, o4-mini 0. ⚠ Kept, because the policy doesn't forbid asking first. It would be excluded if asking counted as the agent's first mistake. |
| **S2c** | **Ends the call with part of its request never carried out** | The simulator is given a to-do list, and the call should only end once everything on it is done. Here it hangs up with items still undone, without the agent having caused it. This happens in three ways: **(1) never asks** for some items and says "that's all"; **(2) shrinks** an item ("fix all my orders" becomes "fix this order"); **(4) leaves to come back later** when nothing stopped it from finishing. (A third way, **(3) giving up after the agent wrongly says something can't be done**, is excluded because the agent started it.) | R2, R6 (and issue #182) | **(1)** `claude retail 104/3`: the agent lists bookshelves and jigsaws in two orders; the simulator returns the first order's, never asks about the second, and says *"that's everything!"*. **(4)** `claude retail 69/2`: told to ask for a cancellation if a return isn't possible, it says *"I'll reach out again once the status updates"* and hangs up. | **≈24** (floor 9) |

**Why S2 is still open for text runs.** The voice prompts tell the simulator that agreeing isn't the same as done, and to check that *all* items are addressed before ending ([guidelines.py:77-78](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/guidelines.py#L77)). The text prompts have neither. They only say *"If the instruction goal is satisified, generate the '###STOP###' token"* ([:220](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/guidelines.py#L220), [:255](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/guidelines.py#L255)). For transfers, they say to emit the token only *"after the agent has clearly indicated…"* ([:256](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/guidelines.py#L256)), which lets an offer count.

## What the counting rule excluded

| Excluded | Why | Size |
|---|---|---|
| **Accepting the agent's wrong proposal** (the earlier S1c, ≈51) | The agent proposed the wrong item or payment; the simulator only said yes. | 19 of the 20 sampled R1 episodes |
| **S2c way (3): dropping a request after the agent's false claim** | The agent said something untrue first ("the e-reader isn't in this order", "there's no NYC address on file"). | Part of the 14 agent-started R2 episodes |
| **Other agent-started R2 failures** | The agent opened the wrong order, said it made a change it never made, used the wrong tool, transferred, or missed an explicit "everywhere". | 14 of the 20 sampled R2 episodes |
| **Agent-started R6 failures** | The agent demanded an order ID it could look up (8), or used the wrong order or tool, or made a false claim (7). | 15 of 25 |
| **A5** (airline, only some changes made) | No clearly simulator-started case in 12 sampled; the rest were agent errors or tasks later rewritten in v1.0.0. | 34 |
| **A8** (airline, user declined) | Mostly task 14, whose constraint was impossible (fixed in v1.0.0). A task bug. | 14 |

## Why S1 and S2 rank highest, and which first

Every other open issue changes something other than the simulator's behaviour (see Other).

- With S1a, S1 is about 9× S2 (~730 vs ~84). S1a is noise the agent can't control: 234 of the 264 volunteered disclosures came in the simulator's *first* message.
- Without S1a, S2 is larger (~84 vs ~33), mostly because of S2b.
- If S2b were also treated as agent-started, S2 would still be slightly larger (~42 vs ~33).

## Other: every open issue not in S1 or S2

Each of the 131 open issues (as of 2026-10-23) is in exactly one bucket. **In S1:** #172, #492, #494, #496. **In S2:** #182.

| Bucket | Issues |
|---|---|
| **Simulator inputs and infrastructure** (not simulator behaviour) | #517 OUT-OF-SCOPE recorded as `USER_STOP` (bookkeeping) · #470 text simulator crashes when told to speak and call a tool in one turn · #154 user tool state shared across concurrent runs · #576 instructions name a non-existent tool · #337 scenario gives a user ID instead of a name · #139 user tool calls mishandled in message conversion · #540 run-to-run noise (includes simulator sampling) · #463 banking simulator non-uniform (banking is out of scope) |
| Dropped | #57: the reporter misread the episode index. The real task is abroad, and the simulator never says "abroad" in at-home episodes. |
| Task data and gold (retail/airline/telecom) | #664, #662, #661, #495, #321, #320, #319, #318, #317, #316, #327, #326, #237, #104, #96. **Still open though already fixed in the data:** #156, #89 (partly), #84 (partly), #47 |
| Evaluator and scoring | #672, #658, #646, #635, #608, #568, #557, #556, #555, #554, #553, #514, #502, #499, #497, #493, #459, #436, #384, #325, #298, #224, #211, #159, #82, #81, #15 |
| Agent policy text | #472 |
| Environment tools | #660, #659, #541, #153 |
| banking_knowledge domain | #663, #633, #628, #599, #592, #587, #586, #574, #565, #545, #543, #530, #485, #477, #439, #438, #432, #372 |
| Runtime, providers, install | #654, #560, #559, #558, #552, #487, #486, #383, #241, #234, #169, #166, #115, #92, #76, #49, #44, #42, #12 |
| Reproducibility questions, licence | #647, #612, #106, #74, #71, #51, #11 |
| Proposals, features, docs, questions | #579, #490, #435, #206, #167, #150, #129, #127, #123, #112, #111, #110, #109, #108, #107, #100, #75, #69, #68, #63, #32, #16 |

## How these numbers were produced

All scripts are in [`scripts/`](scripts/) and read the paper's result files in `data/tau2/results/final/`. Run them from `notes/scripts/` with `python3 <script>`.

**Pipeline:**

1. [`classify.py`](scripts/classify.py) sorts every failed episode into exactly one failure-mode bucket (R1, R2, T1, …). It compares the agent's tool calls with the task's gold actions, and checks how the conversation ended.
2. [`stats.py`](scripts/stats.py) aggregates those buckets into the per-domain tables in [failure-modes.md](failure-modes.md). It also computes targeted counts, such as how often agents asked about location, and the ablation pass rates.
3. [`disclosure.py`](scripts/disclosure.py) puts each telecom abroad episode into one of four groups: the user volunteered being abroad, was asked and answered, was asked and didn't answer, or it never came up. It reports pass rates per group (S1a context).
4. [`invented_ids.py`](scripts/invented_ids.py) flags user messages containing an ID that appears neither in the task's scenario nor earlier in the conversation the simulator could see (S1b).
5. [`sim_attribution.py`](scripts/sim_attribution.py) goes over all 1,920 failed episodes. It tags each with its bucket from step 1 and with simulator flags, then prints per-flag counts and overlaps. This gives the exact S1a, S1b, S2a and S2b counts and the 127-episode R1 candidate pool.
6. [`sample_for_labels.py`](scripts/sample_for_labels.py) prints the episodes that were hand-labelled: the fixed-seed samples from R1 and R2 (`--full` shows whole conversations), all 25 R6 episodes, and the A5 sample.
7. [`dump.py`](scripts/dump.py) prints a single episode compactly. I used it to re-read every quoted example.

**From scripts to the totals:**
- Exact counts come from step 5, or from reading every R6 episode in step 6.
- Estimates = the share labelled in the step-6 samples × the candidate pool, with the Wilson interval from the same share.

## Appendix: hand labels

Every label is by **who made the first mistake**, read from the full conversation.

**R1 sample** (20 of the 127 candidates; seed 1):
- **S1c (1):** claude 72/1: kept the gift card and the lamp change, although scripted to switch to PayPal and only modify the backpack.
- **Agent (19):**
  - The agent proposed the wrong item: claude 20/3, o4-mini 20/1, claude 80/2, gpt-4.1-mini 1/2, gpt-4.1-mini 1/1, gpt-4.1 0/0, o4-mini 93/1, gpt-4.1 56/1, claude 49/2, o4-mini 110/0, gpt-4.1-mini 79/1, claude 79/0, o4-mini 79/2.
  - The agent stated, with no data behind it, that #W2702727 was the older order, so the simulator cancelled it: gpt-4.1 59/3.
  - The agent charged the credit card after telling the user its gift card ($85.00) could cover the difference ($42.55): gpt-4.1-mini 58/2.
  - The agent offered only 500-piece puzzles when the user asked for "500 fewer pieces" than its 1,500-piece one: gpt-4.1-mini 107/3.
  - Task or scoring artefacts: o4-mini 100/1, o4-mini 15/1, gpt-4.1-mini 38/1.

**R2 sample** (20 of 94; seed 2):
- **S2c (4):**
  - claude 104/3: never came back to the second order's returns.
  - gpt-4.1 41/2, gpt-4.1-mini 42/1: asked to fix "my order", only one of two.
  - o4-mini 81/2: said all its items were in one order, then stopped after cancelling it.
- **S1c (2):**
  - claude 71/1: guessed the wrong order number from the agent's bare list (way a).
  - gpt-4.1 59/2: its first message misread which order to keep, then it cancelled that order (way b).
- **Agent (14):**
  - The agent said the e-reader wasn't in the order without checking the others: claude 92/2, 92/3.
  - The agent modified the pending order instead of exchanging the delivered hose: gpt-4.1-mini 29/2.
  - The agent said it updated the address but never called the tool: o4-mini 112/2.
  - The agent opened the wrong order: gpt-4.1-mini 71/0, o4-mini 71/0, 71/1, 71/3.
  - The agent checked one order and said the laptop or NYC address didn't exist: gpt-4.1 112/3, gpt-4.1-mini 112/3, 112/1, o4-mini 112/3.
  - The agent transferred: o4-mini 31/2.
  - The agent missed an explicit "everywhere": gpt-4.1-mini 41/3.

**R6** (all 25):
- **S2c (5):**
  - claude 66/0: deferred instead of its scripted fallback, "cancel the entire order".
  - claude 69/2, o4-mini 69/3: deferred instead of its scripted fallback, "see if it can be cancelled".
  - gpt-4.1 43/3: said it would get the daughter's address after the agent had just shown it.
  - gpt-4.1-mini 45/2: left to buy a gift card.
- **S1b (2):** o4-mini 20/0, o4-mini 33/2: invented an order ID, then left. These are already in the script count.
- **S1c (1):** o4-mini 108/3: guessed two order numbers from the agent's bare list, both wrong (way a).
- **Unclear (2):** gpt-4.1-mini 20/2, o4-mini 45/0.
- **Agent (15):**
  - The agent demanded an order ID it could look up: gpt-4.1-mini 52/1, 83/1, 64/2, 64/3, 7/3, 94/2, 94/3, 93/3.
  - The agent used the wrong order or tool, or made a false claim: gpt-4.1 20/1, gpt-4.1-mini 33/0, 63/0, 69/3, 85/3, o4-mini 63/0, 20/3.

**A5 sample** (12 of 34; seed 2): **S1/S2 0**, **unclear 5** (tasks 23 and 44, both later rewritten), **agent or task bug 7**.

**Caveat:** every count is from the paper-era `gpt-4.1` simulator and text guidelines. Re-run on current main before quoting rates as current.
