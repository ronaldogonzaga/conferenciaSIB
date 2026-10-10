from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from config import Config
from db import fetch_all, test_connection
from parsers.rpx_fixes import apply_rpx_fix, preview_rpx_fix
from parsers.rpx_retorno import parse_rpx
from pending_confsib import list_pending, pending_summary, resolve_ids
from validators.corrections import apply_fix, fix_meta, preview_fix
from validators.sib_rules import count_rule, dashboard_totals, detail_rule, list_rules, summarize_all

app = Flask(__name__)
app.config.from_object(Config)


def _enrich_rpx_with_cadusu(parsed: dict) -> dict:
    """Anexa id/nome/posans/situusu da cadusu quando o CCO do retorno existe localmente."""
    rejeitados = parsed.get("rejeitados") or []
    ccos = sorted(
        {
            str(r.get("cco") or "").strip()
            for r in rejeitados
            if str(r.get("cco") or "").strip()
        }
    )
    by_cco: dict[str, dict] = {}
    if ccos:
        try:
            rows = fetch_all(
                """
                SELECT id, codtit, codusu, nomeusu, situusu, posans, codcco, datafim, dataini
                FROM cadusu
                WHERE TRIM(codcco) = ANY(%s)
                ORDER BY id
                """,
                (ccos,),
            )
            for row in rows:
                key = str(row.get("codcco") or "").strip()
                if key and key not in by_cco:
                    by_cco[key] = dict(row)
        except Exception:
            by_cco = {}

    for reg in rejeitados:
        local = by_cco.get(str(reg.get("cco") or "").strip())
        if local:
            reg["cadusu_id"] = local.get("id")
            reg["cadusu_nome"] = local.get("nomeusu")
            reg["cadusu_situusu"] = local.get("situusu")
            reg["cadusu_posans"] = local.get("posans")
            reg["cadusu_codusu"] = local.get("codusu")
            reg["cadusu_dataini"] = (
                local["dataini"].isoformat() if local.get("dataini") else None
            )
            reg["cadusu_datafim"] = (
                local["datafim"].isoformat() if local.get("datafim") else None
            )
        else:
            reg["cadusu_id"] = None
            reg["cadusu_nome"] = None
            reg["cadusu_situusu"] = None
            reg["cadusu_posans"] = None
            reg["cadusu_codusu"] = None
            reg["cadusu_dataini"] = None
            reg["cadusu_datafim"] = None

    max_rows = Config.RPX_MAX_ROWS
    parsed["rejeitados_truncated"] = len(rejeitados) > max_rows
    if parsed["rejeitados_truncated"]:
        parsed["rejeitados"] = rejeitados[:max_rows]
    parsed["matched_cadusu"] = sum(
        1 for r in parsed["rejeitados"] if r.get("cadusu_id")
    )
    return parsed


@app.get("/")
def index():
    return render_template(
        "index.html",
        app_version=Config.APP_VERSION,
        rpx_default_path=Config.RPX_DEFAULT_PATH,
    )


@app.get("/api/health")
def api_health():
    try:
        info = test_connection()
        return jsonify({"ok": True, "db": info, "version": Config.APP_VERSION})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "version": Config.APP_VERSION}), 500


@app.get("/api/dashboard")
def api_dashboard():
    try:
        totals = dashboard_totals()
        totals["pending_confsib"] = pending_summary()
        return jsonify({"ok": True, "totals": totals})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/pending-confsib")
