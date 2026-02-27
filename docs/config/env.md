# Environment variables

This page details all environment variables that are currently in use by autobot.

* All API keys (for LMs and GitHub) can be set as an environment variable. See [here](../installation/keys.md) for more information.
* `autobot_CONFIG_ROOT`: Used to resolve relative paths in the [config](config.md). E.g., if `autobot_CONFIG_ROOT=/a/b/c` and you set
  add a tool bundle as `tools/my_bundle`, it will be resolved to `/a/b/c/tools/my_bundle`. The default of `autobot_CONFIG_ROOT` is the
  the `autobot` package directory.

The following variables can only be set as environment variables, not in the config file.

If you install `autobot` without the `--editable` option, please make sure to set

* `autobot_CONFIG_DIR` (default `<PACKAGE>/config`)
* `autobot_TOOLS_DIR` (default `<PACKAGE>/tools`)
* `autobot_TRAJECTORY_DIR` (default `<PACKAGE>/trajectories`)

In addition, the following env variables allow to configure the logging.

* `autobot_LOG_TIME`: Add timestamps to log
* `autobot_LOG_STREAM_LEVEL`: Level of logging that is shown on the command line interface (`TRACE` being a custom level below `DEBUG`). Will have no effect for `run-batch`.

!!! hint "Persisting environment variables"
    Most environment variables can also be added to `.env` instead.