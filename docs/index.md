---
title: "Getting Started"
---
<style>
  .md-typeset h1,
  .md-content__button {
    display: none;
  }
</style>

<div style="text-align: center;">
    <img class="light-mode-only" src="assets/readme_assets/autobot-banner-light.svg" alt="autobot banner" style="height: 10em;">
    <img class="dark-mode-only" src="assets/readme_assets/autobot-banner-dark.svg" alt="autobot banner" style="height: 10em;">
</div>

autobot enables your language model of choice (e.g. GPT-4o or Claude Sonnet 4) to autonomously use tools to
[fix issues in real GitHub repositories](https://autobot.com/latest/usage/hello_world),
[find cybersecurity vulnerabilities](https://enigma-agent.com/), or
[perform any custom task](https://autobot.com/latest/usage/coding_challenges).

*  **State of the art** on autobot-bench among open-source projects
*  **Free-flowing & generalizable**: Leaves maximal agency to the LM
*  **Configurable & fully documented**: Governed by a single `yaml` file
*  **Made for research**: Simple & hackable by design

autobot is built and maintained by researchers from Princeton University and Stanford University.

<div class="grid cards">
  <a href="installation/" class="nav-card-link">
    <div class="nav-card">
      <div class="nav-card-header">
        <span class="material-icons nav-card-icon">download</span>
        <span class="nav-card-title">Installation</span>
      </div>
      <p class="nav-card-description">Installing autobot.</p>
    </div>
  </a>

  <a href="usage/hello_world/" class="nav-card-link">
    <div class="nav-card">
      <div class="nav-card-header">
        <span class="material-icons nav-card-icon">settings</span>
        <span class="nav-card-title">Hello world</span>
      </div>
      <p class="nav-card-description">Solve a GitHub issue with autobot.</p>
    </div>
  </a>

  <a href="usage/" class="nav-card-link">
    <div class="nav-card">
      <div class="nav-card-header">
        <span class="material-icons nav-card-icon">lightbulb</span>
        <span class="nav-card-title">User guides</span>
      </div>
      <p class="nav-card-description">Dive deeper into autobot's features and goals.</p>
    </div>
  </a>

  <a href="background/" class="nav-card-link">
    <div class="nav-card">
      <div class="nav-card-header">
        <span class="material-icons nav-card-icon">book</span>
        <span class="nav-card-title">Background & goals</span>
      </div>
      <p class="nav-card-description">Learn more about the project goals and academic research.</p>
    </div>
  </a>
</div>
## News

* July 24: [Mini-autobot](https://github.com/autobot/mini-autobot) achieves 65% on autobot-bench verified in 100 lines of python!
* July 9: [Multimodal support for autobot](usage/multimodal.md) - Process images from GitHub issues with vision-capable AI models
* May 2: [autobot-LM-32b](https://swesmith.com) achieves open-weights SOTA on autobot-bench
* Feb 28: [autobot 1.0 + Claude 3.7 is SoTA on autobot-bench full](https://x.com/KLieret/status/1895487966409298067)
* Feb 25: [autobot 1.0 + Claude 3.7 is SoTA on autobot-bench verified](https://x.com/KLieret/status/1894408819670733158)
* Feb 13: [Releasing autobot 1.0: SoTA on autobot-bench light & tons of new features](https://x.com/KLieret/status/1890048205448220849)
* Dec 7: [An interview with the autobot & autobot-bench team](https://www.youtube.com/watch?v=fcr8WzeEXyk)

## Doc updates

* June 26: [Adding custom tools](usage/adding_custom_tools.md)
* Apr 8: [Running autobot competitively](usage/competitive_runs.md)
* Mar 7: [Updated autobot architecture diagram of 1.0](background/architecture.md)