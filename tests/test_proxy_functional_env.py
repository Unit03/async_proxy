import asyncio
import copy
import os
import pytest
import requests
import subprocess
import time


def setup_function(function):
    python = os.path.join(os.environ["VIRTUAL_ENV"], "bin", "python")

    global simple_server
    simple_server = subprocess.Popen([python, "simple_server.py", "8001"])

    global proxy_server
    env = copy.deepcopy(os.environ)
    env["PROXY_PORT"] = "8123"
    proxy_server = subprocess.Popen([python, "proxy.py"], env=env)
    time.sleep(0.5)

    # Check for failed runs of above servers (they will fail in teardown if
    # so).
    proxy_server.poll()
    simple_server.poll()


def teardown_function(function):
    proxy_server.kill()
    simple_server.kill()


@pytest.mark.functional
def test_get():
    response = requests.get("http://localhost:8001",
                            proxies={"http": "http://localhost:8123"})

    assert response.status_code == 200
    assert "<title>Hello</title>" in response.text
    assert "<h1>Hello</h1>" in response.text
