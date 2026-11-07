import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from llamacpp_model import LlamaServer


@pytest.fixture
def llamacpp_backend(tmp_path: Path):
    executable = os.environ.get("LLAMACPP_SERVER_EXE")
    model = os.environ.get("LLAMACPP_MODEL_FILE")
    if not executable or not model:
        pytest.fail("Integration requires LLAMACPP_SERVER_EXE and LLAMACPP_MODEL_FILE")
    run_dir = tmp_path / "backend"
    run_dir.mkdir()
    backend = LlamaServer(Path(executable), Path(model), run_dir)
    try:
        backend.start()
        yield backend
    finally:
        assert backend.close()
