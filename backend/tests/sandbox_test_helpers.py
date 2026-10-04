import os

def assert_payload_executed(marker_path: str, res: dict = None):
    """Asserts that a marker file exists, proving the payload actually executed."""
    if not os.path.exists(marker_path):
        err_msg = f"Attack payload did not execute (marker missing: {marker_path})"
        if res:
            err_msg += f"\nSandbox Status: {res.get('status')}\nReturn Code: {res.get('return_code')}"
            err_msg += f"\n--- STDOUT ---\n{res.get('stdout')}"
            err_msg += f"\n--- STDERR ---\n{res.get('stderr')}"
        assert False, err_msg

def assert_attack_blocked(blocked_marker: str = None, res: dict = None, expected_status: str = None, expected_returncode: int = None):
    """Asserts that the specific attack artifact does NOT exist, or the operation explicitly failed."""
    if blocked_marker:
        assert not os.path.exists(blocked_marker), f"Security boundary breached! Attack artifact found: {blocked_marker}"
    if res and expected_status:
        assert res["status"] == expected_status, f"Expected status {expected_status}, got {res.get('status')}"
    if res and expected_returncode is not None:
        assert res["return_code"] == expected_returncode, f"Expected return code {expected_returncode}, got {res.get('return_code')}"
