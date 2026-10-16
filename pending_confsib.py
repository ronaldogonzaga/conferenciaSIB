"""Controle local (SQLite) de correções aguardando retorno da confsib (30+ dias)."""

from __future__ import annotations

import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from config import Config
from db import fetch_all, fetch_one

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

_META_MAX_NUMSEQ = "last_confsib_numseq"
_SYNC_TTL_SEC = 5.0
_last_sync: dict[str, Any] | None = None
_last_sync_at = 0.0


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
            baseline_numseq INTEGER,
            UNIQUE (cadusu_id, rule_id)
        )
        """
    )
    cols = {
        str(r[1])
        for r in conn.execute("PRAGMA table_info(pending_confsib)").fetchall()
    }
    if "baseline_numseq" not in cols:
        conn.execute(
            "ALTER TABLE pending_confsib ADD COLUMN baseline_numseq INTEGER"
        )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pending_rule_status
        ON pending_confsib (rule_id, status)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _wait_days(rule_id: str) -> int:
    meta = AWAIT_CONFSIB_RULES.get(rule_id) or {}
    return int(meta.get("wait_days") or Config.PENDING_CONFSIB_WAIT_DAYS)


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM app_meta WHERE key = ?", (key,)
    ).fetchone()
    return None if row is None else str(row["value"])


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_meta (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, _iso(_now())),
    )


def fetch_confsib_max_numseq() -> int | None:
    row = fetch_one("SELECT MAX(numseq) AS max_numseq FROM confsib")
    if not row or row.get("max_numseq") is None:
        return None
    return int(row["max_numseq"])


def fetch_latest_confsib_by_ccos(
    codccos: Iterable[str],
) -> dict[str, dict[str, Any]]:
    keys = sorted({str(c).strip() for c in codccos if c and str(c).strip()})
    if not keys:
        return {}
    rows = fetch_all(
        """
        SELECT DISTINCT ON (TRIM(s.codcco))
               TRIM(s.codcco) AS codcco,
               s.numseq AS numseq,
               TRIM(s.status) AS status
        FROM confsib s
        WHERE TRIM(s.codcco) = ANY(%s)
        ORDER BY TRIM(s.codcco), s.numseq DESC
        """,
        (keys,),
    )
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        codcco = str(r["codcco"]).strip()
        out[codcco] = {
            "codcco": codcco,
            "numseq": int(r["numseq"]) if r.get("numseq") is not None else None,
            "status": (str(r["status"]).strip() if r.get("status") is not None else ""),
        }
    return out


def _auto_resolve_reflected(conn: sqlite3.Connection) -> int:
    """Resolve pendências cujo CCO já refletiu expect_status com numseq > baseline."""
    rows = conn.execute(
        """
        SELECT id, cadusu_id, rule_id, codcco, baseline_numseq
        FROM pending_confsib
        WHERE status = 'aguardando'
          AND COALESCE(TRIM(codcco), '') <> ''
        """
    ).fetchall()
    if not rows:
        return 0

    latest = fetch_latest_confsib_by_ccos(r["codcco"] for r in rows)
    now = _iso(_now())
    resolved = 0

    for r in rows:
        meta = AWAIT_CONFSIB_RULES.get(r["rule_id"]) or {}
        expect = str(meta.get("expect_status") or "").strip().upper()
        if not expect:
            continue
        codcco = str(r["codcco"]).strip()
        cur = latest.get(codcco)
        if not cur or cur.get("numseq") is None:
            continue
        if str(cur.get("status") or "").strip().upper() != expect:
            continue
        baseline = r["baseline_numseq"]
        if baseline is not None and int(cur["numseq"]) <= int(baseline):
            continue
        note = (
            f"auto: confsib status={cur['status']} numseq={cur['numseq']}"
            + (f" > baseline={baseline}" if baseline is not None else " (sem baseline)")
        )
        cur_upd = conn.execute(
            """
            UPDATE pending_confsib
               SET status = 'resolvido',
                   resolved_at = ?,
                   note = ?
             WHERE id = ?
               AND status = 'aguardando'
            """,
            (now, note, int(r["id"])),
        )
        resolved += int(cur_upd.rowcount or 0)
    return resolved


def sync_confsib_state(*, force: bool = False) -> dict[str, Any]:
    """
    Lê MAX(numseq) da confsib, atualiza watermark local e auto-resolve pendências
    cujo retorno ANS já refletiu o status esperado.
    """
    global _last_sync, _last_sync_at
    now_mono = time.monotonic()
    if (
        not force
        and _last_sync is not None
        and (now_mono - _last_sync_at) < _SYNC_TTL_SEC
    ):
        return _last_sync

    current_max = fetch_confsib_max_numseq()
    with _conn() as conn:
        prev_raw = _meta_get(conn, _META_MAX_NUMSEQ)
        previous_max = int(prev_raw) if prev_raw and prev_raw.isdigit() else None
        refreshed = (
            previous_max is not None
            and current_max is not None
            and current_max > previous_max
        )
        # Reavalia sempre: o MAX global só indica carga; a resolução é por CCO.
        auto_resolved = _auto_resolve_reflected(conn)
        if current_max is not None:
            _meta_set(conn, _META_MAX_NUMSEQ, str(current_max))

    result = {
        "confsib_max_numseq": current_max,
        "previous_max_numseq": previous_max,
        "confsib_refreshed": bool(refreshed),
        "auto_resolved": int(auto_resolved),
        "checked_at": _iso(_now()),
    }
    _last_sync = result
    _last_sync_at = now_mono
    return result


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
    row_list = list(rows)
    baselines = fetch_latest_confsib_by_ccos(
        r.get("codcco") for r in row_list if r.get("codcco")
    )
    registered = 0

    with _conn() as conn:
        for row in row_list:
            cadusu_id = int(row["id"])
            codcco = row.get("codcco")
            codcco_txt = None if codcco is None else str(codcco).strip()
            posans = row.get("posans") or meta.get("posans_aplicado")
            baseline = None
            if codcco_txt and codcco_txt in baselines:
                baseline = baselines[codcco_txt].get("numseq")
            conn.execute(
                """
                INSERT INTO pending_confsib (
                    cadusu_id, rule_id, codcco, posans_aplicado,
                    status, applied_at, wait_until, resolved_at, note,
                    baseline_numseq
                ) VALUES (?, ?, ?, ?, 'aguardando', ?, ?, NULL, ?, ?)
                ON CONFLICT(cadusu_id, rule_id) DO UPDATE SET
                    codcco = excluded.codcco,
                    posans_aplicado = excluded.posans_aplicado,
                    status = 'aguardando',
                    applied_at = excluded.applied_at,
                    wait_until = excluded.wait_until,
                    resolved_at = NULL,
                    note = excluded.note,
                    baseline_numseq = excluded.baseline_numseq
                """,
                (
                    cadusu_id,
                    rule_id,
                    codcco_txt or None,
                    None if posans is None else str(posans),
                    _iso(now),
                    _iso(wait_until),
                    note_txt,
                    baseline,
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
    try:
        sync_confsib_state()
    except Exception:
        # Listagem local não deve falhar se o Postgres estiver indisponível.
        pass
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
    sync_info: dict[str, Any] = {}
    try:
        sync_info = sync_confsib_state()
    except Exception as exc:
        sync_info = {
            "confsib_max_numseq": None,
            "previous_max_numseq": None,
            "confsib_refreshed": False,
            "auto_resolved": 0,
            "sync_error": str(exc),
        }
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
        "confsib_max_numseq": sync_info.get("confsib_max_numseq"),
        "previous_max_numseq": sync_info.get("previous_max_numseq"),
        "confsib_refreshed": bool(sync_info.get("confsib_refreshed")),
        "auto_resolved": int(sync_info.get("auto_resolved") or 0),
        "checked_at": sync_info.get("checked_at"),
        "sync_error": sync_info.get("sync_error"),
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
