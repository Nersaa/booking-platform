import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.conf import settings
from django.core.cache import cache
from moto import mock_aws
from rest_framework.test import APIClient

from apps.common import storage
from apps.users.models import User
from apps.users.tokens import issue_token_pair


@pytest.fixture(scope="session")
def django_db_modify_db_settings(
    django_db_modify_db_settings_parallel_suffix: None,
) -> Iterator[None]:
    """Run tests against real PostgreSQL: TEST_DATABASE_URL if set, else a throwaway container."""
    if os.environ.get("TEST_DATABASE_URL"):
        import environ

        settings.DATABASES["default"].update(
            environ.Env.db_url_config(os.environ["TEST_DATABASE_URL"])
        )
        yield
        return

    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as postgres:
        settings.DATABASES["default"].update(
            HOST=postgres.get_container_host_ip(),
            PORT=postgres.get_exposed_port(5432),
            USER=postgres.username,
            PASSWORD=postgres.password,
            NAME=postgres.dbname,
        )
        yield


@pytest.fixture(autouse=True)
def s3() -> Iterator[Any]:
    with mock_aws():
        storage.reset_clients()
        client = storage.internal_client()
        client.create_bucket(Bucket=settings.S3_BUCKET)
        yield client
    storage.reset_clients()


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def client_for() -> Callable[[User], APIClient]:
    def make(user: User) -> APIClient:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token_pair(user)['access']}")
        return client

    return make
