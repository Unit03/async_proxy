import asyncio
import json
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
    proxy_server = subprocess.Popen([python, "proxy.py"])
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
                            proxies={"http": "http://localhost:8000"})
    
    assert response.status_code == 200
    assert "<title>Hello</title>" in response.text
    assert "<h1>Hello</h1>" in response.text


@pytest.mark.functional
def test_get_range_from():
    response = requests.get("http://localhost:8001",
                            headers={"range": "bytes=6-"},
                            proxies={"http": "http://localhost:8000"})
    
    assert response.status_code == 206
    assert len(response.text) == 67
    assert response.text.startswith("<head>")
    assert "<title>Hello</title>" in response.text
    assert "<h1>Hello</h1>" in response.text


@pytest.mark.functional
def test_get_range_to():
    # "Last N bytes".
    response = requests.get("http://localhost:8001",
                            headers={"range": "bytes=-7"},
                            proxies={"http": "http://localhost:8000"})

    assert response.status_code == 206
    assert response.text == "</html>"


@pytest.mark.functional
def test_get_range_from_to():
    response = requests.get("http://localhost:8001",
                            headers={"range": "bytes=6-11"},
                            proxies={"http": "http://localhost:8000"})
    
    assert response.status_code == 206
    assert response.text.startswith("<head>")


@pytest.mark.functional
def test_get_range_multi():
    response = requests.get("http://localhost:8001",
                            headers={"range": "bytes=6-11,19-23"},
                            proxies={"http": "http://localhost:8000"})

    assert response.status_code == 206
    assert response.text == "<head>Hello"


@pytest.mark.functional
def test_get_range_query():
    response = requests.get("http://localhost:8001",
                            params={"range": "bytes=6-"},
                            proxies={"http": "http://localhost:8000"})

    assert response.status_code == 206
    assert response.text.startswith("<head>")
    assert "<title>Hello</title>" in response.text
    assert "<h1>Hello</h1>" in response.text


@pytest.mark.functional
def test_get_range_both():
    # Range specified both in query and headers.
    response = requests.get("http://localhost:8001",
                            params={"range": "bytes=6-"},
                            headers={"range": "bytes=6-"},
                            proxies={"http": "http://localhost:8000"})

    assert response.status_code == 206
    assert response.text.startswith("<head>")
    assert "<title>Hello</title>" in response.text
    assert "<h1>Hello</h1>" in response.text


@pytest.mark.functional
def test_get_range_remote_range():
    response = requests.get("http://localhost:8001/range",
                            headers={"range": "bytes=6-11"},
                            proxies={"http": "http://localhost:8000"})

    assert response.status_code == 206
    assert response.text.startswith("<head>")


@pytest.mark.functional
def test_get_range_mismatch():
    # Range specified both in query and headers, but differently.
    response = requests.get("http://localhost:8001",
                            params={"range": "bytes=6-"},
                            headers={"range": "bytes=7-"},
                            proxies={"http": "http://localhost:8000"})

    assert response.status_code == 416

    response = requests.get("http://localhost:8001",
                            params={"range": "bytes=0-10"},
                            headers={"range": "bytes=0-9"},
                            proxies={"http": "http://localhost:8000"})

    assert response.status_code == 416

    response = requests.get("http://localhost:8001",
                            params={"range": "bytes=0-10"},
                            headers={"range": "bytes=1-10"},
                            proxies={"http": "http://localhost:8000"})

    assert response.status_code == 416



@pytest.mark.functional
def test_post():
    data = b"zxcv"

    response = requests.post("http://localhost:8001",
                             proxies={"http": "http://localhost:8000"},
                             data=data)

    assert response.status_code == 200
    assert "<title>Hello</title>" in response.text
    assert data.decode() in response.text


@pytest.mark.functional
def test_stats():
    response = requests.get("http://localhost:8000/stats")

    assert response.status_code == 200
    data = json.loads(response.text)

    assert data["total_bytes_transferred"] == 0
    assert "uptime" in data

    response = requests.get("http://localhost:8001",
                            proxies={"http": "http://localhost:8000"})

    assert response.status_code == 200

    response = requests.get("http://localhost:8000/stats")

    assert response.status_code == 200
    data = json.loads(response.text)

    assert data["total_bytes_transferred"] > 0
