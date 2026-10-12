import os

DEFAULT_URL = "postgresql+psycopg://daydor_owner:dev@localhost/daydor_dev"


def database_url() -> str:
    return os.environ.get("DAYDOR_DATABASE_URL", DEFAULT_URL)


def test_database_url() -> str:
    return os.environ.get("DAYDOR_TEST_DATABASE_URL",
                          "postgresql+psycopg://daydor_owner:dev@localhost/daydor_test")
