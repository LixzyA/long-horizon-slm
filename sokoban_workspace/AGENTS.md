# Environment and tool use

The working directory is this Sokoban workspace. Use relative paths and the Python command available in your environment. Do not install software or change the game program. Inspect an error before trying again.

# Run output

At the start of each new Pi session, before creating deliverables:

1. Read `.run-version` in the workspace root as an integer.
2. Add 1 to that integer. Call the result the run number.
3. Set the run directory to `output/run-version-<run number>`.
4. If that directory already exists, stop and report the conflict. Do not overwrite an existing run.
5. Create the run directory, then replace the value in `.run-version` with the new run number.
6. Save the game state and report in that run directory. Reuse the same directory for the entire session.

If the counter cannot be read, is not an integer, or cannot be updated, stop and report the problem.
