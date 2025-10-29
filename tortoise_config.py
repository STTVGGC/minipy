import os

# Prefer reading DATABASE_URL from environment; fallback to the same MySQL URL
# used in main.py so behavior is consistent when no env var is set.
DEFAULT_DB = os.getenv("DATABASE_URL", "mysql://Wang:A19356756837@52.196.78.16:3306/messageboard")

TORTOISE_ORM = {
    "connections": {
        "default": DEFAULT_DB
    },
    "apps": {
        "models": {
            "models": ["models", "aerich.models"],
            "default_connection": "default",
        },
    },
}
