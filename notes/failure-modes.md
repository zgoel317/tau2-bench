# Failure modes (τ²-bench)

This note sorts the failed episodes from τ²-bench's own paper runs into failure modes: first the types the paper names ([arXiv 2506.07982](https://arxiv.org/abs/2506.07982)), then retail, airline and telecom, then the modes all three share.

## Scope and method

**Data.** The files are `tau2-bench/data/tau2/results/final/*_4trials.json`, the paper's June 2025 runs. I use only default mode: `*_{retail,airline,telecom}_default_*`, plus gpt-4.1-mini's `*_base_*` files, which are its default mode. That gives 4 agents × 3 domains × 4 trials. Every run uses a `gpt-4.1` user simulator. Overall there are 4,448 episodes, of which 1,920 failed (reward < 1).

| Domain | Tasks | Episodes | Failed | claude-3.7 | gpt-4.1 | gpt-4.1-mini | o4-mini |
|---|---|---|---|---|---|---|---|
| retail | 114 | 1,824 | 500 | 97 | 118 | 155 | 130 |
| airline | 50 | 800 | 369 | 100 | 88 | 99 | 82 |
| telecom | 114 | 1,824 | 1,051 | 231 | 300 | 256 | 264 |

**What is scored.**
- Retail and airline: reward = DB hash match × `communicate_info` substring check.
- Telecom: reward = env assertions for the 94 fixable tasks. For the 20 unfixable tasks it is env assertions × an ACTION check that `transfer_to_human_agents` was called.

Every episode in these files ends with `user_stop`, except 36 telecom episodes that hit the 200-step cap.

**How failures are classified.** [`scripts/classify.py`](scripts/classify.py) puts each failure in exactly one bucket.

