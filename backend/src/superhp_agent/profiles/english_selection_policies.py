"""Optional series-specific additions to the English annotation prompt.

Most English novels should use the shared profile without an extra policy.
Only add an entry here when a series has stable terminology or selection
boundaries that the generic annotation task cannot express clearly enough.
"""

HARRY_POTTER_SELECTION_POLICY = """
You have particular familiarity with the Harry Potter series.

- Treat spells, magical objects, creatures, institutions, titles, and wizarding-world expressions as domain vocabulary.
- Do not select a term solely because it is magical, fictional, or capitalized.
- For a selected term, prefer its widely established Chinese rendering when one exists.
- Ordinary character names such as Harry, Ron, Hermione, Dumbledore, and Hagrid are not annotation targets.
""".strip()


_SELECTION_POLICIES = {
    "harry_potter": HARRY_POTTER_SELECTION_POLICY,
}


def get_english_selection_policy(policy_id: str) -> str:
    """Return one configured prompt addition and reject unknown ids."""
    try:
        return _SELECTION_POLICIES[policy_id]
    except KeyError as exc:
        raise ValueError(f"Unknown English selection policy: {policy_id}") from exc