def api_pending_confsib():
    try:
        rule_id = request.args.get("rule_id") or None
        status = request.args.get("status") or "aguardando"
        rows = list_pending(rule_id=rule_id, status=status)
        return jsonify(
            {
                "ok": True,
                "summary": pending_summary(),
                "rows": rows,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/pending-confsib/resolve")
def api_pending_confsib_resolve():
    body = request.get_json(silent=True) or {}
    rule_id = body.get("rule_id")
    ids = body.get("ids") or []
    if not rule_id:
        return jsonify({"ok": False, "error": "rule_id obrigatório"}), 400
    try:
        n = resolve_ids(rule_id, ids, note=body.get("note") or "resolvido manualmente")
        return jsonify({"ok": True, "resolved": n, "summary": pending_summary()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/rules")
def api_rules():
    rules = list_rules()
    for item in rules:
        item.update(fix_meta(item["id"]))
    return jsonify({"ok": True, "rules": rules})


@app.get("/api/rule/<rule_id>/count")
def api_rule_count(rule_id: str):
    try:
        data = count_rule(rule_id)
        data.update(fix_meta(rule_id))
        return jsonify({"ok": True, "data": data})
    except KeyError:
        return jsonify({"ok": False, "error": "Regra não encontrada"}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "data": {"id": rule_id, "total": -1, "ok": False}}), 500


@app.get("/api/summary")
def api_summary():
    try:
        items = summarize_all()
        for item in items:
            item.update(fix_meta(item["id"]))
        inconsistentes = sum(1 for i in items if i.get("total", 0) > 0)
        registros = sum(max(i.get("total", 0), 0) for i in items)
        return jsonify(
            {
                "ok": True,
                "summary": items,
                "meta": {
                    "regras": len(items),
                    "regras_com_inconsistencia": inconsistentes,
                    "total_registros_flagados": registros,
                },
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/rule/<rule_id>")
def api_rule_detail(rule_id: str):
    try:
        data = detail_rule(rule_id)
        data.update(fix_meta(rule_id))
        return jsonify({"ok": True, "data": data})
    except KeyError:
        return jsonify({"ok": False, "error": "Regra não encontrada"}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/rule/<rule_id>/fix/preview")
def api_fix_preview(rule_id: str):
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    try:
        data = preview_fix(rule_id, ids=ids)
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "meta": fix_meta(rule_id)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/rule/<rule_id>/fix/apply")
def api_fix_apply(rule_id: str):
    body = request.get_json(silent=True) or {}
    ids = body.get("ids") or []
    confirm = bool(body.get("confirm"))
    try:
        data = apply_fix(rule_id, ids=ids, confirm=confirm)
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/retorno/parse")
def api_retorno_parse():
    """Lê arquivo retorno SIB (.RPX) por caminho UNC/local ou upload."""
    try:
        uploaded = request.files.get("file")
        path = (request.form.get("path") or request.args.get("path") or "").strip()
        if request.is_json:
            body = request.get_json(silent=True) or {}
            path = (body.get("path") or path or "").strip()

        if uploaded and uploaded.filename:
            parsed = parse_rpx(fileobj=uploaded.stream, source_name=uploaded.filename)
        elif path:
            parsed = parse_rpx(path)
        else:
            return jsonify(
                {
                    "ok": False,
                    "error": "Informe o caminho do .RPX ou envie o arquivo.",
                }
            ), 400

        parsed = _enrich_rpx_with_cadusu(parsed)
        return jsonify({"ok": True, "data": parsed})
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/retorno/fix")
def api_retorno_fix():
    """Aplica correção automática de uma crítica do .RPX (ex.: 3005 → posans)."""
    body = request.get_json(silent=True) or {}
    codigo = (body.get("codigo_erro") or "").strip()
    ccos = body.get("ccos") or []
    confirm = bool(body.get("confirm"))
    if not codigo:
        return jsonify({"ok": False, "error": "codigo_erro obrigatório"}), 400
    try:
        if confirm:
            data = apply_rpx_fix(codigo, ccos, confirm=True)
        else:
            data = preview_rpx_fix(codigo, ccos)
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/export/<rule_id>")
def api_export(rule_id: str):
    import csv
    import io

    from flask import Response

    try:
        data = detail_rule(rule_id)
    except KeyError:
        return jsonify({"ok": False, "error": "Regra não encontrada"}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    buf = io.StringIO()
    cols = data["columns"]
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", delimiter=";")
    writer.writeheader()
    for row in data["rows"]:
        writer.writerow({k: row.get(k, "") for k in cols})

    filename = f"sib_{rule_id}.csv"
    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def create_app() -> Flask:
    return app


if __name__ == "__main__":
    print("=" * 60)
    print("  Conferência SIB/ANS v%s - http://127.0.0.1:%s" % (Config.APP_VERSION, Config.FLASK_PORT))
    print("  Banco: %s@%s:%s/%s" % (Config.DB_USER, Config.DB_HOST, Config.DB_PORT, Config.DB_NAME))
    print("=" * 60)
    app.run(host="127.0.0.1", port=Config.FLASK_PORT, debug=Config.FLASK_DEBUG)
