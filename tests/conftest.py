import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run tests marked with @pytest.mark.live (make real network calls).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="Pass --live to run network tests.")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip)
