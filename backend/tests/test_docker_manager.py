"""Tests for Docker image resolution and container execution."""
import re
from unittest.mock import MagicMock, patch

import httpx
import pytest
from docker.errors import APIError

from app.services import docker_manager
from app.services.docker_manager import render_source_dockerfile


class TestRenderSourceDockerfile:
    def test_pr_mode_fetches_pr_ref(self):
        content = render_source_dockerfile("Pennyw0rth/NetExec", pr_number=1132)
        assert "git fetch --depth 1 origin pull/1132/head:pr-1132" in content
        assert "git checkout -q pr-1132" in content

    def test_branch_mode_fetches_branch(self):
        content = render_source_dockerfile("Pennyw0rth/NetExec", branch="main")
        assert "git fetch --depth 1 origin main" in content
        assert "git checkout -q FETCH_HEAD" in content

    def test_repo_is_used_in_remote_url(self):
        content = render_source_dockerfile("someone/Fork", pr_number=7)
        assert "https://github.com/someone/Fork.git" in content

    def test_poetry_install_failure_is_not_swallowed(self):
        """Regression: `poetry install ... ;` let dependency resolution failures
        through, producing an image with stale deps that silently failed 169 e2e
        tests. The install must be chained with && so the build fails loudly.
        """
        content = render_source_dockerfile("Pennyw0rth/NetExec", pr_number=1132)
        assert "poetry install --no-interaction;" not in content
        assert "poetry install --no-interaction && \\" in content

    def test_dependency_check_loads_every_protocol(self):
        """Regression: importing nxc.connection passed on an image whose protocol
        modules could not import (missing dploot/certihound), because
        nxc/protocols/<name>/ packages shadow the sibling <name>.py. The check must
        load protocols by path the way ProtocolLoader does at runtime.
        """
        content = render_source_dockerfile("Pennyw0rth/NetExec", pr_number=1132)
        assert "ProtocolLoader" in content
        assert "pl.load_protocol(p['path'])" in content
        assert 'RUN python -c "from nxc.connection import connection;' not in content


class TestGetImageDependencyResolution:
    """`get_image` must never quietly fall back to the base image.

    Regression: when poetry.lock could not be fetched, get_image logged a
    warning and returned the base image. The PR was then tested against stale
    dependencies, which surfaced as a mass e2e failure (169 tests) rather than
    as the dependency problem it actually was.
    """

    def test_unfetchable_source_lockfile_raises(self):
        """A lockfile that exists but cannot be read (here: a 500) must abort.
        A 404 is a different case — see TestMissingLockfileHandling.
        """
        docker_manager.poetry_lock_cache.clear()
        with (
            patch.object(docker_manager, "ensure_image_built"),
            patch.object(docker_manager, "source_image_exists", return_value=False),
            patch.object(docker_manager, "get_base_poetry_lock_hash", return_value="basehash"),
            patch.object(docker_manager.httpx, "get") as http_get,
        ):
            http_get.return_value = httpx.Response(
                500, request=httpx.Request("GET", "https://raw.githubusercontent.com/x")
            )
            with pytest.raises(httpx.HTTPStatusError):
                docker_manager.get_image(pr_number=999, repo="Pennyw0rth/NetExec")

    def test_unreadable_base_lockfile_raises(self):
        docker_manager.poetry_lock_cache.clear()
        client = MagicMock()
        client.containers.run.side_effect = RuntimeError("no such file /poetry.lock.base")
        with (
            patch.object(docker_manager, "ensure_image_built"),
            patch.object(docker_manager, "source_image_exists", return_value=False),
            patch.object(docker_manager, "get_client", return_value=client),
            pytest.raises(RuntimeError, match=re.escape("poetry.lock.base")),
        ):
            docker_manager.get_image(pr_number=999, repo="Pennyw0rth/NetExec")

    def test_matching_hashes_use_base_image(self):
        docker_manager.poetry_lock_cache.clear()
        with (
            patch.object(docker_manager, "ensure_image_built"),
            patch.object(docker_manager, "source_image_exists", return_value=False),
            patch.object(docker_manager, "get_base_poetry_lock_hash", return_value="samehash"),
            patch.object(docker_manager, "get_poetry_lock_hash", return_value="samehash"),
        ):
            image = docker_manager.get_image(pr_number=999, repo="Pennyw0rth/NetExec")
        assert image == docker_manager.DOCKER_IMAGE_NAME

    def test_failed_build_raises_rather_than_returning_base_image(self):
        docker_manager.poetry_lock_cache.clear()
        with (
            patch.object(docker_manager, "ensure_image_built"),
            patch.object(docker_manager, "source_image_exists", return_value=False),
            patch.object(docker_manager, "get_base_poetry_lock_hash", return_value="basehash"),
            patch.object(docker_manager, "get_poetry_lock_hash", return_value="sourcehash"),
            patch.object(docker_manager, "build_source_image", return_value=False),
            pytest.raises(RuntimeError, match="Failed to build image"),
        ):
            docker_manager.get_image(pr_number=999, repo="Pennyw0rth/NetExec")


