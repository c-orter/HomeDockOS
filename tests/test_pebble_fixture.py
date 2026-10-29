import requests

import pytest

pytestmark = pytest.mark.pebble


def test_pebble_directory_is_served(pebble):
    directory = requests.get(pebble["directory"], verify=pebble["ca"], timeout=5).json()

    assert "newOrder" in directory
    assert "newAccount" in directory
