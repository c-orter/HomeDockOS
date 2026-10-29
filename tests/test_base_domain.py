import pytest

from pymodules.hd_BaseDomain import validate_base_domain


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_is_allowed(raw):
    assert validate_base_domain(raw) == ("", None)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Example.COM", "example.com"),
        ("https://www.example.com/path", "example.com"),
        ("home.example.co.uk.", "home.example.co.uk"),
        ("example.com:8080", "example.com"),
    ],
)
def test_normalizes(raw, expected):
    assert validate_base_domain(raw) == (expected, None)


@pytest.mark.parametrize("raw", ["nodots", "1.2.3.4", "bad_name.com", "-a.example.com", "a..com", "*.example.com"])
def test_rejects_invalid_names(raw):
    domain, error = validate_base_domain(raw)

    assert domain == ""
    assert error


@pytest.mark.parametrize("raw", ["duckdns.org", "co.uk", "github.io", "freemyip.com"])
def test_rejects_public_suffixes(raw):
    domain, error = validate_base_domain(raw)

    assert domain == ""
    assert "public suffix" in error


def test_accepts_subdomain_of_public_suffix():
    assert validate_base_domain("mine.duckdns.org") == ("mine.duckdns.org", None)
