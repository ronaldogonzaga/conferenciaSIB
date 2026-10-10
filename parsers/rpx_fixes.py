"""Aplicação de correções na cadusu a partir de críticas do retorno .RPX."""

from __future__ import annotations

from typing import Any

from db import execute_returning, fetch_all
from parsers.rpx_retorno import suggest_for_error

_AUDIT = "dataultalt = CURRENT_DATE, dtope = CURRENT_TIMESTAMP"

# Ações automáticas suportadas (chave = fix_action do ERROR_SUGGESTIONS).
FIX_ACTIONS: dict[str, dict[str, Any]] = {
    "posans_atualizado": {
        "label": "Marcar posans = 4-ATUALIZADO",
        "summary": (
            "Atualiza cadusu.posans para 4-ATUALIZADO nos CCOs rejeitados "
            "que ainda não estão conciliados (evita reenvio inútil à ANS)."
        ),
        "confirm_detail": "Esta ação grava posans = 4-ATUALIZADO no PostgreSQL.",
        "posans_novo": "4-ATUALIZADO",
    },
    "posans_inclusao": {
        "label": "Corrigir para inclusão (posans = 1-INCLUSAO)",
        "summary": (
            "Reativação/reinclusão bloqueada pelo motivo de cancelamento na ANS. "
            "Limpa o CCO antigo e define posans = 1-INCLUSAO para enviar como "
            "nova inclusão."
        ),
        "confirm_detail": (
            "Esta ação grava posans = 1-INCLUSAO e limpa codcco "
            "(nova inclusão SIB) no PostgreSQL."
        ),
        "posans_novo": "1-INCLUSAO",
        "clear_cco": True,
    },
}


def _norm_ccos(ccos: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in ccos or []:
        cco = str(raw or "").strip()
        if not cco or cco in seen:
            continue
        seen.add(cco)
        out.append(cco)
    return out


def _resolve_action(codigo_erro: str) -> tuple[dict[str, Any], dict[str, Any]]:
    code = (codigo_erro or "").strip()
    sug = suggest_for_error(code)
    if not sug.get("fixable"):
        raise ValueError(f"Crítica {code} não possui correção automática.")
    action_key = sug.get("fix_action") or ""
    action = FIX_ACTIONS.get(action_key)
    if not action:
        raise ValueError(f"Ação de correção '{action_key}' não implementada.")
    return sug, {**action, "key": action_key, "codigo_erro": code}


def _preview_rows(action: dict[str, Any], cco_list: list[str]) -> list[dict[str, Any]]:
    key = action["key"]
    if key == "posans_atualizado":
        return fetch_all(
            """
            SELECT id, codtit, codusu, nomeusu, situusu, codcco,
                   posans AS posans_atual,
                   %s::varchar AS posans_novo,
                   TRIM(codcco) AS cco_ref
            FROM cadusu
            WHERE TRIM(codcco) = ANY(%s)
              AND COALESCE(TRIM(posans), '') <> %s
            ORDER BY id
            """,
            (action["posans_novo"], cco_list, action["posans_novo"]),
        )

    if key == "posans_inclusao":
        return fetch_all(
            """
            SELECT id, codtit, codusu, nomeusu, situusu, codcco,
                   posans AS posans_atual,
                   %s::varchar AS posans_novo,
                   ''::varchar AS codcco_novo,
                   TRIM(codcco) AS cco_ref
            FROM cadusu
            WHERE TRIM(codcco) = ANY(%s)
              AND situusu = 'ATIVO'
              AND posans IN ('8-REINCLUSAO', '9-RET REATIV')
            ORDER BY id
            """,
            (action["posans_novo"], cco_list),
        )

    raise ValueError(f"Preview não implementado para ação '{key}'.")


def preview_rpx_fix(codigo_erro: str, ccos: list[Any]) -> dict[str, Any]:
    sug, action = _resolve_action(codigo_erro)
    cco_list = _norm_ccos(ccos)
    if not cco_list:
        raise ValueError("Nenhum CCO informado para a correção.")

    rows = _preview_rows(action, cco_list)
    columns = [
        "id",
        "codtit",
        "codusu",
        "nomeusu",
        "situusu",
        "codcco",
        "posans_atual",
        "posans_novo",
    ]
    if action.get("clear_cco"):
        columns.insert(columns.index("posans_atual"), "codcco_novo")

    return {
        "codigo_erro": action["codigo_erro"],
        "fixable": True,
        "fix_action": action["key"],
        "label": action["label"],
        "summary": action["summary"],
        "confirm_detail": action.get("confirm_detail") or action["summary"],
        "titulo": sug.get("titulo") or "",
        "total_ccos": len(cco_list),
        "total_eligible": len(rows),
        "columns": columns,
        "rows": rows,
    }


def apply_rpx_fix(
    codigo_erro: str,
    ccos: list[Any],
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Confirme a correção com confirm=true.")

    preview = preview_rpx_fix(codigo_erro, ccos)
    ids = [int(r["id"]) for r in preview["rows"]]
    cco_refs = [
        str(r.get("cco_ref") or r.get("codcco") or "").strip()
        for r in preview["rows"]
        if str(r.get("cco_ref") or r.get("codcco") or "").strip()
    ]
    base = {
        "codigo_erro": preview["codigo_erro"],
        "label": preview["label"],
        "summary": preview["summary"],
        "fix_action": preview["fix_action"],
        "confirm_detail": preview.get("confirm_detail"),
    }
    if not ids:
        return {**base, "requested": 0, "updated": 0, "rows": [], "cco_refs": []}

    action = FIX_ACTIONS[preview["fix_action"]]
    key = preview["fix_action"]

    if key == "posans_atualizado":
        updated = execute_returning(
            f"""
            UPDATE cadusu SET
                posans = %s,
                {_AUDIT}
            WHERE id = ANY(%s)
              AND COALESCE(TRIM(posans), '') <> %s
            RETURNING id, codtit, codusu, nomeusu, situusu, codcco, posans
            """,
            (action["posans_novo"], ids, action["posans_novo"]),
        )
    elif key == "posans_inclusao":
        updated = execute_returning(
            f"""
            UPDATE cadusu SET
                posans = %s,
                codcco = NULL,
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'ATIVO'
              AND posans IN ('8-REINCLUSAO', '9-RET REATIV')
            RETURNING id, codtit, codusu, nomeusu, situusu, codcco, posans
            """,
            (action["posans_novo"], ids),
        )
    else:
        raise ValueError(f"Apply não implementado para ação '{key}'.")

    return {
        **base,
        "requested": len(ids),
        "updated": len(updated),
        "rows": updated,
        "cco_refs": cco_refs,
        "posans_novo": action["posans_novo"],
        "cleared_cco": bool(action.get("clear_cco")),
    }
