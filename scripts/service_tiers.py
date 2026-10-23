"""
Service classes that are not observed (decision D34).

Some providers sell the same model at the same precision in more than one
service class: a cheaper tier that yields to other traffic and may be queued
or refused when the provider is busy, and a dearer tier that is served first.
Each provider's observation is its lowest-priced endpoint of standard
priority. The tiers that are not observed are listed in panel.json under
"service_tiers", each with the provider, how its tag ends, its class, the
provider's own description, and the first window it applies to. Applying an
entry only from its date keeps every earlier assessment reproducible.

Used by scripts/probe.py, to choose which endpoint to buy, and by
scripts/assess.py, to check what was bought. Standard library only.
"""


def not_observed(tiers, provider, tag, day):
    """The register entry if `tag`, sold by `provider`, is a tier that is not
    observed on `day` (an ISO date, YYYY-MM-DD); otherwise None."""
    if not tag:
        return None
    for entry in (tiers or {}).get("not_observed") or []:
        ending = entry.get("tag_ends_with")
        if (entry.get("provider") == provider and ending and tag.endswith(ending)
                and (not entry.get("from") or (day or "") >= entry["from"])):
            return entry
    return None
