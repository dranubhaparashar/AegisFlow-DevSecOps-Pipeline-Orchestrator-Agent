# v4 Correction and Test Generation Design

AegisFlow AI v4 adds corrective workflow actions:

1. Install missing validation tools into the active Python/Conda environment.
2. Run safe Ruff auto-format and auto-fix commands.
3. Generate starter pytest files for selected source files.
4. Generate starter pytest files for all Python source files.
5. Re-run validations and show updated evidence.

The generated tests are intentionally safe starter tests. They verify import/load behavior and skip optional dependency problems instead of creating false failures. Business-specific assertions should be added by developers after review.
