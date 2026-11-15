"""SQLite storage. One process-wide connection guarded by an RLock (fine for a demo-scale service)."""
import os
import sqlite3
import threading
import time

_lock = threading.RLock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases(
  id TEXT PRIMARY KEY, name TEXT, leaver TEXT, last_day TEXT, created REAL, touched REAL, demo INTEGER DEFAULT 0, reconstructed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sources(
  id TEXT, case_id TEXT, name TEXT, kind TEXT, acl TEXT, text TEXT, redactions INTEGER DEFAULT 0,
  included INTEGER DEFAULT 1, origin TEXT, added REAL, PRIMARY KEY(case_id,id));
CREATE TABLE IF NOT EXISTS claims(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, num INTEGER, key TEXT, type TEXT, text TEXT, state TEXT,
  confidence REAL, owner TEXT, status TEXT DEFAULT 'pending', version INTEGER DEFAULT 1, level INTEGER,
  evidence TEXT, meta TEXT, fp TEXT, date TEXT, created REAL, updated REAL, UNIQUE(case_id,key), UNIQUE(case_id,num));
CREATE TABLE IF NOT EXISTS claim_versions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, num INTEGER, version INTEGER, text TEXT, state TEXT,
  status TEXT, actor TEXT, action TEXT, at REAL);
CREATE TABLE IF NOT EXISTS testimony(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, key TEXT, author TEXT, answer TEXT, choice TEXT, at REAL);
CREATE TABLE IF NOT EXISTS resolutions(case_id TEXT, key TEXT, choice TEXT, actor TEXT, at REAL, PRIMARY KEY(case_id,key));
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, seq INTEGER, at REAL, actor TEXT, action TEXT, ref TEXT,
  snap TEXT, prev TEXT, hash TEXT, UNIQUE(case_id,seq));
CREATE TABLE IF NOT EXISTS acks(case_id TEXT, name TEXT, role TEXT, version INTEGER, at REAL);
"""


def init(path: str | None = None):
    """(Re)initialise the database. ':memory:' gives a throwaway DB (tests)."""
    global _conn
    path = path or os.environ.get("BATON_DB", "baton.db")
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys=ON")
        if path != ":memory:":
            _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
        _conn.commit()


def _c():
    if _conn is None:
        init()
    return _conn


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in _c().execute(sql, args).fetchall()]


def one(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def run(sql, args=()):
    with _lock:
        cur = _c().execute(sql, args)
        _c().commit()
        return cur.lastrowid


def tx():
    """Context manager: group several writes into one commit."""
    return _Tx()


class _Tx:
    def __enter__(self):
        _lock.acquire()
        _c().execute("BEGIN")
        return _c()

    def __exit__(self, et, ev, tb):
        try:
            _c().commit() if et is None else _c().rollback()
        finally:
            _lock.release()


def purge_old(hours: float = 24):
    cutoff = time.time() - hours * 3600
    old = [r["id"] for r in q("SELECT id FROM cases WHERE touched < ? AND demo = 0", (cutoff,))]
    old += [r["id"] for r in q("SELECT id FROM cases WHERE touched < ? AND demo = 1", (cutoff,))]
    for cid in set(old):
        delete_case(cid)


def delete_case(cid: str):
    with tx() as c:
        for t in ("claims", "claim_versions", "testimony", "resolutions", "audit", "acks", "sources"):
            c.execute(f"DELETE FROM {t} WHERE case_id=?", (cid,))
        c.execute("DELETE FROM cases WHERE id=?", (cid,))
