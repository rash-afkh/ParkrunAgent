"""The interactive ReAct agent (DESIGN.md §7b).

A tool-calling agent over the deterministic core. The LLM only chooses tools and
writes prose; every fact comes from a tool. Built with LangGraph's prebuilt
ReAct agent and langchain-anthropic (the user's stack is LangChain).

Model defaults to claude-opus-5-5; override with PARKRUN_LLM_MODEL (e.g.
claude-haiku-5-5 is far cheaper for experimenting).
"""

from __future__ import annotations

import os

from parkrun_agent.agent.context import AgentContext, build_context
from parkrun_agent.agent.tools import build_tools

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = (
    "You are ParkrunAgent, a friendly assistant that helps {name} (parkrun athlete "
    "A{athlete_id}) decide where to run their next parkrun. Their profile and home "
    "location are already configured — never ask for them.\n\n"
    "Always use the tools for facts. Never invent parkrun events, distances, or "
    "challenge progress — if you need that information, call a tool. When the user "
    "mentions travelling somewhere, call recommend_near with that place. For general "
    "'where should I run next' questions, call recommend_from_home. For 'how am I "
    "doing' questions, call challenge_progress.\n\n"
    "Be concise and encouraging. When you suggest an event, say which challenge it "
    "advances and why it's worth it."
)


def build_model(model: str | None = None):
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model or os.environ.get("PARKRUN_LLM_MODEL", DEFAULT_MODEL),
        max_tokens=2048,
    )


def build_agent(config_path: str, model: str | None = None):
    """Return (compiled_agent, context). Requires Anthropic credentials in the
    environment (ANTHROPIC_API_KEY) at invoke time."""
    from langgraph.prebuilt import create_react_agent

    ctx: AgentContext = build_context(config_path)
    prompt = SYSTEM_PROMPT.format(
        name=ctx.athlete.name or "the athlete", athlete_id=ctx.athlete.id
    )
    agent = create_react_agent(build_model(model), build_tools(ctx), prompt=prompt)
    return agent, ctx


def ask(config_path: str, question: str, model: str | None = None) -> str:
    agent, _ctx = build_agent(config_path, model)
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    final = result["messages"][-1]
    return final.content if isinstance(final.content, str) else str(final.content)
