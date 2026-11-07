import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PI_MODULES = (
    Path.home() / ".pi" / "agent" / "install" / "releases" / "1.4.0" / "node_modules"
)


def main() -> int:
    if not (
        PI_MODULES / "@earendil-works" / "pi-coding-agent" / "package.json"
    ).is_file():
        print(f"Pi 1.4.0 is not installed at {PI_MODULES}.", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="long-horizon-pi-build-") as directory:
        context = Path(directory)
        shutil.copy(ROOT / "docker" / "Dockerfile", context)
        shutil.copy(ROOT / "docker" / "entrypoint.sh", context)
        shutil.copy(ROOT / "docker" / "gateway.py", context)
        shutil.copy(ROOT / "src" / "llamacpp_config.py", context)
        shutil.copytree(PI_MODULES, context / "node_modules")
        return subprocess.call(
            ["docker", "build", "-t", "long-horizon-pi:1.4.0", str(context)]
        )


if __name__ == "__main__":
    raise SystemExit(main())
