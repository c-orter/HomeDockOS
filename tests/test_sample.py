from pymodules.hd_AppSubdomains import slugify_container_name


def test_slugify_container_name():
    assert slugify_container_name("My_App.1") == "my-app-1"


def test_slugify_collapses_dashes_and_trims():
    assert slugify_container_name("--a__b--") == "a-b"
