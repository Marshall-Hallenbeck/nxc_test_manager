"""Tests for target host parsing and test output parsing."""
from app.services.test_runner import parse_target_hosts, parse_test_output


class TestParseTargetHosts:
    def test_single_ip(self):
        result = parse_target_hosts("192.168.1.100")
        assert result == ["192.168.1.100"]

    def test_comma_separated_ips(self):
        result = parse_target_hosts("192.168.1.100,192.168.1.101")
        assert result == ["192.168.1.100", "192.168.1.101"]

    def test_comma_separated_with_spaces(self):
        result = parse_target_hosts("192.168.1.100, 192.168.1.101")
        assert result == ["192.168.1.100", "192.168.1.101"]

    def test_cidr_subnet_small(self):
        result = parse_target_hosts("192.168.1.0/30")
        # /30 has 4 addresses, 2 usable hosts
        assert result == ["192.168.1.1", "192.168.1.2"]

    def test_cidr_subnet_24(self):
        result = parse_target_hosts("10.0.0.0/24")
        assert len(result) == 254  # 256 - network - broadcast
        assert "10.0.0.1" in result
        assert "10.0.0.254" in result

    def test_mixed_ips_and_cidr(self):
        result = parse_target_hosts("192.168.1.50,10.0.0.0/30")
        assert "192.168.1.50" in result
        assert "10.0.0.1" in result
        assert "10.0.0.2" in result
        assert len(result) == 3

    def test_empty_string(self):
        result = parse_target_hosts("")
        assert result == []

    def test_invalid_cidr_ignored(self):
        result = parse_target_hosts("not-a-cidr/99")
        assert result == []

    def test_single_host_cidr(self):
        result = parse_target_hosts("192.168.1.1/32")
        # /32 is a single host
        assert result == ["192.168.1.1"]

    def test_trailing_comma(self):
        result = parse_target_hosts("192.168.1.1,")
        assert result == ["192.168.1.1"]


