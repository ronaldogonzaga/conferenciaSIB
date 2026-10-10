"""Controle local (SQLite) de correções aguardando retorno da confsib (30+ dias)."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from config import Config

# Regras cuja correção envia movimento SIB e só reflete na confsib após processamento ANS.
AWAIT_CONFSIB_RULES: dict[str, dict[str, Any]] = {
    "ativo_inativo_confsib_reinclusao": {
        "label": "Aguardando retorno confsib (reinclusão)",
        "expect_status": "A",
        "posans_aplicado": "8-REINCLUSAO",
        "wait_days": None,  # usa Config.PENDING_CONFSIB_WAIT_DAYS
    },
    "inativo_cadusu_ativo_confsib": {
        "label": "Aguardando retorno confsib (exclusão)",
        "expect_status": "I",
        "posans_aplicado": "3-EXCLUSAO",
        "wait_days": None,
    },
}


def is_await_rule(rule_id: str) -> bool:
    return rule_id in AWAIT_CONFSIB_RULES


def _db_path() -> Path:
    path = Path(Config.PENDING_CONFSIB_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _conn():
    path = _db_path()
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        _ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_confsib (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cadusu_id INTEGER NOT NULL,
            rule_id TEXT NOT NULL,
            codcco TEXT,
            posans_aplicado TEXT,
            status TEXT NOT NULL DEFAULT 'aguardando',
            applied_at TEXT NOT NULL,
            wait_until TEXT NOT NULL,
            resolved_at TEXT,
            note TEXT,
            UNIQUE (cadusu_id, rule_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pending_rule_status
        ON pending_confsib (rule_id, status)
        """
    )


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _wait_days(rule_id: str) -> int:
    meta = AWAIT_CONFSIB_RULES.get(rule_id) or {}
    return int(meta.get("wait_days") or Config.PENDING_CONFSIB_WAIT_DAYS)


def register_pending(
    rule_id: str,
    rows: Iterable[dict[str, Any]],
    *,
    note: str | None = None,
) -> int:
    """Registra (ou renova) pendências após UPDATE bem-sucedido. Retorna qtd gravada."""
    if not is_await_rule(rule_id):
        return 0

    meta = AWAIT_CONFSIB_RULES[rule_id]
    now = _now()
    wait_until = now + timedelta(days=_wait_days(rule_id))
    note_txt = note or meta["label"]
    registered = 0

    with _conn() as conn:
        for row in rows:
            cadusu_id = int(row["id"])
            codcco = row.get("codcco")
            posans = row.get("posans") or meta.get("posans_aplicado")
            conn.execute(
                """
                INSERT INTO pending_confsib (
                    cadusu_id, rule_id, codcco, posans_aplicado,
                    status, applied_at, wait_until, resolved_at, note
                ) VALUES (?, ?, ?, ?, 'aguardando', ?, ?, NULL, ?)
                ON CONFLICT(cadusu_id, rule_id) DO UPDATE SET
                    codcco = excluded.codcco,
                    posans_aplicado = excluded.posans_aplicado,
                    status = 'aguardando',
                    applied_at = excluded.applied_at,
                    wait_until = excluded.wait_until,
                    resolved_at = NULL,
                    note = excluded.note
                """,
                (
                    cadusu_id,
                    rule_id,
                    None if codcco is None else str(codcco).strip(),
                    None if posans is None else str(posans),
                    _iso(now),
                    _iso(wait_until),
                    note_txt,
                ),
            )
            registered += 1
    return registered


def active_pending_ids(rule_id: str | None = None) -> list[int]:
    """IDs em status aguardando (ainda dentro da janela ou sem expirar automaticamente)."""
    _expire_elapsed()
    sql = """
        SELECT cadusu_id
        FROM pending_confsib
        WHERE status = 'aguardando'
    """
    params: list[Any] = []
    if rule_id:
        sql += " AND rule_id = ?"
        params.append(rule_id)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return sorted({int(r["cadusu_id"]) for r in rows})


def _expire_elapsed() -> int:
    """Marca como expirado quem passou de wait_until (voltam a poder ser listados)."""
    now = _iso(_now())
    with _conn() as conn:
        cur = conn.execute(
            """
            UPDATE pending_confsib
               SET status = 'expirado',
                   resolved_at = ?
             WHERE status = 'aguardando'
               AND wait_until < ?
            """,
            (now, now),
        )
        return int(cur.rowcount or 0)


def resolve_ids(
    rule_id: str,
    ids: Iterable[int],
    *,
    status: str = "resolvido",
    note: str | None = None,
) -> int:
    id_list = sorted({int(i) for i in ids})
    if not id_list:
        return 0
    now = _iso(_now())
    placeholders = ",".join("?" for _ in id_list)
    with _conn() as conn:
        cur = conn.execute(
            f"""
            UPDATE pending_confsib
               SET status = ?,
                   resolved_at = ?,
                   note = COALESCE(?, note)
             WHERE rule_id = ?
               AND status = 'aguardando'
               AND cadusu_id IN ({placeholders})
            """,
            [status, now, note, rule_id, *id_list],
        )
        return int(cur.rowcount or 0)


def list_pending(
    *,
    rule_id: str | None = None,
    status: str | None = "aguardando",
    limit: int = 500,
) -> list[dict[str, Any]]:
    _expire_elapsed()
    sql = "SELECT * FROM pending_confsib WHERE 1=1"
    params: list[Any] = []
    if rule_id:
        sql += " AND rule_id = ?"
        params.append(rule_id)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY applied_at DESC LIMIT ?"
    params.append(int(limit))
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def pending_summary() -> dict[str, Any]:
    _expire_elapsed()
    with _conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM pending_confsib WHERE status = 'aguardando'"
        ).fetchone()["n"]
        by_rule = conn.execute(
            """
            SELECT rule_id, COUNT(*) AS total
            FROM pending_confsib
            WHERE status = 'aguardando'
            GROUP BY rule_id
            ORDER BY rule_id
            """
        ).fetchall()
    return {
        "total_aguardando": int(total),
        "wait_days": Config.PENDING_CONFSIB_WAIT_DAYS,
        "by_rule": [
            {
                "rule_id": r["rule_id"],
                "total": int(r["total"]),
                "label": (AWAIT_CONFSIB_RULES.get(r["rule_id"]) or {}).get(
                    "label", r["rule_id"]
                ),
            }
            for r in by_rule
        ],
    }


_ORDER_OR_LIMIT = re.compile(r"\b(ORDER\s+BY|LIMIT|RETURNING)\b", re.IGNORECASE)


def sql_exclude_pending(rule_id: str, id_expr: str = "c.id") -> str:
    """Cláusula AND ... para embutir em SQL PostgreSQL (só ints)."""
    if not is_await_rule(rule_id):
        return ""
    ids = active_pending_ids(rule_id)
    if not ids:
        return ""
    return f" AND {id_expr} NOT IN ({','.join(str(i) for i in ids)})"


def inject_pending_exclusion(sql: str, rule_id: str, id_expr: str = "c.id") -> str:
    """Insere exclusão de IDs pendentes antes de ORDER BY / LIMIT / RETURNING."""
    clause = sql_exclude_pending(rule_id, id_expr=id_expr)
    if not clause:
        return sql
    m = _ORDER_OR_LIMIT.search(sql)
    if not m:
        return sql.rstrip() + "\n" + clause + "\n"
    return sql[: m.start()] + clause + "\n" + sql[m.start() :]
