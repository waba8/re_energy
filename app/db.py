"""MongoDB Atlas connection and collection handles.

The connection URI is assembled from parts so the password never lands in a
committed file. .env is gitignored; the repo is public.
"""
import os
import urllib.parse

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

CLUSTER_HOST = "cluster0.t3hdaj.mongodb.net"
DB_NAME = "premise"


def _clean(name: str) -> str:
    """Read an env var, tolerating trailing spaces in the key and quotes in the value."""
    for key in (name, f"{name} "):
        val = os.environ.get(key)
        if val:
            return val.strip().strip('"').strip("'")
    raise RuntimeError(f"Missing {name} in .env")


def build_uri() -> str:
    user = urllib.parse.quote_plus(_clean("DB_USERNAME"))
    pwd = urllib.parse.quote_plus(_clean("DB_PASSWORD"))
    return (
        f"mongodb+srv://{user}:{pwd}@{CLUSTER_HOST}/"
        f"?retryWrites=true&w=majority&appName=Cluster0"
    )


_client: AsyncIOMotorClient | None = None


def client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(build_uri(), serverSelectionTimeoutMS=8000)
    return _client


def db():
    return client()[DB_NAME]


# Collection handles. Named to match BUILD_PLAN.md §4.
def sites():
    return db()["sites"]


def premises():
    return db()["premises"]


def conclusions():
    return db()["conclusions"]


def events():
    return db()["events"]


def actions():
    return db()["actions"]


def revisions():
    return db()["revisions"]


def allocations():
    return db()["allocations"]