class TestParseTestOutput:
    """Tests for parse_test_output which returns {"results": [...], "summary": {...}}."""

    # --- NetExec emoji format (✔ / ❌) ---

    def test_netexec_checkmark_passed(self):
        output = "[15:06:54] └─$ netexec ftp 192.168.56.10 -u 'Admin' -p 'Pass' ✔"
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 1
        assert results[0]["status"].value == "passed"
        # └─$ prefix should be stripped
        assert results[0]["test_name"].startswith("netexec ftp")

    def test_netexec_cross_failed(self):
        output = "[15:07:31] netexec ftp 192.168.56.10 -u 'Admin' -p 'Pass' -M enum_ftp ❌"
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 1
        assert results[0]["status"].value == "failed"
        assert "-M enum_ftp" in results[0]["test_name"]

    def test_netexec_green_checkmark_passed(self):
        """Test ✅ (U+2705) also works as a pass marker."""
        output = "netexec smb 10.0.0.1 -u admin -p pass ✅"
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 1
        assert results[0]["status"].value == "passed"

    def test_netexec_mixed_results(self):
        output = """Running command: netexec ftp 192.168.56.10 -u 'Admin' -p 'Pass'
[15:06:54] └─$ netexec ftp 192.168.56.10 -u 'Admin' -p 'Pass' ✔
[*] Results:
Running command: netexec ftp 192.168.56.10 -u 'Admin' -p 'Pass' -M enum_ftp
[15:07:31] netexec ftp 192.168.56.10 -u 'Admin' -p 'Pass' -M enum_ftp ❌
[-] Failed loading module
[*] Results:
Running command: netexec ftp 192.168.56.10 -u 'Admin' -p 'Pass' --ls
[15:07:34] └─$ netexec ftp 192.168.56.10 -u 'Admin' -p 'Pass' --ls ✔
Ran 3 tests in 0 mins and 40 seconds -  Passed: 2  Failed: 1  Not Tested: 0"""
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 3
        passed = [r for r in results if r["status"].value == "passed"]
        failed = [r for r in results if r["status"].value == "failed"]
        assert len(passed) == 2
        assert len(failed) == 1
        # Summary should also be parsed
        assert parsed["summary"]["total"] == 3
        assert parsed["summary"]["passed"] == 2
        assert parsed["summary"]["failed"] == 1

    def test_netexec_per_test_output(self):
        """Each result should contain only its section of output, not the whole thing."""
        output = """Running command: netexec ftp 10.0.0.1 -u admin -p pass
[15:06:54] └─$ netexec ftp 10.0.0.1 -u admin -p pass ✔
[*] Results:
FTP  10.0.0.1  230 Login successful.
Running command: netexec ftp 10.0.0.1 -u admin -p pass -M enum_ftp
[15:07:31] netexec ftp 10.0.0.1 -u admin -p pass -M enum_ftp ❌
[-] Failed loading module at /nxc/modules/enum_ftp.py
[*] Results:
[-] Module error details here"""
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 2
        # First result (passed) should only have its section
        assert "Login successful" in results[0]["output"]
        assert "Failed loading module" not in results[0]["output"]
        # Second result (failed) should only have its section
        assert "Failed loading module" in results[1]["output"]
        assert "Login successful" not in results[1]["output"]

    def test_netexec_strips_box_drawing_prefix(self):
        output = "[15:06:54] └─$ netexec smb 10.0.0.1 -u admin -p pass ✔"
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 1
        # Should not contain the └─$ prefix
        assert "└─$" not in results[0]["test_name"]
        assert results[0]["test_name"].startswith("netexec smb")

    def test_netexec_long_command_truncated(self):
        long_cmd = "netexec ftp 192.168.56.10 -u 'Admin' -p 'Pass' " + "-M module " * 20
        output = f"{long_cmd} ❌"
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 1
        assert len(results[0]["test_name"]) == 100

    # --- Summary line parsing ---

    def test_summary_line_parsed(self):
        output = "Ran 19 tests in 1 mins and 12 seconds -  Passed: 7  Failed: 12  Not Tested: 7"
        parsed = parse_test_output(output)
        assert parsed["summary"]["total"] == 19
        assert parsed["summary"]["passed"] == 7
        assert parsed["summary"]["failed"] == 12
        assert parsed["summary"]["not_tested"] == 7

    def test_summary_only_no_emojis(self):
        """When only summary is available (no emoji lines), results should be empty."""
        output = "Some setup output\nRan 5 tests in 30 seconds -  Passed: 3  Failed: 2"
        parsed = parse_test_output(output)
        assert parsed["summary"]["total"] == 5
        assert parsed["summary"]["passed"] == 3
        assert parsed["summary"]["failed"] == 2
        assert len(parsed["results"]) == 0

    # --- pytest-style fallback ---

    def test_pytest_passed_output(self):
        output = "PASSED test_smb_auth in 1.5s"
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 1
        assert results[0]["test_name"] == "test_smb_auth"
        assert results[0]["status"].value == "passed"
        assert results[0]["duration"] == 1.5

    def test_pytest_failed_output(self):
        output = "FAILED test_ldap_bind in 2.3s"
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 1
        assert results[0]["test_name"] == "test_ldap_bind"
        assert results[0]["status"].value == "failed"

    def test_pytest_multiple_results(self):
        output = """PASSED test_smb_auth in 1.5s
FAILED test_ldap_bind in 2.3s
SKIPPED test_kerberos"""
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 3

    def test_no_matches(self):
        output = "Some random output with no test results"
        parsed = parse_test_output(output)
        assert parsed["results"] == []
        assert parsed["summary"]["total"] == 0

    def test_no_duration(self):
        output = "PASSED test_basic"
        parsed = parse_test_output(output)
        results = parsed["results"]
        assert len(results) == 1
        assert results[0]["duration"] is None
