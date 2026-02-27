# Configuring repositories

We currently support the following repository types:

* A pre-existing repository (`PreExistingRepoConfig`)
* A local repository (`LocalRepoConfig`)
* A GitHub repository (`GithubRepoConfig`)

With `autobot run`, you can specify the repository type with the `--env.repo` flag.
For example:

```bash title="From a pre-existing repository"
--env.repo.repo_name="testbed" # (1)!
--env.repo.type=preexisting
```

1. Folder name at the root of the deployment

```bash title="From a local repository"
--env.repo.path=/path/to/repo
--env.repo.type=local
```

All of these classes are defined in `autobot.environment.repo`.

::: autobot.environment.repo.PreExistingRepoConfig
    options:
        show_root_full_path: false
        show_bases: false

::: autobot.environment.repo.LocalRepoConfig
    options:
        show_root_full_path: false
        show_bases: false

::: autobot.environment.repo.GithubRepoConfig
    options:
        show_root_full_path: false
        show_bases: false

::: autobot.environment.repo.repo_from_simplified_input
    options:
        show_root_full_path: false
        show_bases: false
