"""Intent-diff — the L1 capstone (plan §8 shadow regression).

Compare the *order intents* of two strategy versions or runs from the journal —
e.g. version N+1 running in **shadow** (nothing transmitted) beside version N
**live** — before promoting N+1. Each intent is an accepted order
(sym/side/qty/price). Orders are cid'd ``<tag>-<seq>`` and tags are version-scoped
(``<name>.<ver>``, run.py), so aligning by ``seq`` compares the two versions
decision-for-decision: same input → same n-th decision, or a flagged divergence.
"""
from __future__ import annotations

from typing import Any


def _tag(cid: str) -> str:
    return cid.rsplit("-", 1)[0] if "-" in cid else cid


def _seq(cid: str) -> str:
    return cid.rsplit("-", 1)[-1] if "-" in cid else ""


def _shape(i: dict[str, Any]) -> tuple:
    return (i.get("sym"), i.get("side"), i.get("qty"), i.get("price"))


def intent_diff(events: list[dict[str, Any]], tag_a: str, tag_b: str) -> dict[str, Any]:
    """Diff two tags' order intents from a journal event list. Returns matched count,
    the divergences (same seq, different order), and intents unique to each side."""
    def intents(tag: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for e in events:
            cid = str(e.get("cid") or "")
            if e.get("status") == "accepted" and _tag(cid) == tag:
                out[_seq(cid)] = {"cid": cid, "sym": e.get("sym"), "side": e.get("side"),
                                  "qty": e.get("qty"), "price": e.get("price"),
                                  "ts": e.get("ts")}
        return out

    a, b = intents(tag_a), intents(tag_b)
    common: list[str] = []
    differing: list[dict[str, Any]] = []
    for seq in sorted(set(a) & set(b), key=lambda s: (len(s), s)):
        if _shape(a[seq]) == _shape(b[seq]):
            common.append(seq)
        else:
            differing.append({"seq": seq, "a": a[seq], "b": b[seq]})
    a_only = [a[s] for s in a if s not in b]
    b_only = [b[s] for s in b if s not in a]
    return {
        "tag_a": tag_a, "tag_b": tag_b,
        "matched": len(common),
        "differing": differing,
        "a_only": a_only,
        "b_only": b_only,
        "identical": not differing and not a_only and not b_only,
    }