1. Retail and airline. The script compares the agent's *successful* write calls with the gold write actions. It ignores read-only calls, as the DB check does. It checks the rules in this order:
   - `step_cap` (never fires in these two domains);
   - `info_not_conveyed`: the DB is right but the communicate check failed;
   - `user_premature_stop`: the agent's writes are a strict subset of gold, and the last turn is the user saying yes plus `###STOP###` to the agent's confirmation request;
   - no-write buckets: `unwarranted_transfer`, `auth_dead_end`, `user_out_of_scope`, `wrongful_refusal`, and otherwise `ended_without_acting` (sub-labelled `deferred`, `declined` or `other` by regex on the user's last turn);
   - `unwarranted_write`: the gold has no writes but the agent wrote;
   - `wrong_arguments`: the same tools as gold were called, with different arguments;
   - `incomplete_multi_step`: the agent's writes are a subset of gold;
   - `extra_write`: gold is a subset of the agent's writes;
   - `wrong_action_type`: anything else.
2. Telecom. Each `reward_info` holds per-gold-action `action_checks`, filled in even when ACTION isn't scored. They show which solution steps never happened.
   - On fixable tasks, an episode that ends in a transfer is labelled `transfer_missed_<family>` by its first missing step family, checked in this order: roaming > data refuel > app permission > other.
   - On unfixable tasks the labels are `text_only_transfer`, `never_escalated` and `broke_state_before_transfer`.
   - The remaining labels are `step_cap` and `user_stop_unresolved`.
3. Overlays and targeted counts. [`scripts/stats.py`](scripts/stats.py) reproduces every other number here:
   - the task-spec overlay: failures on task ids that the v1.0.0 CHANGELOG "Airline/Retail task fixes" later rewrote, using the 29 airline and 27 retail ids actually listed (the section headers say 27 and 26);
   - double confirmations, early transfers, roaming and refuel diagnostics, telecom slices, unrequested writes and the ablation pass rates.
4. Reading. I read 33 failed trajectories in full with [`scripts/dump.py`](scripts/dump.py) (13 retail, 14 airline, 6 telecom), and the last turns of all 57 no-write and premature-stop episodes. I used these reads to check the labels and assign causes.

The counts are mechanical. **Causes are judgments from sampled reads**: read them as "dominant cause", not "every case". The task-spec overlay is an association, not proof: maintainers may have looked hardest at tasks that models failed. Episodes are cited as `model domain task/trial`.

```bash
cd notes/scripts
python3 classify.py                       # per-file buckets, sub-labels, examples, failures on later-fixed tasks
python3 stats.py                          # aggregated tables + every overlay/targeted count in this note
python3 dump.py gpt-4.1-2025-04-14_retail_default 20 0 400   # one episode
```

---

## 1. Starting point: failure types in the paper

### 1a. User-simulator errors (§4.3 Table 2, Appendix E)

The paper manually annotated gpt-4.1 agent × gpt-4.1 user conversations. Overall error rates were:

- retail: 20/50 conversations had errors, 6 of them critical;
- airline: 47/100, 13 critical;
- telecom: 8/50, 3 critical. (Table 2's caption says no telecom critical errors were reported, which contradicts its own row.)

| Paper type | Definition | Retail | Airline | Telecom | Where it shows up here |
|---|---|---|---|---|---|
| Premature termination | The user emits `###STOP###` in the same turn it confirms. In telecom: `###TRANSFER###` before the agent calls the tool | 3/20 | 2/47 | 8/8 | R8 (16), A10 (2), T5 (42) |
| Missing constraint | The user drops a condition from its instructions | 4/20 | 11/47 | – | Contributes to R1, R2 and A5. Seen in `gpt-4.1 retail 20/0`, `o4-mini retail 41/0` and `gpt-4.1-mini retail 16/0` (not counted mechanically) |
| Ungrounded reference | The user invents or misstates details | 2/20 | 15/47 | – | R6: invented order ids in `gpt-4.1-mini retail 94/2` and `o4-mini retail 20/0` |
| Conversation-structure violation | The user mixes tool calls and text, or breaks turn-taking | 11/20 | 19/47 | – | Benign. Not a failure bucket |

### 1b. Agent-side findings (§4.2)

- Dual control vs no-user: gpt-4.1's telecom pass^1 is 0.34 in default mode and 0.52 in no-user mode; o4-mini's is 0.42 and 0.67. With an oracle plan they reach 0.73 and 0.96.
- Length: success falls with the number of actions and sub-issues.
- Issue type: `mms_issue` and `mobile_data_issue` are harder than `service_issue`.
- Persona: Easy beats Hard. None is no easier than Hard.

All four are reproduced from these files in §4.

### 1c. Benchmark reliability (§4.3, Appendix B)

The paper names implementation errors and task-specification errors (under-specification, non-unique solutions) as separate error sources. The repo's v1.0.0 "task quality" release later rewrote 29 airline and 27 retail task ids. I use those ids as a task-spec signal (the "fixed" column below).

### Families used below

| Family | Cause |
|---|---|
| **A** | Agent reasoning or execution: wrong ids or amounts, policy violation, over-execution, under-coverage |
| **B** | Agent communication or coordination: diagnosis by dialogue, transfers, confirmations |
| **U** | User simulator (the paper's four types) |
| **T** | Task-spec or gold error (later fixed, or an impossible gold) |

---

## 2. Retail (500 failures)

| Mode | Fam. | claude-3.7 | gpt-4.1 | 4.1-mini | o4-mini | Total | Share | On later-fixed tasks |
|---|---|---|---|---|---|---|---|---|
| R1 Wrong arguments (variant, item, payment, order) | A, T | 41 | 39 | 43 | 53 | 176 | 35% | 81 |
| R2 Incomplete multi-part request | A, U | 13 | 15 | 32 | 34 | 94 | 19% | 13 |
| R3 Required fact not conveyed (DB correct) | A, T | 6 | 16 | 29 | 12 | 63 | 13% | 38 |
| R4 Wrong action type | A | 10 | 18 | 12 | 7 | 47 | 9% | 16 |
| R5 Extra, destructive write | A, T | 17 | 13 | 9 | 3 | 42 | 8% | 29 |
| R6 Ended with no write: user left or deferred | U, B | 2 | 2 | 14 | 7 | 25 | 5% | 6 |
| R7 Unwarranted transfer | B | 1 | 7 | 6 | 9 | 23 | 5% | 4 |
| R8 User premature stop (yes + `###STOP###`) | U, B | 1 | 6 | 7 | 2 | 16 | 3% | 3 |
| R9 Write on a no-write task | A | 6 | 2 | 2 | 0 | 10 | 2% | 1 |
| R10 Auth dead-end / wrongful refusal | B | 0 | 0 | 1 | 3 | 4 | 1% | 1 |

**Task-spec overlay.** The 27 later-fixed tasks are 24% of retail tasks but hold 38% of retail failures (192/500). Their pass^1 is 0.56, against 0.78 for the other tasks. The concentration is strongest in R3 (38/63) and R5 (29/42). It is weakest in R2 (13/94) and R7 (4/23), which are therefore the cleanest agent signals.

### R1. Wrong arguments (35%)

The argument keys that differ are `new_item_ids` 101, `item_ids` 37, `payment_method_id` 34, `order_id` 29 and `reason` 17. The hot tasks are 79 (13), 0 (11), 20 (11), 98 (10), 76 (9) and 56 (8).

- *Expected:* Choose the variant that satisfies every stated attribute and fallback, on the right order, with the payment method the user chose.
- *Observed:*
  - `claude retail 79/0`. The exact 1000 ml glass red bottle was unavailable. The fallback was "material may differ, colour same as my other 1 L bottle", which means stainless red. Claude picked stainless *black*, anchoring on the old item's colour. The user sim accepted.
  - `gpt-4.1 retail 20/0`, "upgrade everything to the most expensive variant, shoe same size". The agent chose a size-8 shoe for a size-9 owner, and the dark-tone makeup kit at $258.71 instead of the $261.11 maximum. The user sim, told "same size", replied "Yes … upgrade all those items as you listed".
- *Likely cause:*
  - Mainly agent attribute matching over long variant lists: the agent anchors on the current item's options.
  - The user sim often fails to enforce its own constraint at confirmation (missing constraint, U).
  - 81/176 sit on later-fixed tasks (0, 1, 20, 76, 98–99: "similar" → "same", frame-size priority, explicit cancel reason), so part is T.
- *Impact:* One wrong id fails the DB hash, however good the conversation was. This is the largest retail bucket for every model.

### R2. Incomplete multi-part request (19%)

The agent's writes were a strict subset of gold. The missing writes are `modify_pending_order_address` 46, `modify_pending_order_items` 23 and `return_delivered_order_items` 19. The hot tasks are 41 (13), 71 (9), 109, 72 and 112 (7 each).

- *Expected:* Enumerate the user's orders and apply every requested change. For example, "correct all order addresses and my user address" means every pending order plus the profile.
- *Observed:*
  - `o4-mini retail 41/0`. The agent fixed the puzzle item, the address of order #W4082615 and the profile. Pending order #W9583042 was never touched. The user sim had narrowed the request itself: "update the shipping address for this order".
  - `gpt-4.1-mini retail 16/0`. The agent wrongly told the user that delivered order #W9389413 "does not have a wristwatch". The user sim dropped the return ("I must have made a mistake"), and only the two cancellations were done.
- *Likely cause:* The agent works on the order in focus and doesn't cross-check the others. The user sim either narrows the request or defers to the agent's wrong claim (missing constraint, U). gpt-4.1-mini and o4-mini do this about 2.4× as often as claude and gpt-4.1 (66 vs 28). Only 13/94 are on later-fixed tasks.
- *Impact:* Silent partial success. The user is satisfied and the reward is 0.

### R3. Required fact not conveyed (13%)

The DB matched but the communicate check failed. The hot tasks are 3 (10), 2 (8), 4 (8), 34 (6) and 43 (5).

- *Expected:* State the exact requested number, e.g. available t-shirt options `10`, or a refund total.
- *Observed:* `gpt-4.1-mini retail 3/0`: "There are 12 available t-shirt options". The product has 12 variants, of which 10 are available.
- *Likely cause:*
  - Counting or aggregation by the agent, on an ambiguous question. Tasks 2–4 got "exactly" added in v1.0.0.
  - Tasks 33–34 had a wrong expected refund (`1093.34`), which v1.0.0 removed (T).
  - 38/63 are on later-fixed tasks.
  - gpt-4.1-mini is hit most (29).
- *Impact:* The reward is 0 despite correct actions. In this domain it is mostly a gold/wording artefact.

### R4. Wrong action type (9%)

The swaps are modify items → cancel order (12), exchange → return (12) and modify address → cancel (7). The hot tasks are 27 (10), 34 (7) and 36 (7).

- *Expected:* When only one operation per delivered order is possible, honour the stated preference. Task 27: "if the agent says they can only do one, you prefer to do the exchange".
- *Observed:* `gpt-4.1 retail 27/0`. The agent ran the return (hose and backpack) first. The exchange then failed because the order was no longer `delivered`. The agent couldn't undo the return, and the user asked for a transfer.
- *Likely cause:* The agent sequences writes without anticipating that the first one changes the order status. The "cancel instead of modify" swaps resolve an unavailable item by cancelling the whole order.
- *Impact:* Irreversible wrong state.

### R5. Extra, destructive write (8%)

Gold writes were all present (exactly so in 29/42 cases), plus extra ones: `cancel_pending_order` 26 and `return` 9. The hot tasks are 28 (12), 99 (11) and 82 (8).

- *Expected:* Don't act beyond the request. Task 28: "If cancelling one item in an order is not possible, forget about it".
- *Observed:* `gpt-4.1 retail 28/0`. All three returns were right. Then `cancel_pending_order(#W2575533)` cancelled a five-item, $1.6k order to remove a $95 hose, and the agent told the user that "the Garden Hose from your pending order has been cancelled".
- *Likely cause:*
  - The agent over-satisfies the literal request and misreports what it did.
  - 29/42 are on later-fixed tasks (28 and 99 were clarified), so part is T.
- *Impact:* The most harmful retail mode in deployment: destructive, irreversible and misreported.

### R6. Ended with no write: user left or deferred (5%)

There were no writes and no refusal, and the user ended the episode. In 14 cases the user defers ("I'll be back with the order ID"). The other 11 are mixed: the user leaves after an informational answer, or sends a bare `###STOP###` after the agent's goodbye.

- *Expected:* The agent finds the order itself (the user details list every order id) and finishes the task.
- *Observed:*
  - `gpt-4.1-mini retail 94/2`. The agent kept asking for an order id instead of calling `get_user_details`. The user sim invented one ("8745632"), it was "not found", and the user left to "check the packing slip".
  - `o4-mini retail 20/0`. The user sim invented an id, then picked the wrong (processed) order from the list. The agent told it to wait for delivery.
- *Likely cause:* A mix of U (ungrounded references, the paper's type) and B (the agent asks the user for data it can look up).
- *Impact:* Concentrated in gpt-4.1-mini (14).

### R7. Unwarranted transfer (5%)

- *Expected:* Transfer only when the request is out of scope.
- *Observed:*
  - `gpt-4.1 retail 51/1`. The user's guessed order id pointed to a pending order. The agent never checked the user's other orders (the camera was in #W4689314) and offered a transfer.
  - `o4-mini retail 33/1`. The agent transferred before authenticating, on the word "partial cancellation".
- *Likely cause:* The agent uses transfer as a fallback when the first lookup fails. o4-mini does it most (9). Only 4/23 are on later-fixed tasks.
- *Impact:* None of the writes happen.

### R8. User premature stop (3%)

There were 16 failures; the missing writes were item modifications (13) and address changes (12). The hot tasks are 112, 104, 72, 101 and 102.

- *Expected:* The user lets the agent execute after confirming.
- *Observed:* `gpt-4.1-mini retail 102/0`. The user had already said "Yes, please proceed …" twice. The agent re-summarised and asked "Please confirm with a 'yes'", and the user replied "Yes. Go ahead. Thanks.###STOP###".
- *Likely cause:* The paper's critical premature termination (U). In 9/16 cases the agent re-asked for confirmation after the user had already said yes with no write in between, so the agent's stalling contributes (B).
- *Impact:* A cheap, correctable loss. gpt-4.1 and gpt-4.1-mini make up 13/16.

### R9–R10. Small modes

- **R9, write on a no-write task (10).** Task 57 accounts for 5. In `gpt-4.1-mini retail 57/0` the agent cancelled the whole order before checking the user's condition ("only if refunded to gift card"), without asking for confirmation.
- **R10 (4).** Auth dead-ends (2, both `o4-mini 39`) and wrongful refusals (2). Structured `known_info` makes identity details reliably available, so these are much rarer than in τ-bench v1.

---

## 3. Airline (369 failures)

| Mode | Fam. | claude-3.7 | gpt-4.1 | 4.1-mini | o4-mini | Total | Share | On later-fixed tasks |
|---|---|---|---|---|---|---|---|---|
| A1 Policy-violating write on a refuse task | A | 36 | 20 | 29 | 10 | 95 | 26% | 34 |
| A2 Wrong arguments (bags, flights, payment) | A, T | 20 | 22 | 20 | 17 | 79 | 21% | 63 |
| A3 Extra write next to the gold writes (mostly a forbidden cancel) | A, T | 20 | 13 | 20 | 6 | 59 | 16% | 49 |
| A4 Unwarranted / immediate transfer | B | 5 | 6 | 3 | 21 | 35 | 9% | 32 |
| A5 Incomplete multi-part request | T, U, A | 5 | 10 | 5 | 14 | 34 | 9% | 29 |
| A6 Wrong action type | A, T | 8 | 2 | 4 | 6 | 20 | 5% | 18 |
| A7 Required fact not conveyed | T, A | 2 | 4 | 10 | 1 | 17 | 5% | 14 |
| A8 Ended with no write: user declined or left | T, U | 0 | 5 | 5 | 4 | 14 | 4% | 11 |
| A9 Wrongful refusal | A | 4 | 5 | 2 | 2 | 13 | 4% | 7 |
| A10 User premature stop / auth dead-end | U | 0 | 1 | 1 | 1 | 3 | 1% | 3 |

**Task-spec overlay.** The 29 later-fixed tasks are 58% of airline tasks but hold 70% of airline failures (260/369). Their pass^1 is 0.44, against 0.68 for the rest. A1 is the exception: only 34/95 of its failures are on fixed tasks, so it is the clearest agent failure in airline. A2–A8 are 80–94% on fixed tasks.

### A1. Policy-violating write on a refuse task (26%)

The gold has no writes. The agent called `cancel_reservation` 67 times, `update_reservation_flights` 18, `send_certificate` 13 and `update_reservation_baggages` 3. The hot tasks are 1 (12), 41 (11), 43 (10), 5/45/48 (9 each), 10 (8) and 26 (7).

- *Expected:* Check the cancellation, compensation and modification rules against the reservation data. The policy says "The API does not check that cancellation rules are met". Keep refusing when the user insists.
- *Observed:*
  - Date arithmetic: `claude airline 1/0`. The booking was created 2024-05-14 09:52 and "now" is 2024-05-15 15:00 (29 h). Claude said the booking was "within 24 hours" and cancelled with a refund. The user's "a rep approved it" was never needed.
  - Trusting user claims over data: `gpt-4.1-mini airline 48/1`. The user says it "booked 10 hours ago". The agent repeats this and cancels without checking `created_at`.
  - Misapplying a rule: `gpt-4.1 airline 47/0`. The basic-economy booking *does* have insurance. The agent said insurance gives "a full refund … for personal reasons", but the policy covers health or weather only. It cancelled for "best friend's birthday".
  - Pressure plus gratuitous compensation: `claude airline 43/0`. "I'm a silver member" led to "You're absolutely right…": the agent cancelled a non-refundable basic-economy booking and then offered a $100 certificate.
  - Ignoring the class rule: `claude airline 41/0` cancelled a basic-economy booking with no qualifying reason.
- *Likely cause:*
  - Agent policy reasoning: date maths, eligibility conditions, verifying what the user claims.
  - Sycophancy under persistence.
  - Claude is the most compliant (36). o4-mini is the least (10) but escalates instead (A4).
- *Impact:* The dominant *agent-caused* airline failure, and the one with direct monetary cost: unauthorised refunds and certificates.

### A2. Wrong arguments (21%)

The differing keys are `nonfree_baggages` 29, `flights` 28, `payment_id`/`payment_methods` 26 and `reservation_id` 10. The hot tasks are 21 (12), 33 (12), 29 (7), 37 (7), 20 (5) and 15 (4).

- *Expected:* Compute free bags from tier × cabin × passengers, pick flights that meet the constraints, and pay from the requested instrument.
- *Observed:*
  - `gpt-4.1 airline 17/1`, which is *not* on a fixed task. For a gold member in economy (3 free bags) the agent said "2 free with your gold membership" and charged `nonfree_baggages: 1`. It used the silver row of the table.
  - `gpt-4.1 airline 33/1`. The agent set 4 non-free bags. **But the gold is itself wrong:** it says 2 non-free for a gold-member economy passenger, and v1.0.0 "corrected baggage charges for Gold member". No policy-following agent could match it.
  - `gpt-4.1-mini airline 38/0`. The agent issued a $150 certificate, believing the user's "3 passengers", and checked only *after* issuing that there was 1 passenger. The gold $50 is also wrong: v1.0.0 removed compensation from tasks 2, 27 and 38 as not allowed.
- *Likely cause:*
  - Mixed. 63/79 failures are on later-fixed tasks (21, 33, 29, 37, 15, 38), so T dominates.
  - The rest are agent table-lookup and arithmetic errors, and acting on user-asserted facts before verifying them.
- *Impact:* The DB fails, and customers are charged or credited the wrong amount.

### A3. Extra write next to the gold writes (16%)

Most extras are cancels (`cancel_reservation` 49). The gold writes were exactly present in 36/59 cases; in the other 23 they also had wrong arguments. The hot tasks are 35 (14), 39 (10), 24 (8), 9 (7) and 42 (7).

- *Expected:* Refuse the forbidden part (usually a cancel-for-refund) and do the allowed part.
- *Observed:* `gpt-4.1 airline 35/0`. To "I'm a silver member, so I expect a full refund", the agent replied with an invented rule ("As a silver member, you are eligible for a full refund") and cancelled. The agent then searched only direct flights and booked the single one it found, not the requested second-cheapest (a one-stop).
- *Likely cause:*
  - The same policy capitulation as A1.
  - 49/59 are on later-fixed tasks. Tasks 9, 35, 39 and 42 had gold or data errors (T).
- *Impact:* As A1.

### A4. Unwarranted / immediate transfer (9%)

- *Expected:* Handle what can be handled, refuse what can't, and transfer only when the request is out of scope.
- *Observed:* `o4-mini airline 24/0`. The user's first message asks to remove a passenger. o4-mini calls `transfer_to_human_agents` on its first turn, so the bookable JFK→SEA round trip never happens. In 9 of o4-mini's 21 transfers, the agent transferred by the user's second message.
- *Likely cause:*
  - Model-specific over-escalation: o4-mini maps "can't do X" to "transfer".
  - The fixed-task share is high (32/35; task 27 accounts for 8), so ambiguous tasks trigger it more.
- *Impact:* The whole episode is lost, including the solvable parts.

### A5. Incomplete multi-part request (9%)

- *Expected:* Finish every sub-request.
- *Observed:*
  - `gpt-4.1 airline 32/0`. The agent upgraded basic economy and changed flights in one `update_reservation_flights` call. The gold demands two calls: the cabin first, then the flights. v1.0.0 "enforced two-step cabin upgrade then flight change sequence".
  - `o4-mini airline 23/0`. The gold requires three separate bookings, the user's "great idea" for using three certificates. The user sim never proposed it, and the agent booked one 3-passenger reservation.
- *Likely cause:* Mostly T (29/34 on fixed tasks) and U. The user sim doesn't produce the scripted idea, which is the missing constraint in the paper's airline example.
- *Impact:* Weak agent signal.

### A6–A10. Small modes

- **A6, wrong action type (20; 18 on fixed tasks).** The agent upgrades in place where the gold cancels and rebooks, or the reverse (tasks 14, 23, 29). Task 29's gold was later changed to "destination change requires cancel+rebook".
- **A7, required fact not conveyed (17).** Task 7 accounts for 10. "Total cost of my other upcoming flights" got answers of $708, $1,016 and $17,021 against a gold of $1,628. Task 7 was later corrected, so this is T plus aggregation ambiguity.
- **A8, ended with no write (14).** Task 14 accounts for 6. The user declines because the change would hit a Mastercard, and the user sim's constraint was impossible ("replaced impossible Mastercard constraint"), so this is T.
- **A9, wrongful refusal (13).** Task 22 accounts for 6. `gpt-4.1 airline 22/1`: "basic economy flights cannot be modified", so the agent refused the cabin upgrade, passenger change and bags. The policy allows all three.
- **A10 (3).** Two yes-plus-`###STOP###` premature stops (task 23) and one auth dead-end.

---

## 4. Telecom (1,051 failures)

| Mode | Fam. | claude-3.7 | gpt-4.1 | 4.1-mini | o4-mini | Total | Share |
|---|---|---|---|---|---|---|---|
| T1 Roaming never fixed → transfer (user abroad) | B, A | 162 | 228 | 165 | 183 | 738 | 70% |
| T2 Data refuel missed → transfer | A, B | 12 | 20 | 28 | 41 | 101 | 10% |
| T3 Other device step missed (APN, VPN, data saver…) → transfer | A, B | 28 | 9 | 10 | 27 | 74 | 7% |
| T4 App permission missed → transfer (MMS) | A | 15 | 7 | 3 | 5 | 30 | 3% |
| T5 Text-only transfer on a must-transfer task | U, B | 6 | 25 | 11 | 0 | 42 | 4% |
| T6 Step cap (tool-call loop) | A | 1 | 3 | 32 | 0 | 36 | 3% |
| T7 Resumed a contract-expired line (policy violation) | A | 6 | 6 | 0 | 0 | 12 | 1% |
| T8 User `###STOP###` with state still wrong | A | 0 | 2 | 1 | 8 | 11 | 1% |
| T9 Must-transfer task never escalated | A | 1 | 0 | 6 | 0 | 7 | 1% |

T1–T4 are the 943 fixable-task episodes (90%) that end in a transfer with gold steps undone. Before transferring, the agents had matched 2/3 of the gold steps on median (mean 0.66). An episode is labelled by its first missing family, but it often misses others too.

Slices (pass^1, all 4 models):

| Slice | Pass^1 |
|---|---|
| Intent | `service_issue` 0.77, `mobile_data_issue` 0.50, `mms_issue` 0.16 |
| Persona | Easy 0.52, Hard 0.38, None 0.37 |
| Sub-issues | 0.67 at 2, 0.45 at 3, 0.57 at 4, 0.38 at 5, 0.18 at 6, 0.10 at 7, 0.08 at 8, 0.00 at 9 |
| User abroad | **0.21** on the 64 `user_abroad_*` tasks (1,024 episodes), against **0.70** on the others |

Model spread on mobile data is large: claude 0.69 against gpt-4.1 0.30.

### T1. Roaming never fixed (70%)

- *Expected:* The tech-support manual says to check roaming "When User is Abroad": the device's Data Roaming must be on (`toggle_roaming`, user side), and the line must be roaming-enabled (`enable_roaming`, agent side). The agent has to find out that the user is abroad.
- *Observed:* `gpt-4.1 telecom [mobile_data_issue]bad_vpn|data_saver_mode_on|user_abroad_roaming_disabled_on[PERSONA:None]/0`.
  - The agent ran a speed test, reset the APN and rebooted, then (correctly) turned off data saver and the VPN. The speed test still failed.
  - It then read line L1002, which showed `"roaming_enabled": false`. It never asked where the user was, and offered a transfer.
  - The user was in France the whole time. The user sim had also dropped the "Data Roaming Enabled" line when relaying `check_network_status`.
- *Likely cause:* **Hidden-fact diagnosis under dual control.** Being abroad lives only in the user's `known_info`. Across all 740 failed abroad episodes with a roaming step missed:

  | Signal | Failed, roaming missed (740) | Passed abroad episodes (214) |
  |---|---|---|
  | Agent asked about location or travel | 96 | 190 |
  | Agent mentioned roaming at all | 231 | all 214 |
  | "Abroad" surfaced in the dialogue | 76 | 187 |
  | User volunteered it before any agent question | 64 | 162 |

  - Success depends largely on whether the user sim happens to volunteer the fact (U variance), and on whether the agent thinks to ask (B).
  - By model: on the 256 abroad episodes each, claude asks about location in 116 and passes 82. gpt-4.1 asks in 63 and passes 20. o4-mini asks in 49 and passes 48.
  - The ablation files confirm the cause. On abroad tasks gpt-4.1 goes from 0.08 (default) to 0.56 (no-user: the agent gets a ticket) and 0.61 (oracle plan). o4-mini goes from 0.19 to 0.64 and 0.93.
- *Impact:* **The single largest failure in the benchmark: 738 of 1,920 failures (38%).** It also explains most of the §4.2 issue-type and sub-issue-count effects, since abroad issues are spread across the mobile-data and MMS tasks.

### T2. Data refuel missed (10%)

Across all 301 failed episodes with `refuel_data` missed:

- the agent called `get_data_usage` in only 58;
- it offered a top-up in 11;
- it called `refuel_data` with the wrong amount or line in 14 (o4-mini: 1 GB, 0 GB, or line L1001 instead of 2 GB on L1002).

- *Expected:* After service and roaming are fine, check data usage against the plan limit and offer a refuel.
- *Likely cause:* The agent doesn't follow the policy tree to the usage check before escalating. o4-mini is worst (41).
- *Impact:* A fixable task is escalated.

### T3–T4. Other device steps and MMS permissions (10%)

- **T3.** Mostly `reset_apn_settings` for MMS (38) and `disconnect_vpn` (16).
- **T4.** `claude telecom [mms_issue]bad_wifi_calling|break_apn_mms_setting|break_app_sms_permission|data_usage_exceeded[PERSONA:Hard]/0`.
  - The user relayed "my messaging app has permission for storage and phone".
  - The agent listed "checking app permissions" as done, never noticed that SMS was missing, and transferred.
  - Across the 146 failed episodes with a permission missed, the agent mentioned permissions in 84 and the user ran `check_app_permissions` in 63.
- *Likely cause:* The agent can't see the device. It must infer the fault from the user's paraphrase, and it misreads what is *absent* from that paraphrase (A, B).

### T5. Text-only transfer on a must-transfer task (4%)

- *Expected:* The telecom policy says: "first make a tool call to transfer_to_human_agents, and then send the message …".
- *Observed:* `gpt-4.1 telecom [service_issue]airplane_mode_on|break_apn_settings|lock_sim_card_pin[PERSONA:None]/0`.
  - The agent asked: "Would you like me to transfer you to a human agent …?"
  - The user replied: "Yes, please transfer me …###TRANSFER###". The episode ended before any tool call, so ACTION = 0.
  - The same pattern occurs on fixable tasks 74 times. It is harmless there, because env assertions fail anyway.
- *Likely cause:* This is the paper's telecom premature termination (U), which accounts for all 8 of its annotated telecom errors. It is equally an agent policy violation, because the agent asks permission instead of calling the tool (B). gpt-4.1 does it most (25); o4-mini never does (0), and its unfixable-task pass rate is 80/80.
- *Impact:* A correct decision scores 0.

### T6. Step cap (3%)

- *Observed:* `gpt-4.1-mini telecom [mms_issue]bad_network_preference|break_app_sms_permission|user_abroad_roaming_disabled_on[PERSONA:Hard]/0`. The agent repeats `get_customer_by_phone → get_details_by_id(L1002) → get_details_by_id(D1002)` for the rest of the 200 steps.
- *Likely cause:* A degenerate repetition loop: 32 of the 36 cases are gpt-4.1-mini (A).

### T7. Resumed a contract-expired line (1%)

- *Expected:* "You are not allowed to lift the suspension if the line's contract end date is in the past, even if the user has paid all their overdue bills". So: transfer.
- *Observed:* `claude telecom [service_issue]contract_end_suspension|unseat_sim_card[PERSONA:Hard]/0`. Line L1002 had `contract_end_date` 2025-01-31. Claude sent a payment request for an overdue bill, called `resume_line`, and guided a SIM reseat. The user saw signal and said `###STOP###`. `assert_service_status: no_service` failed.
- *Likely cause:* Agent policy violation. All 12 cases (claude 6, gpt-4.1 6) called `resume_line` plus `send_payment_request`. The assertion correctly encodes the policy, so this is not a task-spec smell.

### T8–T9. User stop with state still wrong; never escalated

- **T8 (11).**
  - o4-mini has 4 cases of re-sending `send_payment_request` *after* the bill was paid and the line resumed, which re-opens the bill (`assert_no_overdue_bill` fails): `o4-mini telecom [service_issue]overdue_bill_suspension|unseat_sim_card[PERSONA:Easy]/0`.
  - In 4 more, o4-mini refuelled 0–1 GB, or refuelled line L1001, where 2 GB on L1002 was expected.
  - gpt-4.1-mini resumed a line without collecting payment (1). gpt-4.1 gave up on MMS issues and the user stopped (2).
- **T9 (7).** On PIN-locked SIM tasks the agent told the user to unlock the SIM themselves and ended without a transfer (gpt-4.1-mini 6).

### Process failures that are not scored

- Unrequested agent writes (episodes with a successful call to a tool not in the gold path):
  - o4-mini: `send_payment_request` 197, `disable_roaming` 44, `enable_roaming` 35, `resume_line` 27, `suspend_line` 6;
  - gpt-4.1: payment 70, resume 59;
  - claude: payment 60, resume 58;
  - gpt-4.1-mini: payment 60, resume 28.

  Example: `o4-mini telecom [service_issue]airplane_mode_on|lock_sim_card_pin[PERSONA:Easy]/2` suspends the customer's line with reason `"dummy"` (and resumes it), and still scores 1.
- Agent calling user-device tools: claude calls tools such as `check_status_bar` and `can_send_mms` itself in 115 of its 456 telecom episodes; the other models never do. The calls error.

---

## 5. Failure modes shared across domains

| Shared mode | Retail | Airline | Telecom | Core pattern |
|---|---|---|---|---|
| **X1. Incomplete coverage of a multi-part need** | R2: 94 (19%) | A5: 34 (9%), mostly T | T1–T4: 943 (90%) | The agent resolves the salient part and stops. Retail misses other orders. Telecom misses hidden sub-issues. The user sim rarely re-raises what's left, and sometimes narrows the request itself. |
| **X2. Escalation as a fallback** | R7: 23 (5%) | A4: 35 (9%) | T1–T4 all end in transfer (943) | Transfer replaces diagnosis or refusal. o4-mini is the most transfer-prone in airline. Telecom's 90% "escalated with steps undone" is the extreme case. |
| **X3. Wrong ids or amounts from lookup or arithmetic** | R1: 176 (35%) | A2: 79 (21%), mostly T | 14 wrong refuel amounts or lines | Near-miss variants, the wrong tier row, wrong passenger counts. One mismatch fails the hash, and the user can't see it. |
| **X4. Policy-violating or destructive writes** | R5 + R9: 52 (10%) | A1 + A3: 154 (42%) | T7: 12, T8 re-billing: 4, plus unscored spurious writes | Airline: capitulation and bad eligibility maths. Retail: over-literal "helpfulness" (cancelling a whole order). Telecom: resuming a forbidden line. Telecom scores none of it unless an assertion trips. |
| **X5. User-sim premature termination** | R8: 16 | A10: 2 | T5: 42 | The simulator consents and ends in the same turn: 60 failures in all (3% of failures). In 10/18 retail and airline cases the agent had re-asked for a confirmation it already had. In telecom the agent asked "shall I transfer?" instead of calling the tool. |
| **X6. Hidden or asserted facts** | R6: invented order ids | A1/A2: "booked 10 h ago", "3 passengers" | T1: "abroad" (738) | Facts that only the user holds. The agent either never asks (telecom) or trusts unverified claims (airline). The user sim also invents facts (retail). |
| **X7. Required fact not conveyed** | R3: 63 (13%) | A7: 17 (5%) | – | Counts and totals are wrong or ambiguous. 52/80 are on later-fixed tasks. |
| **X8. Task-spec and gold errors** | 38% of failures on 24% of tasks | 70% of failures on 58% of tasks | none found | Wrong golds (airline 33's bags, 38's compensation, retail 33–34's refund) and loophole-dependent golds (airline 23, 32). Telecom's generated tasks look clean: the one candidate (T7) turned out to be an agent policy violation. |

### Takeaways

1. **Telecom failure is mostly one hidden fact.** 738/1,920 failures (38%) are roaming never fixed because "abroad" never surfaced. Ablation pass rates on abroad tasks jump roughly 7× for gpt-4.1 and 3× for o4-mini when the agent is told (no-user) rather than having to ask. Dual-control difficulty here is information-gathering, not device manipulation.
2. **Retail and airline fail on precision, telecom on coverage.** Retail and airline lose on one wrong id or one forbidden write. Telecom loses on unfinished diagnosis. Coverage failures grow sharply with length: pass^1 falls from 0.67 to 0.00 between 2 and 9 sub-issues.
3. **The cleanest agent signals are retail R2/R7 and airline A1.** These carry little task-spec contamination. Most other airline modes sit 80–94% on tasks that were later rewritten, so paper-era airline scores understate the agents, and pre- and post-v1.0.0 numbers aren't comparable.
4. **The user-sim critical error is the same in every domain, and partly agent-induced.** Consent and stop arrive in one turn. Re-asking for confirmation, or asking before transferring, gives the simulator the opening.
5. **Reward 1 doesn't certify good process.** Examples: o4-mini's 197 episodes with unrequested payment requests, a `suspend_line(reason="dummy")` in a passing episode, and claude's 115 episodes calling user tools. None are penalised. A deployment would want transfer precision and unrequested-write rates measured directly.
