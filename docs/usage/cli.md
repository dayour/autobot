# autobot command line interface

All functionality of autobot is available via the command line interface via the `autobot` command.

You can run `autobot --help` to see all subcommands.

## Running autobot

* `autobot run`: Run autobot on a single issue ([tutorial](hello_world.md)).
* `autobot run-batch`: Run autobot on a batch of issues ([tutorial](batch_mode.md)).
* `autobot run-replay`: Replay a trajectory file or a demo file. This means that you take all actions from the trajectory and execute them again in the environment. Useful for debugging your [tools](../config/tools.md) or for building new [demonstrations](../config/demonstrations.md).

## Inspecting runs

* `autobot inspect` or `autobot i`: Open the command line inspector ([more information](inspector.md)).
* `autobot inspector` or `autobot I`: Open the web-based inspector ([more information](inspector.md)).
* `autobot quick-stats` or `autobot qs`: When executed in a directory with trajectories, displays a summary of `exit_status` and more

## Advanced scripts

* `autobot merge-preds`: Merge multiple prediction files into a single file.
* `autobot traj-to-demo`: Convert a trajectory file to an easy to edit demo file ([more information on demonstrations](../config/demonstrations.md)).
* `autobot remove-unfinished`: Remove unfinished trajectories
