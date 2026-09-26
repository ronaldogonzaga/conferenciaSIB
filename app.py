from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from config import Config
from db import test_connection
from validators.corrections import apply_fix, fix_meta, preview_fix
from validators.sib_rules import count_rule, dashboard_totals, detail_rule, list_rules, summarize_all

app = Flask(__name__)
app.config.from_object(Config)


@app.get("/")
def index():
    return render_template("index.html", app_version=Config.APP_VERSION)


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
        return jsonify({"ok": True, "totals": dashboard_totals()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/rules")
def api_rules():
    return jsonify({"ok": True, "rules": list_rules()})


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
    print("  Conferência SIB/ANS v%s — http://127.0.0.1:%s" % (Config.APP_VERSION, Config.FLASK_PORT))
    print("  Banco: %s@%s:%s/%s" % (Config.DB_USER, Config.DB_HOST, Config.DB_PORT, Config.DB_NAME))
    print("=" * 60)
    app.run(host="127.0.0.1", port=Config.FLASK_PORT, debug=Config.FLASK_DEBUG)
