# Project Summary
This is an experiment for running a long horizon task with small language model.

- Use `uv`: `uv sync` and `uv run pytest`
- Never commit secrets or local environment files.

# Python Conventions

- Use four-space indentation, `snake_case` for functions and modules, and `PascalCase` for classes.
- Add type annotations to public interfaces.
- All source codes will be placed under `src` folder, create subfolder where practical.

# Testing

- Use pytest library to create the test
- Place tests under `tests/`, mirroring the source package where practical.

# Git and Reviews

Pull requests should:

- Explain the behavior change.
- Link the relevant requirement or issue.
- List the verification performed.
- Include an API example or screenshot when observable behavior changes.

# Experiment Reports

- For every project experiment report, update `experiment-results/experiment-summary.md` with its findings, conditions, limitations, report link, and run index entries.