class TestRunTestContainerLogStreaming:
    def make_client(self, log_chunks, stream_error=None):
        container = MagicMock()
        container.id = "c" * 64
        if stream_error:
            container.logs.side_effect = stream_error
        else:
            container.logs.return_value = iter(log_chunks)
        container.wait.return_value = {"StatusCode": 0}
        client = MagicMock()
        client.containers.run.return_value = container
        return client, container

    def test_streams_lines_to_callback(self):
        client, container = self.make_client([b"line one\nline two\n"])
        lines = []
        with patch.object(docker_manager, "get_client", return_value=client):
            exit_code, container_id = docker_manager.run_test_container(
                pr_number=1, target_host="10.0.0.1", target_username="u",
                target_password="p", image_name="img", log_callback=lines.append,
            )
        assert lines == ["line one", "line two"]
        assert exit_code == 0
        assert container_id == "c" * 64
        container.remove.assert_called_once_with(force=True)

    def test_streaming_failure_propagates_and_still_removes_container(self):
        """Regression: a streaming error was caught and logged, then the run
        continued and reported an exit code derived from a truncated log. A
        partial log must not be scored as a test result.
        """
        client, container = self.make_client([], stream_error=OSError("stream broke"))
        with (
            patch.object(docker_manager, "get_client", return_value=client),
            pytest.raises(OSError, match="stream broke"),
        ):
            docker_manager.run_test_container(
                pr_number=1, target_host="10.0.0.1", target_username="u",
                target_password="p", image_name="img",
            )
        container.remove.assert_called_once_with(force=True)

    def test_password_is_passed_via_environment_not_command(self):
        client, container = self.make_client([b"done\n"])
        with patch.object(docker_manager, "get_client", return_value=client):
            docker_manager.run_test_container(
                pr_number=1, target_host="10.0.0.1", target_username="u",
                target_password="s3cret", image_name="img",
            )
        kwargs = client.containers.run.call_args.kwargs
        assert kwargs["environment"]["TARGET_PASSWORD"] == "s3cret"
        assert "command" not in kwargs


