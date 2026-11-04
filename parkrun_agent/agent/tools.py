"""LangChain tools — thin wrappers over the deterministic core.

The LLM decides *which* tool to call; the tools do all the real work (geo,
challenge logic, scoring). They close over an AgentContext so the model never
has to pass the athlete id or home around. Returning readable strings keeps the
agent prompt simple.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from parkrun_agent.agent.context import AgentContext
from parkrun_agent.describe import athlete_summary
from parkrun_agent.formatting import format_progress, format_recommendations


def build_tools(ctx: AgentContext) -> list[BaseTool]:
    @tool
    def profile_summary() -> str:
        """Summarise the athlete's parkrun history: total runs, distinct events,
        countries, years active, most-visited event, PBs, farthest-apart events,
        and club badges. Use for 'describe me' / 'my parkrun history' questions."""
        return athlete_summary(ctx.athlete, ctx.catalogue)

    @tool
    def challenge_progress() -> str:
        """Report the athlete's progress on every active challenge (alphabet,
        pirates, compass, Wilson Index, etc.). Use for 'how am I doing' questions."""
        return format_progress([c.progress(ctx.athlete) for c in ctx.challenges])

    @tool
    def recommend_from_home() -> str:
        """Recommend where to run next from the athlete's configured home, as
        local / stretch / destination tiers. Use for general 'where should I run
        next' questions when no travel location is mentioned."""
        recs = ctx.service.recommend(ctx.athlete, ctx.challenges, ctx.home, ctx.params)
        return format_recommendations(recs, travel=False)

    @tool
    def recommend_near(place: str) -> str:
        """Recommend parkruns near a place the athlete is travelling to, e.g.
        'Vilnius' or 'Edinburgh'. Geocodes the place, then ranks nearby events by
        how much they advance the athlete's challenges and whether they're new."""
        hit = ctx.geocoder.geocode(place)
        if hit is None:
            return f"Could not find a location called {place!r}."
        point, label = hit
        recs = ctx.service.recommend(
            ctx.athlete, ctx.challenges, point, ctx.params, travel=True
        )
        header = f"Near {label} ({point.lat:.3f}, {point.lon:.3f}):\n"
        return header + format_recommendations(recs, travel=True)

    return [profile_summary, challenge_progress, recommend_from_home, recommend_near]
