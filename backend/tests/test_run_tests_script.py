"""Tests for the test-runner entrypoint script (docker/test-runner/run_tests.sh).

The script is exercised by extracting its command-building section and running it
under bash with a stub for the python invocation, so the assertions cover the real
shell code rather than a copy of it.
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "docker" / "test-runner" / "run_tests.sh"

# Stub standing in for the real python interpreter. It prints argv one element
# per line so a test can assert on the exact arguments the script passed. It
# must be a real executable, not a shell function: the script invokes the
# command through `timeout`, which execs a binary and cannot see shell
# functions.
PYTHON_STUB = """#!/bin/bash
echo '--ARGV-START--'
printf '%s\\n' "$@"
echo '--ARGV-END--'
"""


def script_text() -> str:
    return SCRIPT.read_text()


def run_command_section(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run the script's command-building + execution section under bash."""
    text = script_text()
    start = text.index("# Build the command as an argument array")
    harness = "#!/bin/bash\nset -e\n" + text[start:]

    with tempfile.TemporaryDirectory() as bindir:
        stub = Path(bindir) / "python"
        stub.write_text(PYTHON_STUB)
        stub.chmod(0o755)

        return subprocess.run(
            ["bash", "-c", harness],
            capture_output=True,
            text=True,
            env={"PATH": f"{bindir}:/usr/bin:/bin", **env},
            timeout=60,
        )


def parse_argv(stdout: str) -> list[str]:
    lines = stdout.splitlines()
    start = lines.index("--ARGV-START--")
    end = lines.index("--ARGV-END--")
    return lines[start + 1:end]


BASE_ENV = {
    "TARGET_HOST": "10.0.0.1",
    "TARGET_USERNAME": "administrator",
    "TARGET_PASSWORD": "Passw0rd!",
}


class TestCommandBuilding:
    def test_base_command_passes_credentials_as_single_arguments(self):
        result = run_command_section(BASE_ENV)
        argv = parse_argv(result.stdout)
        assert argv[:7] == [
            "tests/e2e_tests.py",
            "-t", "10.0.0.1",
            "-u", "administrator",
            "-p", "Passw0rd!",
        ]

    def test_comma_separated_protocols_become_separate_arguments(self):
        result = run_command_section({**BASE_ENV, "PROTOCOLS": "smb,ldap,winrm"})
        argv = parse_argv(result.stdout)
        idx = argv.index("--protocols")
        assert argv[idx + 1:idx + 4] == ["smb", "ldap", "winrm"]

    def test_comma_separated_line_nums_become_separate_arguments(self):
        result = run_command_section({**BASE_ENV, "LINE_NUMS": "5,10-15,20"})
        argv = parse_argv(result.stdout)
        idx = argv.index("--line-nums")
        assert argv[idx + 1:idx + 4] == ["5", "10-15", "20"]

    def test_optional_flags_are_appended(self):
        result = run_command_section({
            **BASE_ENV,
            "USE_KERBEROS": "1",
            "VERBOSE": "1",
            "SHOW_ERRORS": "1",
            "NOT_TESTED": "1",
            "DNS_SERVER": "8.8.8.8",
        })
        argv = parse_argv(result.stdout)
        assert "-k" in argv
        assert "-v" in argv
        assert "-e" in argv
        assert "--not-tested" in argv
        assert argv[argv.index("--dns-server") + 1] == "8.8.8.8"


class TestPasswordIsNotLogged:
    def test_password_is_redacted_in_the_executing_log_line(self):
        """Regression: the script echoed the full command including
        `-p <password>`. That line is streamed to the database and rendered in
        the web UI, disclosing the target credential to anyone who can read a
        test run.
        """
        password = "SuperSecret123!"
        result = run_command_section({**BASE_ENV, "TARGET_PASSWORD": password})

        executing = next(
            line for line in result.stdout.splitlines() if line.startswith("Executing:")
        )
        assert password not in executing
        assert "-p ******" in executing

    def test_password_still_reaches_the_test_command_intact(self):
        password = "SuperSecret123!"
        result = run_command_section({**BASE_ENV, "TARGET_PASSWORD": password})
        argv = parse_argv(result.stdout)
        assert argv[argv.index("-p") + 1] == password


class TestNoShellInjection:
    @pytest.mark.parametrize(
        "hostile",
        [
            'pw"; echo INJECTED; "',
            "pw$(echo INJECTED)",
            "pw`echo INJECTED`",
            "pw; echo INJECTED",
            "pw && echo INJECTED",
        ],
    )
    def test_hostile_password_is_not_executed(self, hostile):
        """Regression: the command was assembled into a string and run through
        `eval`, so shell metacharacters in the password (free-form from the web
        UI) were re-parsed and executed inside the test container.
        """
        result = run_command_section({**BASE_ENV, "TARGET_PASSWORD": hostile})

        assert "INJECTED" not in result.stdout.replace(hostile, "")
        argv = parse_argv(result.stdout)
        assert argv[argv.index("-p") + 1] == hostile

    def test_hostile_target_host_is_not_executed(self):
        hostile = "10.0.0.1; echo INJECTED"
        result = run_command_section({**BASE_ENV, "TARGET_HOST": hostile})

        assert "INJECTED" not in result.stdout.replace(hostile, "")
        argv = parse_argv(result.stdout)
        assert argv[argv.index("-t") + 1] == hostile

    def test_script_does_not_use_eval(self):
        code_lines = [
            line for line in script_text().splitlines()
            if not line.lstrip().startswith("#")
        ]
        assert not [line for line in code_lines if "eval" in line.split()]


class TestTimeoutHandling:
    def test_timeout_message_is_reported(self):
        """Regression: `set -e` aborted the script at the failing command, so
        `EXIT_CODE=$?` and the 124/timeout branch below it never ran and the
        user never saw why the run stopped.
        """
        text = script_text()
        start = text.index("# Use timeout to prevent infinite hangs")
        harness = (
            "#!/bin/bash\n"
            "set -e\n"
            "CMD=(sleep 30)\n"
            + text[start:]
        )
        result = subprocess.run(
            ["bash", "-c", harness],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "CONTAINER_TIMEOUT": "1"},
            timeout=60,
        )
        assert "ERROR: Test execution timed out after 1 seconds" in result.stdout
        assert result.returncode == 124

    def test_successful_run_exits_zero(self):
        text = script_text()
        start = text.index("# Use timeout to prevent infinite hangs")
        harness = "#!/bin/bash\nset -e\nCMD=(true)\n" + text[start:]
        result = subprocess.run(
            ["bash", "-c", harness],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
            timeout=60,
        )
        assert result.returncode == 0
        assert "timed out" not in result.stdout


class TestDependencyVerification:
    def test_uses_protocol_loader_not_bare_connection_import(self):
        """Regression: `from nxc.connection import connection` passed on images
        whose protocol modules could not import, because nxc/protocols/<name>/
        packages shadow the sibling <name>.py. The runtime check must match the
        one baked into the PR/branch image.
        """
        text = script_text()
        assert "ProtocolLoader" in text
        assert "pl.load_protocol(p['path'])" in text
        assert 'python -c "from nxc.connection import connection"' not in text
