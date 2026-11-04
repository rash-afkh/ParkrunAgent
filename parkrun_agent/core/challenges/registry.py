"""Build challenges from user config (the 'add your own' story, DESIGN.md §5).

A custom challenge is a dict (loaded from YAML), e.g.:

    key: home_counties
    name: Home Counties Tour
    type: token_collection
    token: first_letter          # or 'compass'
    targets: [Surrey, Kent, Essex]
    description: optional text

Anything not expressible as a token collection is added as a Python subclass of
Challenge and registered here.
"""

from __future__ import annotations

from parkrun_agent.core.challenges.base import (
    Challenge,
    TokenCollectionChallenge,
    compass_words,
    initial_letter,
)

# Named token functions available to YAML-defined challenges.
TOKEN_FNS = {
    "first_letter": initial_letter,
    "compass": compass_words,
}


def build_challenge_from_config(cfg: dict) -> Challenge:
    ctype = cfg.get("type", "token_collection")
    if ctype == "token_collection":
        token_name = cfg.get("token", "first_letter")
        if token_name not in TOKEN_FNS:
            raise ValueError(f"Unknown token function {token_name!r} (have {list(TOKEN_FNS)}).")
        return TokenCollectionChallenge(
            key=cfg["key"],
            name=cfg.get("name", cfg["key"]),
            description=cfg.get("description", ""),
            targets=cfg["targets"],
            token_fn=TOKEN_FNS[token_name],
        )
    raise ValueError(f"Unknown challenge type {ctype!r}.")
