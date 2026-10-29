# Project Description
This is an experiment for running a long horizon task with SLM.

# Environment and tool use

The working directory is `C:\Project\long-horizon-slm` on Windows. Pi's bash tool uses Git Bash, not Linux. Use paths relative to the working directory, such as `input/andrej.md`; in Git Bash the project is `/c/Project/long-horizon-slm`. Do not search `/`, other drives, or unrelated directories. The seed file can be read directly; do not search for it.

Use tools already available. Do not run `apt-get`, `apt-cache`, or other Linux package managers, and do not install software. If a command fails, inspect its output and do not repeat the same command unchanged. If you cannot access a required tool, source, or the internet, record the limitation and continue only with work that does not depend on it. If blocked, stop and report the blocker. Avoid piping commands through tools that can hide their failure status.

# Python cli
To run Python commands on Git Bash use `py` and `python` instead of `py3` and `python3`. For example:

`py main.py`
`py --version`
`python src/main.py`
`python utils/util.py`

# Run output

At the start of each new Pi session, before creating deliverables:

1. Read `.run-version` in the project root as an integer.
2. Add 1 to that integer. Call the result the run number.
3. Set the run directory to `output/run-version-<run number>`.
4. If that directory already exists, stop and report the conflict.
   Do not overwrite an existing run.
5. Create the run directory, then replace the value in `.run-version`
   with the new run number.
6. Save every deliverable for this session inside that run directory.
   Do not write deliverables directly into `output/`.

If the counter cannot be read, is not an integer, or cannot be updated,
stop and report the problem. Reuse the same run directory for the rest
of this session; do not increment the counter for each file or message.