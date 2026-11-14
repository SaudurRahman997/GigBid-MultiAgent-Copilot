"""Needs `make up`. Checks the three Phase 0 services respond on their ports."""

import socket
import urllib.request

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("port", [5432, 6379])
def test_tcp_port_open(port):
    with socket.create_connection(("localhost", port), timeout=3):
        pass


def test_phoenix_healthz():
    with urllib.request.urlopen("http://localhost:6006/healthz", timeout=5) as resp:
        assert resp.status == 200
