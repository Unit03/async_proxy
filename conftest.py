import pytest


def pytest_addoption(parser):
    parser.addoption("--functional", action="store_true",
                     help="Run functional tests")


def pytest_runtest_setup(item):
    if "functional" in item.keywords \
            and not item.config.getoption("--functional"):
        pytest.skip("need --functional option to run")
