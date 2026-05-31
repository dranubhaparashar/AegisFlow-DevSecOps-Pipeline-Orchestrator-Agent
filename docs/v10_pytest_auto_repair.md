# v10 Pytest Auto-Repair

AegisFlow v10 adds a smart safe correction loop for Pytest failures.

When Pytest fails, AegisFlow can:

- clean `__pycache__`, `.pytest_cache`, `.coverage`, and `*.pyc` files;
- remove generated tests for `__init__.py`;
- rename nested generated test files to globally unique names;
- rerun Pytest once and report the result.

It does not modify source/business code.
