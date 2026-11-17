"""Import every model so Alembic sees the full metadata."""
from app.models.base import Base  # noqa: F401
from app.models.catalog import *  # noqa: F401,F403
from app.models.identity import *  # noqa: F401,F403
from app.models.inventory import *  # noqa: F401,F403
from app.models.money import *  # noqa: F401,F403
from app.models.orders import *  # noqa: F401,F403
from app.models.phase2 import *  # noqa: F401,F403
