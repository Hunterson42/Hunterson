"""
The register of provider groups, Rule 10 (decision D29).

Providers that resell inference served by another listed provider or by a
common network, or that are under common control, count as one provider. The
groups are kept in affiliations.json at the repository root, each with its
evidence and the day it applies from, and are read by the tracker
(scripts/track.py) for the qualifying counts and by the assessor
(scripts/assess.py) for the contributors and the price.

A group applies from its "from" day, which must be later than the day it was
recorded, so a group never changes a day already counted. Uses only the Python
standard library.
"""
import datetime
import json
import os

PATH = "affiliations.json"


def _day(text, what):
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"affiliations.json: {what} is not a date in the form YYYY-MM-DD: {text!r}")


def load(path=PATH):
    """The groups, checked. A missing file means no groups."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        groups = json.load(f).get("groups") or []
    for g in groups:
        name = g.get("name") or "?"
        members = g.get("members") or []
        if len(set(members)) < 2:
            raise ValueError(f"affiliations.json: group {name} needs at least two members")
        if not g.get("evidence"):
            raise ValueError(f"affiliations.json: group {name} has no evidence")
        recorded = _day(g.get("recorded"), f"group {name}, recorded")
        start = _day(g.get("from"), f"group {name}, from")
        if start <= recorded:
            raise ValueError(f"affiliations.json: group {name} must apply from a day after it was recorded")
        if g.get("until") is not None and _day(g["until"], f"group {name}, until") <= start:
            raise ValueError(f"affiliations.json: group {name} ends before it starts")
    return groups


def active(groups, day):
    """The groups that apply on a day, given as YYYY-MM-DD."""
    return [g for g in groups if g["from"] <= day and (g.get("until") is None or day < g["until"])]


def group_of(groups, day):
    """Provider name -> group name, for every provider in a group that applies on the day."""
    out = {}
    for g in active(groups, day):
        for m in g["members"]:
            if m in out and out[m] != g["name"]:
                raise ValueError(f"affiliations.json: {m} is in two groups on {day}")
            out[m] = g["name"]
    return out


def canonical(name, mapping):
    """The name a provider counts under: its group's, or its own."""
    return mapping.get(name, name)
