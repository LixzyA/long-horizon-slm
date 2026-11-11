# Video narration

## Can small models recover?

This is the story of our long horizon small language model project. Our question is whether a small model can recognize an earlier mistake, recover from it, and continue a task whose steps depend on one another.

## Start with a real task

We started with a research and website assignment. The early agent sessions searched wrong paths, repeated failed commands, and produced incomplete or inconsistent files. In one session, repeated file writes continued through context compaction. These were exploratory runs, so they did not isolate one cause.

## Build a reliable harness

We built a supervisor that copies a workspace into a Docker container, supplies the task, enforces a deadline, and records events and outcomes. Later, the supervisor took ownership of the game state. We also built a local replay viewer. A run marked settled only means the agent stopped; it does not prove the task was solved.

## From profile to Sokoban

We moved to one box Sokoban, where each action has a visible result. Four initial boards were each solved once by our local Qwen model. The baseline run used undo after a bad push. We then designed a harder board called detour, with a shortest known solution of twenty six actions.

## The detour challenge

Detour requires a move that initially pushes the box away from the goal. That makes the task more than simply moving closer. The local pilot used a budget of sixty actions, with blocked moves and undo attempts counting toward that limit.

## Where the local model failed

The first two thinking on detour runs stopped with a length reason before reaching the action limit. Two thinking off runs used all sixty actions without solving. In one, the player looped between two squares and never moved the box. In another, the box reached the top row without a recovery.

## Context is part of the result

The on runs approached the thirty two thousand token context window, and the final response was cut short. We added a separate concise prompt to reduce repeated per action reasoning. Its first thinking on run still ended with a length stop after fifty one actions. One trial cannot establish the effect of the prompt.

## A hosted pilot

We also ran a hosted DeepSeek pilot through OpenRouter. Across eight runs it solved each of the five boards at least once, including detour in twenty six actions. Three attempts stopped before taking an action. The models used different setups, so we cannot make a fair comparison.

## What we can learn

The traces suggest useful targets: notice a bad move, interpret feedback, undo when appropriate, and replan. But our current game shows feedback immediately. It does not yet isolate delayed feedback, and no post training experiment has been completed. The results are a starting point, not evidence of an improvement.

## The next experiment

Next, we need repeated baselines on varied boards, separate conditions for immediate and delayed feedback, and held out evaluation cases. Then we can compare the base model, ordinary successful task fine tuning, and recovery focused training. The goal is a clear test of whether recovery actually improves.
