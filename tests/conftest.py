import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create and cleanup a temporary directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
