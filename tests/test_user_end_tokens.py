"""Text-mode end tokens: a STOP/TRANSFER sent with other text is deferred once."""

import pytest

from tau2.agent.llm_agent import LLMAgent
from tau2.data_model.message import AssistantMessage, ToolCall
from tau2.data_model.simulation import TerminationReason
from tau2.domains.mock.environment import get_environment, get_tasks
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.user import guidelines
from tau2.user.user_simulator import UserSimulator

AGENT = AssistantMessage(role="assistant", content="Shall I go ahead?")


def _script_user(monkeypatch, *replies):
    """Make the simulator's LLM return the given texts in order."""
    it = iter(replies)
    monkeypatch.setattr(
        "tau2.user.user_simulator.generate",
        lambda **kwargs: AssistantMessage(role="assistant", content=next(it), cost=0),
    )


class _VoiceModeUser(UserSimulator):
    simulation_mode = "voice"


def _run(monkeypatch, *replies, cls=UserSimulator):
    _script_user(monkeypatch, *replies)
    user = cls(llm="test", instructions="Be a customer.")
    state = user.get_init_state()
    out = []
    for _ in replies:
        msg, state = user.generate_next_message(AGENT, state)
        out.append((msg.content, UserSimulator.is_stop(msg)))
    return out


@pytest.mark.parametrize("token", ["###STOP###", "###TRANSFER###"])
def test_bare_token_ends_the_call(monkeypatch, token):
    assert _run(monkeypatch, f"  {token}\n") == [(f"  {token}\n", True)]


@pytest.mark.parametrize("token", ["###STOP###", "###TRANSFER###"])
def test_token_with_text_is_stripped(monkeypatch, token):
    assert _run(monkeypatch, f"Yes, go ahead.{token}") == [("Yes, go ahead.", False)]


def test_deferred_only_once_in_a_row(monkeypatch):
    assert _run(monkeypatch, "Yes.###STOP###", "Thanks, bye!###STOP###") == [
        ("Yes.", False),
        ("Thanks, bye!###STOP###", True),
    ]


def test_deferral_resets_after_a_plain_message(monkeypatch):
    out = _run(monkeypatch, "Yes.###STOP###", "Is it done?", "Great.###STOP###")
    assert out == [("Yes.", False), ("Is it done?", False), ("Great.", False)]


def test_out_of_scope_is_not_deferred(monkeypatch):
    text = "I don't have that information.###OUT-OF-SCOPE###"
    assert _run(monkeypatch, text) == [(text, True)]


def test_voice_mode_is_not_deferred(monkeypatch):
    out = _run(monkeypatch, "Yes.###STOP###", cls=_VoiceModeUser)
    assert out == [("Yes.###STOP###", True)]


def test_agent_acts_on_a_yes_before_the_call_ends(monkeypatch):
    """The S2a pattern: "Yes.###STOP###" used to end the call before the write."""
    task = get_tasks()[0]
    environment = get_environment()
    agent = LLMAgent(
        tools=environment.get_tools(),
        domain_policy=environment.get_policy(),
        llm="test",
    )
    write = AssistantMessage(
        role="assistant",
        tool_calls=[
            ToolCall(
                id="w",
                name="create_task",
                arguments={"user_id": "user_1", "title": "Groceries"},
                requestor="assistant",
            )
        ],
    )
    turns = iter([AGENT, write, AssistantMessage(role="assistant", content="Done.")])
    monkeypatch.setattr(agent, "_generate_next_message", lambda m, s: next(turns))
    _script_user(monkeypatch, "Create a task please.", "Yes.###STOP###", "###STOP###")
    user = UserSimulator(llm="test", instructions="Be a customer.")

    result = Orchestrator(
        domain="mock",
        agent=agent,
        user=user,
        environment=environment,
        task=task,
        max_steps=20,
    ).run()

    assert result.termination_reason == TerminationReason.USER_STOP
    tool_results = [m for m in result.messages if m.role == "tool"]
    assert [m.id for m in tool_results] == ["w"]
    assert not tool_results[0].error


@pytest.mark.parametrize("use_tools", [False, True])
def test_text_guidelines_have_completion_rules(use_tools):
    text = guidelines.simulation_guidelines(
        UserSimulator(llm="test").persona_config, mode="text", use_tools=use_tools
    )
    assert "Agreeing to an action is not the same as the action being completed" in text
    assert "verify that ALL items in your scenario instructions" in text
    assert "not when it offers or asks whether to transfer you" in text
    assert "tokens on their own, as a message with no other text" in text
