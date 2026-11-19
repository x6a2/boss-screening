"""SQLite 存储。只存本地，不做任何网络同步。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import Candidate, ScoreResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    uid        TEXT PRIMARY KEY,
    name       TEXT,
    data       TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scores (
    uid            TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    total          REAL NOT NULL,
    passed_must    INTEGER NOT NULL,
    detail         TEXT NOT NULL,
    scored_at      TEXT NOT NULL,
    PRIMARY KEY (uid, requirement_id)
);
CREATE TABLE IF NOT EXISTS requirements (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    definition TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = "data/bosscreen.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # --- candidates ---------------------------------------------------
    def upsert_candidates(self, cands: list[Candidate]) -> int:
        now = _now()
        written = 0
        for c in cands:
            data = json.dumps(asdict(c), ensure_ascii=False)
            row = self.conn.execute("SELECT uid FROM candidates WHERE uid=?", (c.uid,)).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE candidates SET name=?, data=?, last_seen=? WHERE uid=?",
                    (c.name, data, now, c.uid),
                )
            else:
                self.conn.execute(
                    "INSERT INTO candidates(uid, name, data, first_seen, last_seen) VALUES (?,?,?,?,?)",
                    (c.uid, c.name, data, now, now),
                )
            written += 1
        self.conn.commit()
        return written

    def load_candidates(self) -> list[Candidate]:
        rows = self.conn.execute("SELECT data FROM candidates ORDER BY last_seen DESC").fetchall()
        out = []
        for r in rows:
            d = json.loads(r["data"])
            out.append(Candidate(**d))
        return out

    # --- scores -------------------------------------------------------
    def save_scores(self, req_id: str, results: list[ScoreResult]) -> int:
        now = _now()
        for r in results:
            self.conn.execute(
                "INSERT OR REPLACE INTO scores(uid, requirement_id, total, passed_must, detail, scored_at)"
                " VALUES (?,?,?,?,?,?)",
                (r.uid, req_id, r.total, int(r.passed_must), json.dumps(asdict(r), ensure_ascii=False), now),
            )
        self.conn.commit()
        return len(results)

    def list_scores(self, req_id: str) -> list[ScoreResult]:
        rows = self.conn.execute(
            "SELECT detail FROM scores WHERE requirement_id=? ORDER BY passed_must DESC, total DESC",
            (req_id,),
        ).fetchall()
        return [ScoreResult(**json.loads(r["detail"])) for r in rows]

    # --- requirements -------------------------------------------------
    def save_requirement(self, req_id: str, name: str, definition: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO requirements(id, name, definition, created_at) VALUES (?,?,?,?)",
            (req_id, name, json.dumps(definition, ensure_ascii=False), _now()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
