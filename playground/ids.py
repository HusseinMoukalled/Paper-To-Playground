"""Stable identifier prefixes shared across pipeline contracts.

Use source IDs such as ``SRC-000001``, evidence IDs such as ``E001``, and
the type-specific IR prefixes below. Once assigned, an ID is not rewritten
when a contract crosses a package boundary.
"""

SOURCE_ELEMENT_ID_PREFIX = "SRC-"
EVIDENCE_ID_PREFIX = "E"

IR_ID_PREFIXES = {
    "variable": "var-",
    "equation": "eq-",
    "relationship": "rel-",
    "mechanism_step": "step-",
    "control": "control-",
    "exploration": "explore-",
    "computation": "compute-",
    "visual": "visual-",
    "grounding_claim": "claim-",
}
