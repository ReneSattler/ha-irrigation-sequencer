"""Shared pytest fixtures for the irrigation_sequencer test suite."""
import asyncio
import sys

import pytest

# On Windows, asyncio's default ProactorEventLoop needs a real OS socket for
# its internal self-pipe, which pytest-socket (used transitively here to
# keep tests from making real network calls) blocks - breaking every test
# with a SocketBlockedError before it even runs. The SelectorEventLoop
# doesn't need that socket. Linux/macOS CI is unaffected either way.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/irrigation_sequencer loadable in tests."""
    yield
