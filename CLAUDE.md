# Documentation standard

Every Python class and public method must have a docstring:

- **Module level** — what this module does, usage snippet, which `settings` fields it reads.
- **Class level** — purpose, key design decisions, lifecycle notes.
- **Method level** — one-line summary, then `Args:`, `Returns:`, and `Raises:` sections where applicable.

Use Google-style docstrings throughout.

# Test documentation standard

Every test function must have a one-line docstring describing what behaviour it verifies.
Write it as a plain statement, not a repetition of the function name — focus on the expected outcome.
