"""Schema setup and migration helpers."""
from db.models import init_db


def setup():
    """Create all tables (idempotent)."""
    init_db()
    print("Database initialized successfully.")


if __name__ == "__main__":
    setup()
