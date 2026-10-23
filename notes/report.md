# τ²-bench user simulator: what to fix first

**Fork:** [github.com/zgoel317/tau2-bench](https://github.com/zgoel317/tau2-bench/tree/s2-simulator-fixes) (branch `s2-simulator-fixes`) · Evidence: Appendix A, [simulator priorities](simulator-priorities.md), [failure modes](failure-modes.md)

## 1. Diagnosis

I analysed the paper's June 2025 runs (4 agents × 3 domains × 4 trials, `gpt-4.1` simulator; 1,920 of 4,448 episodes failed), counting a failure against the simulator only if it made the first mistake.

**S1. What the simulator says.** *Expected:* the user conveys its scenario consistently and never invents facts. *Observed:*
- **S1a, 697:** it mentions decisive facts only at random. Same agent and abroad task: trial 0 opens *"I'm currently in France"* and passes; trial 3 never says it and fails. Over 1,024 abroad episodes it never surfaced in 71% (pass 0.04) vs 26% volunteered (0.64).
- **S1b, 17:** it invents IDs when agents ask for ones they could look up.
- **S1c, ≈16:** it asks for the wrong thing unprompted.

*Cause/impact:* chance in the user's first message decides whether it says it is abroad, so agents pass or fail on luck; they share the blame, asking in only 38 of 760 episodes where it wasn't volunteered.

**S2. When the simulator ends the call.** *Expected:* the user ends only once every request is carried out. *Observed:*
- **S2a, 18:** it says "yes" and hangs up in one message, e.g. *"Yes. Go ahead. Thanks.###STOP###"*, before any write.
- **S2b, 42:** it treats an offer to transfer as the transfer (*"Yes, please transfer me…###TRANSFER###"*), so the graded tool call never happens.
- **S2c, ≈24 (CI 8–39):** it leaves requests undone, e.g. never raising its second order (*"that's everything!"*). In 20 sampled retail partial-completion failures, 4 were S2c and 14 agent-started.

*Cause:* the text prompts lack the voice prompt's "agreeing ≠ done" and "verify ALL items" rules and accept a transfer once *"clearly indicated"* ([guidelines.py](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/guidelines.py#L220)); the code ends the episode on a token anywhere in a message ([user_simulator.py](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/user_simulator.py#L142)). *Impact:* agents are scored on turns they never get.

**Which first.** With S1a, S1 (≈730) dwarfs S2 (≈84); without it, S2 leads (≈84 vs ≈33). I prioritise S2, a protocol defect; forgetting is what real customers do, and forcing disclosure in S1a's task data would hand the agent the answer.

## 2. Two approaches

**Fix 1** copies the voice prompt's completion rules into the text prompts: agreeing is not completion, verify every item, and send `###TRANSFER###` only once the agent says it *has* transferred you. It covers all of S2, but only probabilistically, and the voice rules have never been measured. The risk is a pushier user who fights correct refusals or coaches the agent with its checklist.

**Fix 2** makes an end token count only on its own: if `###STOP###` or `###TRANSFER###` arrives with other text, the token is stripped and the simulator decides again next turn (at most once in a row). It is ~25 lines in `UserSimulator`, text mode only, and removes S2a and S2b deterministically but not S2c. The extra turn lets the agent make an unconfirmed write or meet a missed `communicate_info` check.

**I recommend Fix 2 first:** it removes the mechanism behind 60 exactly counted failures and is testable offline. Fix 1, the only remedy for S2c, follows. The branch implements both, with offline tests.

## 3. Experiment

**Arms.** Baseline (A), a repeat to measure noise (A′), Fix 1 (B), Fix 2 (C), both (D), all from one commit with simulator `gpt-4.1-2025-04-14` at temperature 0, fixed seeds and no LLM cache. Agents: `gpt-4.1` and `gpt-4.1-mini` (51 of the 60 S2a/S2b failures).

**Cases.** The *target set* is the 33 tasks behind the S2 failures (8 trials each); the *guard set* (4 trials each) holds refusal tasks, transfer tasks the baseline passes, and 30 random tasks per domain.

**Measures.** Primary: each target task's pass rate against A. Mechanism: text-plus-token messages vanish in C and D, the turn after a deferral holds the pending tool call, and old S2 failures become agent-caused. Guard pass rate, timeouts and post-task turns stay flat.

**Variability.** Failures cluster by task, so each task is compared with its own baseline, with task-bootstrap CIs and the A–A′ gap as the noise floor. A fix works if the target CI lower bound is above zero, or its S2 failures become agent-caused, with the guard set within noise.

## 4. Challenging the conclusion

**Fidelity.** Blind-audit a sample of transcripts per arm: did users pursue every item, end only when done, invent nothing, and end like a real caller?

**Better simulator or easier task?** Gains should come only from the pending action in deferred or premature-end episodes. Users may add no new IDs: "what about my other order?" is fine, naming the item is coaching. An agent that says "transferring you" without the tool call must now fail. If agent scores converge, the task got easier.

**What would change my mind.** No target gain beyond A–A′ noise, or agents rarely making the pending call after a deferral, would mean S2 doesn't affect scores. Refusal-task shifts would mean Fix 1 made users pushy. **On the premise:** S1a's fix is *controlled* forgetting ("mentions location only if asked") applied in every trial.

**AI use.** I proposed both fixes, refined the counting rule and S1/S2 taxonomy, and outlined this report. Claude Code implemented the fix and analysis scripts, labelled the sampled conversations under my counting rule, and assembled the report.

---

## Appendix A. Evidence table

| Code | Episode (agent · domain · task/trial) | Turn that matters | Expected | Root cause | Count (method) |
|---|---|---|---|---|---|
| S2a | gpt-4.1-mini · retail · 102/0 | Agent: "Please confirm with a 'yes'" → User: *"Yes. Go ahead. Thanks.###STOP###"*; DB reward 0 | Wait for the write | Token ends the call anywhere in the message; no "agreeing ≠ done" rule in text prompts | 18 (exact; 10 after a re-ask) |
| S2b | gpt-4.1 · telecom · airplane_mode_on\|break_apn_settings\|lock_sim_card_pin/0 | *"Would you like me to transfer you…"* → *"Yes, please transfer me…###TRANSFER###"*; ACTION 0 | Wait for the transfer | "clearly indicated" lets an offer count ([guidelines.py:256](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/guidelines.py#L256)) | 42 (exact; judgment call: policy neither requires nor forbids asking first) |
| S2c | claude · retail · 104/3; claude · retail · 69/2 | *"Nope, that's everything!"* with the second order untouched; *"I'll reach out again once the status updates"* instead of the scripted fallback | Pursue all items / the fallback | No "verify ALL items" rule in text prompts | ≈24, CI 8–39 (R2 sample 4/20 + R6 read in full 5/25) |
| S1a | claude · telecom · bad_network_preference\|user_abroad_roaming_enabled_off[Hard]/0 vs /3 | Trial 0 opens *"I'm currently in France"* → pass; trial 3 never says it → fail | Consistent across trials | Opening-message sampling noise | 697 (exact); never surfaced 71% (pass 0.04) vs volunteered 26% (0.64); asked → answered 36/38 |
| S1b | o4-mini · retail · 20/0 | Agent: *"I've located your account… provide the order ID"* → *"the order ID is 45789213"* (doesn't exist) | Say it doesn't know | Agent asks for an ID it could look up; simulator invents | 17 (exact; 17/17 after an agent ask) |
| S1c | claude · retail · 71/1 | Agent lists bare order numbers; user picks *"order #W7032009"*, which it was never given, and it's wrong | Describe the order | Simulator guesses instead of describing | ≈16, floor 4 (samples) |
| Excluded | e.g. 19 of 20 sampled R1 failures | Agent proposes the wrong item; user says yes | — | Agent made the first mistake | Not counted against the simulator |

Scripts that reproduce every count: `notes/scripts/` (`sim_attribution.py`, `disclosure.py`, `invented_ids.py`, `sample_for_labels.py`, `dump.py`). Episode-level labels: [simulator priorities, Appendix](simulator-priorities.md#appendix-hand-labels).
