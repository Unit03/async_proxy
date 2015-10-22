import asyncio
import os
import pytest
import requests
import subprocess
import time


def setup_function(function):
    python = os.path.join(os.environ["VIRTUAL_ENV"], "bin", "python")

    global simple_server
    simple_server = subprocess.Popen([python, "simple_server.py"])

    global proxy_server
    proxy_server = subprocess.Popen([python, "run.py"])
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
    response = requests.get("http://localhost:8000",
                            proxies={"http": "http://localhost:8001"})
    
    assert response.status_code == 200
    assert "<title>Hello</title>" in response.text
    assert "<h1>Hello</h1>" in response.text


@pytest.mark.functional
def test_get_range_from():
    response = requests.get("http://localhost:8000",
                            headers={"range": "bytes=6-"},
                            proxies={"http": "http://localhost:8001"})
    
    assert response.status_code == 200
    assert response.text.startswith("<head>")
    assert "<title>Hello</title>" in response.text
    assert "<h1>Hello</h1>" in response.text


@pytest.mark.functional
def test_get_range_from_to():
    response = requests.get("http://localhost:8000",
                            headers={"range": "bytes=6-11"},
                            proxies={"http": "http://localhost:8001"})
    
    assert response.status_code == 200
    assert response.text.startswith("<head>")


@pytest.mark.functional
def test_get_range_multi():
    response = requests.get("http://localhost:8000",
                            headers={"range": "bytes=6-11,19-23"},
                            proxies={"http": "http://localhost:8001"})
    
    assert response.status_code == 200
    assert response.text == "<head>Hello"


@pytest.mark.functional
def test_post():
    data = b"zxcv"

    response = requests.post("http://localhost:8000",
                             proxies={"http": "http://localhost:8001"},
                             data=data)
    
    assert response.status_code == 200
    assert "<title>Hello</title>" in response.text
    assert data.decode() in response.text


if __name__ == "__main__":
    test_functional()