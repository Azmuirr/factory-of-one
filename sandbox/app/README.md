# Tallybird app (sandbox)

A small slice of Tallybird's product code: the onboarding flow, its screens, and its feature flags. Builder changes it through the `code` tools, which work on a copy and run these tests. Nothing here is ever changed in place.

| File | Holds |
|---|---|
| `tallybird/onboarding.py` | The steps a new user walks through. Onboarding v2 (rel_0412) made calendar connect first and removed the skip |
| `tallybird/screens.py` | Each step as HTML, built from the design system in `sandbox/design` |
| `tallybird/flags.py`, `flags.yaml` | Feature flags, modeled on LaunchDarkly. New flags ship off |
| `tests/` | The team's tests. A change must keep them passing and add its own |

Run the tests from this folder: `python -m pytest -q`.
