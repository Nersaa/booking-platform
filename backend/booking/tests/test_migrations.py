from alembic import command
from alembic.config import Config

from tests.conftest import ALEMBIC_INI


def test_models_and_migrations_are_in_sync(migrated_database_url: str) -> None:
    """Fails when a model was changed without generating a migration."""
    config = Config(ALEMBIC_INI)
    config.attributes.update(database_url=migrated_database_url, configure_logger=False)

    command.check(config)
