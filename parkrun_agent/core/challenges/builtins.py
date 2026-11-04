"""Built-in challenges shipped with the app.

These mirror the parkrun app's default challenges. Each is a zero-arg builder so
the registry/config layer can instantiate only the ones a user enables.
"""

from __future__ import annotations

import string

from parkrun_agent.core.challenges.base import (
    TokenCollectionChallenge,
    compass_words,
    initial_letter,
)

# The official Alphabeteer excludes X (no parkrun starts with X), giving 25 letters.
ALPHABET_TARGETS = [c for c in string.ascii_uppercase if c != "X"]


def alphabeteer() -> TokenCollectionChallenge:
    return TokenCollectionChallenge(
        key="alphabeteer",
        name="Alphabeteer (A–Z)",
        description="Run at events whose names start with each letter A–Z (excluding X).",
        targets=ALPHABET_TARGETS,
        token_fn=initial_letter,
    )


def pirates() -> TokenCollectionChallenge:
    return TokenCollectionChallenge(
        key="pirates",
        name="Pirates",
        description="Run at events starting with each of P, I, R, A, T, E, S.",
        targets=list("PIRATES"),
        token_fn=initial_letter,
    )


def compass() -> TokenCollectionChallenge:
    return TokenCollectionChallenge(
        key="compass",
        name="Compass Club",
        description="Run at events whose names contain North, South, East and West.",
        targets=["NORTH", "SOUTH", "EAST", "WEST"],
        token_fn=compass_words,
    )


# key -> builder. The registry and config loader use this.
BUILTIN_BUILDERS = {
    "alphabeteer": alphabeteer,
    "pirates": pirates,
    "compass": compass,
}


def build_default_challenges() -> list[TokenCollectionChallenge]:
    return [builder() for builder in BUILTIN_BUILDERS.values()]
