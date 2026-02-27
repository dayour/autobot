
if [ -z "$(docker images -q autobot/autobot 2> /dev/null)" ]; then
  echo "WARNING: Please wait for the postCreateCommand to start and finish (a new window will appear shortly)"
fi

echo "Here's an example autobot command to try out:"

echo "autobot run \\
  --agent.model.name=claude-sonnet-4-20250514 \\
  --agent.model.per_instance_cost_limit=2.00 \\
  --env.repo.github_url=https://github.com/autobot/test-repo \\
  --problem_statement.github_url=https://github.com/autobot/test-repo/issues/1 \\
"
