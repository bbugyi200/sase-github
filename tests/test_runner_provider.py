"""Tests for the GitHubRunnerProvider."""

import subprocess
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from sase.runner_provider import RunnerContext
from sase_github.runner_provider import (
    GitHubRunnerProvider,
    allocate_gh_workspace,
)


@dataclass
class _FakeResolved:
    project_name: str = "org/myrepo"
    project_file: str = "/home/user/.sase/projects/org-myrepo/org-myrepo.gp"
    primary_workspace_dir: str = "/home/user/projects/org-myrepo"
    bare_repo_dir: str = "/home/user/.sase/bare/org-myrepo.git"
    checkout_target: str = "main"


# ---------------------------------------------------------------------------
# allocate_gh_workspace tests
# ---------------------------------------------------------------------------


_GH_MOD = "sase_github.runner_provider"


class TestAllocateGhWorkspace:
    """Tests for the allocate_gh_workspace() helper."""

    @patch(f"{_GH_MOD}.claim_workspace")
    @patch(f"{_GH_MOD}.get_first_available_axe_workspace", return_value=101)
    @patch(
        f"{_GH_MOD}.ensure_git_clone",
        return_value="/home/user/projects/org-myrepo__101",
    )
    @patch(f"{_GH_MOD}.resolve_ref", return_value=_FakeResolved())
    def test_auto_allocate(
        self,
        mock_resolve: MagicMock,
        mock_clone: MagicMock,
        mock_avail: MagicMock,
        mock_claim: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SASE_GH_PRE_ALLOCATED", raising=False)
        ctx = allocate_gh_workspace("org/myrepo")

        mock_resolve.assert_called_once_with("org/myrepo", "gh")
        mock_avail.assert_called_once_with(
            "/home/user/.sase/projects/org-myrepo/org-myrepo.gp"
        )
        mock_clone.assert_called_once_with("/home/user/projects/org-myrepo", 101)
        mock_claim.assert_called_once()

        assert ctx.project_name == "org/myrepo"
        assert ctx.workspace_num == 101
        assert ctx.workspace_dir == "/home/user/projects/org-myrepo__101"
        assert ctx.should_release is True

    @patch(f"{_GH_MOD}.claim_workspace")
    @patch(
        f"{_GH_MOD}.ensure_git_clone",
        return_value="/home/user/projects/org-myrepo__5",
    )
    @patch(f"{_GH_MOD}.resolve_ref", return_value=_FakeResolved())
    def test_explicit_n(
        self,
        mock_resolve: MagicMock,
        mock_clone: MagicMock,
        mock_claim: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SASE_GH_PRE_ALLOCATED", raising=False)
        ctx = allocate_gh_workspace("org/myrepo", n=5)

        mock_clone.assert_called_once_with("/home/user/projects/org-myrepo", 5)
        assert ctx.workspace_num == 5

    @patch(f"{_GH_MOD}.claim_workspace")
    @patch(f"{_GH_MOD}.resolve_ref", return_value=_FakeResolved())
    def test_pre_allocated_env(
        self,
        mock_resolve: MagicMock,
        mock_claim: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SASE_GH_PRE_ALLOCATED", "1")
        monkeypatch.setenv("SASE_GH_WORKSPACE_NUM", "42")
        monkeypatch.setenv("SASE_GH_WORKSPACE_DIR", "/tmp/ws42")

        ctx = allocate_gh_workspace("org/myrepo")

        assert ctx.workspace_num == 42
        assert ctx.workspace_dir == "/tmp/ws42"


# ---------------------------------------------------------------------------
# GitHubRunnerProvider lifecycle tests
# ---------------------------------------------------------------------------


def _make_completed(
    stdout: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=""
    )


class TestGitHubRunnerProvider:
    """Tests for the GitHubRunnerProvider class."""

    def test_name(self) -> None:
        assert GitHubRunnerProvider().name == "gh"

    @patch(f"{_GH_MOD}.os.chdir")
    @patch(f"{_GH_MOD}._prepare_git_workspace", return_value="abc123")
    @patch(f"{_GH_MOD}.allocate_gh_workspace")
    def test_pre_agent(
        self,
        mock_alloc: MagicMock,
        mock_prepare: MagicMock,
        mock_chdir: MagicMock,
    ) -> None:
        mock_alloc.return_value = RunnerContext(
            project_name="org/repo",
            workspace_dir="/tmp/ws",
            workspace_num=101,
        )

        provider = GitHubRunnerProvider()
        ctx = provider.pre_agent("org/repo", n=5, release=False)

        mock_alloc.assert_called_once_with("org/repo", n=5, release=False)
        mock_prepare.assert_called_once_with("/tmp/ws")
        mock_chdir.assert_called_once_with("/tmp/ws")
        assert ctx.head_before == "abc123"

    @patch(f"{_GH_MOD}._run_git")
    @patch(f"{_GH_MOD}._capture_git_diff", return_value="/tmp/diff.patch")
    @patch(f"{_GH_MOD}.release_workspace")
    def test_post_agent_with_release(
        self,
        mock_release: MagicMock,
        mock_diff: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        # head_now != head_before → commits were made
        mock_git.side_effect = [
            _make_completed(stdout="new-head\n"),  # rev-parse HEAD
            _make_completed(stdout="feat: add widget\n"),  # git log -1
        ]

        ctx = RunnerContext(
            project_file="/path/to/proj.gp",
            workspace_dir="/tmp/ws",
            workspace_num=101,
            checkout_target="myrepo",
            should_release=True,
            head_before="abc123",
        )

        provider = GitHubRunnerProvider()
        result = provider.post_agent(ctx)

        # cl_name = "myrepo" (no "/" in checkout_target)
        mock_release.assert_called_once_with(
            "/path/to/proj.gp", 101, "gh-myrepo", "myrepo"
        )
        mock_diff.assert_called_once_with("/tmp/ws", "abc123")
        assert result.diff_path == "/tmp/diff.patch"
        assert result.meta["meta_workspace"] == "101"
        assert result.meta["meta_commit_message"] == "feat: add widget"

    @patch(f"{_GH_MOD}._run_git")
    @patch(f"{_GH_MOD}._capture_git_diff", return_value="/tmp/diff.patch")
    @patch(f"{_GH_MOD}.release_workspace")
    def test_post_agent_with_release_org_slash_repo(
        self,
        mock_release: MagicMock,
        mock_diff: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        # checkout_target has "/" → cl_name should be None
        mock_git.side_effect = [
            _make_completed(stdout="same-head\n"),  # rev-parse HEAD (no commits)
        ]

        ctx = RunnerContext(
            project_file="/path/to/proj.gp",
            workspace_dir="/tmp/ws",
            workspace_num=101,
            checkout_target="org/repo",
            should_release=True,
            head_before="same-head",
        )

        provider = GitHubRunnerProvider()
        result = provider.post_agent(ctx)

        # cl_name = None because "/" in checkout_target
        mock_release.assert_called_once_with(
            "/path/to/proj.gp", 101, "gh-org/repo", None
        )
        assert "meta_commit_message" not in result.meta

    @patch(f"{_GH_MOD}._run_git")
    @patch(f"{_GH_MOD}._capture_git_diff", return_value=None)
    @patch(f"{_GH_MOD}.release_workspace")
    def test_post_agent_without_release(
        self,
        mock_release: MagicMock,
        mock_diff: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        # head_now == head_before → no commits
        mock_git.side_effect = [
            _make_completed(stdout="same-head\n"),  # rev-parse HEAD
        ]

        ctx = RunnerContext(
            project_file="/path/to/proj.gp",
            workspace_dir="/tmp/ws",
            workspace_num=5,
            checkout_target="feature",
            should_release=False,
            head_before="same-head",
        )

        provider = GitHubRunnerProvider()
        result = provider.post_agent(ctx)

        mock_release.assert_not_called()
        assert result.diff_path is None
        assert result.meta == {"meta_workspace": "5"}

    @patch(f"{_GH_MOD}._run_git")
    @patch(f"{_GH_MOD}._capture_git_diff", return_value="/tmp/diff.patch")
    @patch(f"{_GH_MOD}.release_workspace")
    def test_post_agent_meta_commit_message_captured(
        self,
        mock_release: MagicMock,
        mock_diff: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        mock_git.side_effect = [
            _make_completed(stdout="new-head\n"),  # rev-parse HEAD (different)
            _make_completed(stdout="fix: resolve crash\n"),  # git log -1
        ]

        ctx = RunnerContext(
            project_file="/path/to/proj.gp",
            workspace_dir="/tmp/ws",
            workspace_num=7,
            checkout_target="myrepo",
            should_release=True,
            head_before="old-head",
        )

        provider = GitHubRunnerProvider()
        result = provider.post_agent(ctx)

        assert result.meta["meta_commit_message"] == "fix: resolve crash"

    @patch(f"{_GH_MOD}._capture_git_diff", return_value=None)
    def test_post_agent_empty_head_before(
        self,
        mock_diff: MagicMock,
    ) -> None:
        ctx = RunnerContext(
            project_file="/path/to/proj.gp",
            workspace_dir="/tmp/ws",
            workspace_num=3,
            checkout_target="myrepo",
            should_release=False,
            head_before="",
        )

        provider = GitHubRunnerProvider()
        result = provider.post_agent(ctx)

        assert "meta_commit_message" not in result.meta