class TestImageTagNaming:
    """Docker tags accept only [A-Za-z0-9_.-] after the colon."""

    DOCKER_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")

    def tag_of(self, image_name):
        return image_name.split(":", 1)[1]

    def test_slashed_branch_produces_a_valid_tag(self):
        """Regression: the branch name went into the tag verbatim, so any
        branch with a slash (feature/foo) produced
        `netexec-test-runner:<hash>-branch-feature/foo`, which Docker rejects
        with "invalid tag" and failed the entire run at build time.
        """
        name = docker_manager.get_source_image_name(branch="security/detection-integrity")
        assert "/" not in self.tag_of(name)
        assert self.DOCKER_TAG.match(self.tag_of(name))

    @pytest.mark.parametrize(
        "branch",
        [
            "main",
            "feature/foo",
            "release/v1.2.3",
            "user/fix_thing-2",
            "deeply/nested/branch/name",
            "weird~branch^name:with*chars",
        ],
    )
    def test_arbitrary_branches_produce_valid_tags(self, branch):
        name = docker_manager.get_source_image_name(branch=branch)
        assert self.DOCKER_TAG.match(self.tag_of(name)), name

    def test_pr_tag_is_valid(self):
        name = docker_manager.get_source_image_name(pr_number=1132)
        assert self.DOCKER_TAG.match(self.tag_of(name))

    def test_branches_that_normalise_alike_stay_distinct(self):
        a = docker_manager.get_source_image_name(branch="feature/foo")
        b = docker_manager.get_source_image_name(branch="feature-foo")
        assert a != b

    def test_same_branch_is_stable_across_calls(self):
        a = docker_manager.get_source_image_name(branch="feature/foo")
        b = docker_manager.get_source_image_name(branch="feature/foo")
        assert a == b

    def test_long_branch_name_stays_within_tag_limit(self):
        name = docker_manager.get_source_image_name(branch="feature/" + "x" * 300)
        assert self.DOCKER_TAG.match(self.tag_of(name))

    def test_different_repos_stay_distinct(self):
        a = docker_manager.get_source_image_name(branch="main", repo="Pennyw0rth/NetExec")
        b = docker_manager.get_source_image_name(branch="main", repo="fork/NetExec")
        assert a != b


class TestMissingLockfileHandling:
    """A missing poetry.lock and an unreachable GitHub are different failures."""

    def test_absent_lockfile_returns_none_and_uses_base_image(self):
        docker_manager.poetry_lock_cache.clear()
        with (
            patch.object(docker_manager, "ensure_image_built"),
            patch.object(docker_manager, "source_image_exists", return_value=False),
            patch.object(docker_manager, "get_base_poetry_lock_hash", return_value="basehash"),
            patch.object(docker_manager.httpx, "get") as http_get,
        ):
            http_get.return_value = httpx.Response(
                404, request=httpx.Request("GET", "https://raw.githubusercontent.com/x")
            )
            image = docker_manager.get_image(pr_number=42, repo="someone/no-lockfile")

        assert image == docker_manager.DOCKER_IMAGE_NAME

    def test_absent_lockfile_is_reported_to_the_log_callback(self):
        docker_manager.poetry_lock_cache.clear()
        lines = []
        with (
            patch.object(docker_manager, "ensure_image_built"),
            patch.object(docker_manager, "source_image_exists", return_value=False),
            patch.object(docker_manager, "get_base_poetry_lock_hash", return_value="basehash"),
            patch.object(docker_manager.httpx, "get") as http_get,
        ):
            http_get.return_value = httpx.Response(
                404, request=httpx.Request("GET", "https://raw.githubusercontent.com/x")
            )
            docker_manager.get_image(
                pr_number=42, repo="someone/no-lockfile", log_callback=lines.append
            )

        assert any("no poetry.lock" in line.lower() for line in lines)

    @pytest.mark.parametrize("status", [403, 429, 500, 502])
    def test_other_http_errors_still_raise(self, status):
        """A rate limit or server error must not be mistaken for "no lockfile" —
        that is the silent-stale-dependency path this guards against.
        """
        docker_manager.poetry_lock_cache.clear()
        with (
            patch.object(docker_manager, "ensure_image_built"),
            patch.object(docker_manager, "source_image_exists", return_value=False),
            patch.object(docker_manager, "get_base_poetry_lock_hash", return_value="basehash"),
            patch.object(docker_manager.httpx, "get") as http_get,
        ):
            http_get.return_value = httpx.Response(
                status, request=httpx.Request("GET", "https://raw.githubusercontent.com/x")
            )
            with pytest.raises(httpx.HTTPStatusError):
                docker_manager.get_image(pr_number=42, repo="Pennyw0rth/NetExec")

    def test_network_error_still_raises(self):
        docker_manager.poetry_lock_cache.clear()
        with (
            patch.object(docker_manager, "ensure_image_built"),
            patch.object(docker_manager, "source_image_exists", return_value=False),
            patch.object(docker_manager, "get_base_poetry_lock_hash", return_value="basehash"),
            patch.object(docker_manager.httpx, "get", side_effect=httpx.ConnectError("no route")),
            pytest.raises(httpx.ConnectError),
        ):
            docker_manager.get_image(pr_number=42, repo="Pennyw0rth/NetExec")

    def test_absent_lockfile_result_is_cached(self):
        docker_manager.poetry_lock_cache.clear()
        with patch.object(docker_manager.httpx, "get") as http_get:
            http_get.return_value = httpx.Response(
                404, request=httpx.Request("GET", "https://raw.githubusercontent.com/x")
            )
            first = docker_manager.get_poetry_lock_hash(pr_number=42, repo="a/b")
            second = docker_manager.get_poetry_lock_hash(pr_number=42, repo="a/b")

        assert first is None
        assert second is None
        assert http_get.call_count == 1


