"""
tests/test_main.py

Smoke test verifying main.py executes without error and prints expected boot message.
"""

import sys
from contextlib import redirect_stdout
import io
import pytest
import main


def test_main_boots_successfully() -> None:
    """Verifies main.py prints 'FSM boot ok' and exits with code 0."""
    f = io.StringIO()
    with redirect_stdout(f):
        with pytest.raises(SystemExit) as ex:
            main.main()

    # Check exit code is 0
    assert ex.value.code == 0
    # Check output
    output = f.getvalue().strip()
    assert "FSM boot ok" in output
