"""GitHub runner provider — manages workspace lifecycle for GitHub-based agent runs.

Migrates logic from ``xprompts/gh.yml`` + ``sase_github.scripts.gh_setup`` into
the :class:`RunnerProvider` protocol so it can be invoked via ``%gh:org/repo``
directives.
"""

import logging
import os

from sase.runner_provider import PostAgentResult, RunnerContext, RunnerProvider
from sase.runner_providers.git import (
    _capture_git_diff,
    _prepare_git_workspace,
    _run_git,
)
from sase.running_field import (
    claim_workspace,
    get_first_available_axe_workspace,
    release_workspace,
)
from sase.workspace_provider import resolve_ref
from sase.workspace_utils import ensure_git_clone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def allocate_gh_workspace(
    ref: str,
    *,
    n: int | None = None,
    release: bool = True,
) -> RunnerContext:
    """Resolve *ref*, claim a workspace, and return a populated context.

    This is the shared allocation logic extracted from
    :func:`sase_github.scripts.gh_setup.main`.
    """
    resolved = resolve_ref(ref, "gh")

    project_name = resolved.project_name
    project_file = resolved.project_file

    # Check if workspace was pre-allocated by the TUI
    if os.environ.get("SASE_GH_PRE_ALLOCATED") == "1":
        workspace_num = int(os.environ["SASE_GH_WORKSPACE_NUM"])
        workspace_dir = os.environ["SASE_GH_WORKSPACE_DIR"]
    elif n is not None:
        workspace_num = n
        workspace_dir = ensure_git_clone(resolved.primary_workspace_dir, workspace_num)
    else:
        workspace_num = get_first_available_axe_workspace(project_file)
        workspace_dir = ensure_git_clone(resolved.primary_workspace_dir, workspace_num)

    pid = os.getpid()
    workflow_name = f"gh-{ref}"
    claim_workspace(
        project_file,
        workspace_num,
        workflow_name,
        pid,
        None,
        pinned=not release,
    )

    return RunnerContext(
        project_name=project_name,
        project_file=project_file,
        workspace_dir=workspace_dir,
        workspace_num=workspace_num,
        checkout_target=resolved.checkout_target,
        primary_workspace_dir=resolved.primary_workspace_dir,
        should_release=release,
    )


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------


class GitHubRunnerProvider(RunnerProvider):
    """Runner provider for GitHub workspaces."""

    @property
    def name(self) -> str:
        return "gh"

    def pre_agent(
        self,
        ref: str,
        *,
        n: int | None = None,
        release: bool = True,
    ) -> RunnerContext:
        ctx = allocate_gh_workspace(ref, n=n, release=release)
        head_before = _prepare_git_workspace(ctx.workspace_dir)
        ctx.head_before = head_before
        os.chdir(ctx.workspace_dir)
        return ctx

    def post_agent(self, ctx: RunnerContext) -> PostAgentResult:
        if ctx.should_release:
            workflow_name = f"gh-{ctx.checkout_target}"
            cl_name = (
                ctx.checkout_target if "/" not in ctx.checkout_target else None
            )
            release_workspace(
                ctx.project_file,
                ctx.workspace_num,
                workflow_name,
                cl_name,
            )

        diff_path = _capture_git_diff(ctx.workspace_dir, ctx.head_before)

        meta: dict[str, str] = {"meta_workspace": str(ctx.workspace_num)}

        # Capture commit message when commits were made (matches gh.yml diff step)
        if ctx.head_before:
            head_now = _run_git(
                ["rev-parse", "HEAD"], cwd=ctx.workspace_dir, check=True
            ).stdout.strip()
            if head_now != ctx.head_before:
                commit_msg = _run_git(
                    ["log", "-1", "--format=%s", "HEAD"],
                    cwd=ctx.workspace_dir,
                    check=True,
                ).stdout.strip()
                if commit_msg:
                    meta["meta_commit_message"] = commit_msg

        return PostAgentResult(
            diff_path=diff_path,
            meta=meta,
        )
