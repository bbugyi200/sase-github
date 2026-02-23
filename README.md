# sase-github — GitHub VCS Plugin for sase

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/type_checker-mypy-blue.svg)](https://mypy-lang.org/)
[![pytest](https://img.shields.io/badge/tests-pytest-blue.svg)](https://docs.pytest.org/)

## Overview

**sase-github** is a plugin for [sase](https://github.com/bbugyi200/sase) that adds GitHub-specific VCS support. It
provides the `GitHubPlugin` VCS provider for GitHub-hosted repositories, integrating with the `gh` CLI for pull request
creation and management, along with GitHub-specific xprompt workflows.

## Installation

```bash
pip install sase-github
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install sase-github
```

Requires `sase>=0.1.0` as a dependency (installed automatically).

## What's Included

### VCS Provider

- **GitHubPlugin** — GitHub VCS provider that extends `GitCommon` with `gh` CLI integration for PR workflows

### XPrompts

| XPrompt         | Description                                |
| --------------- | ------------------------------------------ |
| `#gh`           | GitHub-specific operations and workflows   |
| `#pr`           | Pull request creation and management       |
| `#new_pr_desc`  | Generate PR descriptions from commit diffs |

## How It Works

sase-github uses Python [entry points](https://packaging.python.org/en/latest/specifications/entry-points/) to register
itself with sase core:

- **`sase_vcs`** — Registers `GitHubPlugin` as the `github` VCS provider
- **`sase_xprompts`** — Makes GitHub xprompts discoverable via plugin discovery

When sase detects a GitHub-hosted repository (via `gh` CLI), it automatically loads `GitHubPlugin` to handle VCS
operations like PR creation, branch management, and commit workflows.

## Requirements

- Python 3.12+
- [sase](https://github.com/bbugyi200/sase) >= 0.1.0
- [gh](https://cli.github.com/) CLI (for GitHub API operations)

## Development

```bash
just install    # Install in editable mode with dev deps
just fmt        # Auto-format code
just lint       # Run ruff + mypy
just test       # Run tests
just check      # All checks (lint + test)
```

## Project Structure

```
src/sase_github/
├── __init__.py        # Package exports
├── plugin.py          # GitHubPlugin implementation
└── xprompts/
    ├── gh.yml         # GitHub operations workflow
    ├── pr.yml         # PR creation workflow
    └── new_pr_desc.yml # PR description generation
```

## License

MIT
