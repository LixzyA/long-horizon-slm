import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import network_guard


def test_only_ipv4_isolated_internal_network_is_accepted() -> None:
    good = {
        "Internal": True,
        "EnableIPv6": False,
        "Options": {"com.docker.network.bridge.gateway_mode_ipv4": "isolated"},
    }
    assert network_guard.verify_network_settings(good)
    assert not network_guard.verify_network_settings({**good, "Internal": False})
    assert not network_guard.verify_network_settings({**good, "EnableIPv6": True})
    assert not network_guard.verify_network_settings({**good, "Options": {}})
