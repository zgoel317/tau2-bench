# τ²-bench user simulator: what to fix first

**Fork:** [github.com/zgoel317/tau2-bench](https://github.com/zgoel317/tau2-bench/tree/s2-simulator-fixes) (branch `s2-simulator-fixes`) · Evidence: Appendix A, [simulator priorities](simulator-priorities.md), [failure modes](failure-modes.md)

## 1. Diagnosis

I analysed the paper's June 2025 runs (4 agents × 3 domains × 4 trials, `gpt-4.1` simulator; 1,920 of 4,448 episodes failed), counting a failure against the simulator only if it made the first mistake.

**S1. What the simulator says.** *Expected:* the user conveys its scenario consistently and never invents facts. *Observed:*
- **S1a, 697:** it mentions decisive facts only at random. Same agent and abroad task: trial 0 opens *"I'm currently in France"* and passes; trial 3 never says it and fails. Over 1,024 abroad episodes it never surfaced in 71% (pass 0.04) vs 26% volunteered (0.64).
- **S1b, 17:** it invents IDs when agents ask for ones they could look up.
- **S1c, ≈16:** it asks for the wrong thing unprompted.

*Cause/impact:* Whether the user's first message says it is abroad is up to chance, so agents pass or fail on luck; they share the blame, asking in only 38 of 760 episodes where it wasn't volunteered.

**S2. When the simulator ends the call.** *Expected:* the user ends only once every request is carried out. *Observed:*
- **S2a, 18:** it says "yes" and hangs up in one message, e.g. *"Yes. Go ahead. Thanks.###STOP###"*, before any write.
- **S2b, 42:** it treats an offer to transfer as the transfer (*"Yes, please transfer me…###TRANSFER###"*), so the graded tool call never happens.
- **S2c, ≈24 (CI 8–39):** it leaves requests undone, e.g. never raising its second order (*"that's everything!"*). In 20 sampled retail partial-completion failures, 4 were S2c and 14 agent-started.

*Cause:* the text prompts lack the voice prompt's "agreeing ≠ done" and "verify ALL items" rules and accept a transfer once *"clearly indicated"* ([guidelines.py](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/guidelines.py#L220)); the code ends the episode on a token anywhere in a message ([user_simulator.py](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/user_simulator.py#L142)). *Impact:* agents are scored on turns they never get.

**Which first.** With S1a, S1 (≈730) dwarfs S2 (≈84); without it, S2 leads (≈84 vs ≈33). I prioritise S2, a protocol defect. Forgetting information is plausible customer behavior, and forcing disclosure in S1a's task data would hand the agent the answer.

## 2. Two approaches

**Fix 1** copies the voice prompt's completion rules into the text prompts: agreeing is not completion, verify every item, and send `###TRANSFER###` only once the agent says it *has* transferred you. It covers all of S2, but only probabilistically, and the voice rules have never been measured. The risk is a pushier user who fights correct refusals or coaches the agent with its checklist.

**Fix 2** makes an end token count only on its own: if `###STOP###` or `###TRANSFER###` arrives with other text, the token is stripped and the simulator decides again next turn (at most once in a row). It is ~25 lines in `UserSimulator`, text mode only, and removes S2a and S2b deterministically but not S2c. The extra turn lets the agent make an unconfirmed write or meet a missed `communicate_info` check.

**I recommend Fix 2 first:** it removes the mechanism behind 60 exactly counted failures and is testable offline. Fix 1, the only remedy for S2c, follows. The branch implements both, with offline tests.

## 3. Experiment

**Setup.** I compare five versions ("arms") that differ only in the fix: **A:** the current simulator, as the baseline, **A′:** the baseline run again, to show how much results vary by chance alone, **B:** Fix 1 only, **C:** Fix 2 only, and **D:** both fixes.

Everything else stays the same: one commit, the `gpt-4.1-2025-04-14` simulator at temperature 0, the same seeds, and no LLM cache. The agents are `gpt-4.1` and `gpt-4.1-mini`, which produced 51 of the 60 S2a/S2b failures.

**Tasks:** Performance should improve on the **Target set** (33 tasks where the simulator ended the call too early, each run 8 times) and the **Guard set** (tasks the fixes could break, each run 4 times) should not change. The Guard set should have refusal tasks, transfer tasks the baseline already passes, and 30 random tasks per domain.

**What I measure.** The main result is each target task's pass rate compared with the baseline. To check that the fix worked as intended, messages like "Yes.###STOP###" should disappear in C and D, the agent should use the extra turn after a held-back end token for the action the user just agreed to, and any remaining S2 failures should now be the agent's fault. On the guard set, the pass rate, timeouts and turns after the task is done should stay the same.

**Telling real effects from luck.** Some tasks fail far more than others, so I compare each task with itself in the baseline instead of pooling every run, with error bars from resampling tasks (a bootstrap). An effect counts only if it is larger than the A vs A′ difference. A fix works if the target set clearly improves (the error bar is above zero) or its remaining S2 failures become the agent's fault, and in both cases the guard set changes no more than chance would explain.

## 4. Challenging the conclusion

**Does the simulator behave like a real customer?** Check that the user pursued every request, ended only when finished, invented nothing, and ended the call naturally. **On the premise:** S1a's forgetting might be considered realistic so fixing it is debatable. Such a fix might make the user simulator less realistic. Ex: is "mentions location only if asked" less realistic than immediately mentioning location? S1a is also related to a very specific subset of trajectories (roaming), not to overarching simulator behavior.

**Better simulator, or easier task?** Performance gains should appear only in conversations the old simulator ended too early. The user must give no new hints: "what about my other order?" is fine, naming the item ID is not. Some agents should lose points, e.g. one that says "transferring you" without calling the transfer tool. Strong and weak agents should stay as far apart as before.

**What would change my mind.** If scores don't improve beyond run-to-run noise, or agents rarely complete the action once given the extra turn, S2 doesn't distort results. If agents start giving in on refusal tasks, Fix 1 makes the user pushy, not realistic.

**AI use.** I proposed both fixes, refined the counting rule and S1/S2 taxonomy, and outlined this report. Claude Code implemented the fix and analysis scripts, labelled the sampled conversations under my counting rule, and assembled the report.

---

## Appendix A. Evidence table

| Code | Episode (agent · domain · task/trial) | Real example | Expected | Root cause | Count (method) |
|---|---|---|---|---|---|
| S2a | gpt-4.1-mini · retail · 102/0 | Agent: "Please confirm with a 'yes'" → User: *"Yes. Go ahead. Thanks.###STOP###"*; DB reward 0 | Wait for the write | Token ends the call anywhere in the message; no "agreeing ≠ done" rule in text prompts | 18 (exact; 10 after a re-ask) |
| S2b | gpt-4.1 · telecom · airplane_mode_on\|break_apn_settings\|lock_sim_card_pin/0 | *"Would you like me to transfer you…"* → *"Yes, please transfer me…###TRANSFER###"*; ACTION 0 | Wait for the transfer | "clearly indicated" lets an offer count ([guidelines.py:256](https://github.com/sierra-research/tau2-bench/blob/cc1df47/src/tau2/user/guidelines.py#L256)) | 42 (exact; judgment call: policy neither requires nor forbids asking first) |
| S2c | claude · retail · 104/3; claude · retail · 69/2 | *"Nope, that's everything!"* with the second order untouched; *"I'll reach out again once the status updates"* instead of the scripted fallback | Pursue all items / the fallback | No "verify ALL items" rule in text prompts | ≈24, CI 8–39 (R2 sample 4/20 + R6 read in full 5/25) |
| S1a | claude · telecom · bad_network_preference\|user_abroad_roaming_enabled_off[Hard]/0 vs /3 | Trial 0 opens *"I'm currently in France"* → pass; trial 3 never says it → fail | Consistent across trials | Opening-message sampling noise | 697 (exact); never surfaced 71% (pass 0.04) vs volunteered 26% (0.64); asked → answered 36/38 |
| S1b | o4-mini · retail · 20/0 | Agent: *"I've located your account… provide the order ID"* → *"the order ID is 45789213"* (doesn't exist) | Say it doesn't know | Agent asks for an ID it could look up; simulator invents | 17 (exact; 17/17 after an agent ask) |
| S1c | claude · retail · 71/1 | Agent lists bare order numbers; user picks *"order #W7032009"*, which it was never given, and it's wrong | Describe the order | Simulator guesses instead of describing | ≈16, floor 4 (samples) |
| Excluded | e.g. 19 of 20 sampled R1 failures | Agent proposes the wrong item; user says yes | — | Agent made the first mistake | Not counted against the simulator |

Scripts that reproduce every count: `notes/scripts/` (`sim_attribution.py`, `disclosure.py`, `invented_ids.py`, `sample_for_labels.py`, `dump.py`). Episode-level labels: [simulator priorities, Appendix](simulator-priorities.md#appendix-hand-labels).
