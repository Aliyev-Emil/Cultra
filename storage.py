"""Saves the app's data, so accounts, balances and history survive a restart.

main.py keeps working with plain Python dicts and lists, exactly like before. On start-up it reads
them back from here (load_all), and after every request that changed something it hands the
changed parts to save().

Where the data is kept:
  - DATABASE_URL is set (on Render: your Supabase connection string)  ->  that PostgreSQL database
  - DATABASE_URL is not set (your laptop)                              ->  the file cultra.db next to main.py

Both use one table, cultra_data, with one row per part of the data:

    name                 data (the dict/list as JSON text)          saved_at
    "users"              {"123": {"username": "Emil", ...}, ...}   2026-10-14 ...
    "bankcards"          ...
    "transactions"       [ ... ]

Test the connection without starting the server:   python storage.py
"""
import os
import sqlite3
import ssl
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

TABLE = "cultra_data"
LOCAL_FILE = Path(__file__).resolve().parent / "cultra.db"


class SqliteStore:
    """A file on this computer. Nothing to set up: Python has SQLite built in."""

    kind = "SQLite"

    def __init__(self, path):
        self.where = str(path)
        # check_same_thread=False: main.py saves from a helper thread (one save at a time)
        self.db = sqlite3.connect(path, check_same_thread=False)
        with self.db:
            self.db.execute(
                f"CREATE TABLE IF NOT EXISTS {TABLE} ("
                " name TEXT PRIMARY KEY,"
                " data TEXT NOT NULL,"
                " saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def load_all(self):
        """{"users": "<json text>", ...} - empty the very first time."""
        return dict(self.db.execute(f"SELECT name, data FROM {TABLE}").fetchall())

    def save(self, parts):
        """parts = {"users": "<json text>", ...}. All of them are saved, or none (one transaction)."""
        with self.db:
            self.db.executemany(
                f"INSERT INTO {TABLE} (name, data) VALUES (?, ?)"
                " ON CONFLICT (name) DO UPDATE SET data = excluded.data, saved_at = CURRENT_TIMESTAMP",
                list(parts.items()),
            )


class PostgresStore:
    """An online PostgreSQL database (Supabase), reached with the pure-Python driver pg8000."""

    kind = "PostgreSQL"

    def __init__(self, url):
        address = urlparse(url)
        options = parse_qs(address.query)

        if options.get("sslmode", [""])[0] == "disable":
            tls = False                    # only for a database without SSL on your own computer
        else:
            # Encrypted. The certificate isn't checked against a list of trusted ones, because
            # Supabase signs it with its own certificate authority (like sslmode=require).
            tls = ssl.create_default_context()
            tls.check_hostname = False
            tls.verify_mode = ssl.CERT_NONE

        self.settings = {
            "user": unquote(address.username or "postgres"),
            "password": unquote(address.password or ""),
            "host": address.hostname or "localhost",
            "port": address.port or 5432,
            "database": unquote(address.path.lstrip("/")) or "postgres",
            "ssl_context": tls,
            "timeout": 20,                 # seconds: give up instead of hanging forever
            "application_name": "cultra",
        }
        # For messages and logs. Never the password.
        self.where = f"{self.settings['host']}:{self.settings['port']}/{self.settings['database']}"
        self.connection = None

        # The database may need a moment (Render can start the server before its network is ready)
        for attempt in range(1, 4):
            try:
                self._run(self._create_table)
                return
            except Exception as error:
                if attempt == 3:
                    raise
                print(f"Database not reachable yet ({describe(error)}), trying again...", flush=True)
                time.sleep(3 * attempt)

    @staticmethod
    def _create_table(con):
        con.run(
            f"CREATE TABLE IF NOT EXISTS {TABLE} ("
            " name TEXT PRIMARY KEY,"
            " data TEXT NOT NULL,"
            " saved_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        # Supabase also puts every table in the public schema on its web API. Row Level Security
        # with no rules = that API can't read or change this table. The server isn't affected:
        # it logs in as the table's owner.
        con.run(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")

    def _run(self, work):
        """Runs work(connection). If the connection broke (poolers close idle ones), it opens a new
        one and tries once more. The work must be safe to repeat - saving the same data is."""
        for attempt in (1, 2):
            try:
                if self.connection is None:
                    import pg8000.native   # only needed when DATABASE_URL is set
                    self.connection = pg8000.native.Connection(**self.settings)
                return work(self.connection)
            except Exception:
                self._close()
                if attempt == 2:
                    raise

    def _close(self):
        try:
            if self.connection is not None:
                self.connection.close()
        except Exception:
            pass                           # it's broken anyway
        self.connection = None

    def load_all(self):
        rows = self._run(lambda con: con.run(f"SELECT name, data FROM {TABLE}"))
        return {name: data for name, data in rows}

    def save(self, parts):
        def work(con):
            con.run("START TRANSACTION")   # all parts or none
            for name, data in parts.items():
                con.run(
                    f"INSERT INTO {TABLE} (name, data) VALUES (:name, :data)"
                    " ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data, saved_at = now()",
                    name=name, data=data,
                )
            con.run("COMMIT")

        self._run(work)


def describe(error):
    """Short text for an error, without the connection string (it contains the password)."""
    text = f"{type(error).__name__}: {error}"
    url = os.environ.get("DATABASE_URL", "")
    password = unquote(urlparse(url).password or "") if url else ""
    if password:
        text = text.replace(password, "***")
    return text[:300]


def open_store():
    """The store main.py saves into: PostgreSQL when DATABASE_URL is set, otherwise cultra.db."""
    url = os.environ.get("DATABASE_URL", "").strip()

    if not url:
        return SqliteStore(LOCAL_FILE)

    if not url.startswith(("postgresql://", "postgres://")):
        raise ValueError(
            "DATABASE_URL must start with postgresql:// - copy it from Supabase: "
            "Connect > Session pooler, and put your database password in place of [YOUR-PASSWORD]"
        )
    if "[YOUR-PASSWORD]" in url:
        raise ValueError("DATABASE_URL still says [YOUR-PASSWORD]: put your database password there")

    return PostgresStore(url)


if __name__ == "__main__":
    # python storage.py  ->  checks the connection and shows what's saved, without starting the server
    try:
        store = open_store()
        parts = store.load_all()
    except Exception as error:
        print("Could not use the database:", describe(error))
        sys.exit(1)

    print(f"OK: {store.kind} ({store.where})")
    if parts:
        for name, data in sorted(parts.items()):
            print(f"  {name}: {len(data):,} characters")
    else:
        print("  Empty. The server fills it with the demo data the first time it starts.")