class TestCleanupSourceImages:
    def make_image(self, tags, created):
        img = MagicMock()
        img.tags = tags
        img.attrs = {"Created": created}
        return img

    def make_client(self, images):
        client = MagicMock()
        client.images.list.return_value = images
        return client

    def images_newest_first(self, count):
        """Count images tagged pr-0..pr-N, pr-0 newest."""
        return [
            self.make_image([f"netexec-test-runner:hash-pr-{i}"], f"2026-01-{30 - i:02d}T00:00:00Z")
            for i in range(count)
        ]

    def test_removes_only_images_beyond_the_keep_limit(self):
        client = self.make_client(self.images_newest_first(5))
        with patch.object(docker_manager, "get_client", return_value=client):
            removed = docker_manager.cleanup_source_images(keep_recent=3)

        assert removed == [
            "netexec-test-runner:hash-pr-3",
            "netexec-test-runner:hash-pr-4",
        ]

    def test_keeps_everything_when_under_the_limit(self):
        client = self.make_client(self.images_newest_first(3))
        with patch.object(docker_manager, "get_client", return_value=client):
            removed = docker_manager.cleanup_source_images(keep_recent=10)

        assert removed == []
        client.images.remove.assert_not_called()

    def test_never_removes_the_latest_base_image(self):
        images = [
            self.make_image(["netexec-test-runner:latest"], "2020-01-01T00:00:00Z"),
            *self.images_newest_first(2),
        ]
        client = self.make_client(images)
        with patch.object(docker_manager, "get_client", return_value=client):
            removed = docker_manager.cleanup_source_images(keep_recent=1)

        assert "netexec-test-runner:latest" not in removed
        assert removed == ["netexec-test-runner:hash-pr-1"]

    def test_image_in_use_is_kept_not_forced(self):
        """An image a running container still references must survive cleanup:
        concurrent runs would otherwise have the image pulled out from under
        them. force=False makes Docker refuse, and the tag is simply retained.
        """
        client = self.make_client(self.images_newest_first(3))
        client.images.remove.side_effect = APIError("conflict: image is in use")
        with patch.object(docker_manager, "get_client", return_value=client):
            removed = docker_manager.cleanup_source_images(keep_recent=1)

        assert removed == []
        for call in client.images.remove.call_args_list:
            assert call.kwargs["force"] is False

    def test_one_in_use_image_does_not_block_the_others(self):
        client = self.make_client(self.images_newest_first(4))
        client.images.remove.side_effect = [APIError("in use"), None, None]
        with patch.object(docker_manager, "get_client", return_value=client):
            removed = docker_manager.cleanup_source_images(keep_recent=1)

        assert removed == [
            "netexec-test-runner:hash-pr-2",
            "netexec-test-runner:hash-pr-3",
        ]

    def test_zero_disables_cleanup(self):
        client = self.make_client(self.images_newest_first(50))
        with patch.object(docker_manager, "get_client", return_value=client):
            removed = docker_manager.cleanup_source_images(keep_recent=0)

        assert removed == []
        client.images.remove.assert_not_called()

    def test_defaults_to_the_configured_cache_size(self):
        from app.config import settings

        client = self.make_client(self.images_newest_first(5))
        with (
            patch.object(docker_manager, "get_client", return_value=client),
            patch.object(settings, "image_cache_size", 2),
        ):
            removed = docker_manager.cleanup_source_images()

        assert len(removed) == 3
