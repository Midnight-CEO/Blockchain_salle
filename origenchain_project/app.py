"""OrigenChain - demo web app for agricultural batch traceability."""
from __future__ import annotations

import io
import os
import secrets
from datetime import date
from pathlib import Path
from typing import Any

import qrcode
from flask import Flask, abort, jsonify, render_template, request, send_file

from blockchain import Blockchain

BASE_DIR = Path(__file__).resolve().parent
ALLOWED_PRODUCTS = {"Café", "Cacao"}
ALLOWED_ROLES = {
    "Productor", "Cooperativa", "Transportador", "Procesador", "Exportador", "Tostador"
}
ALLOWED_EVENT_TYPES = {
    "Recepción", "Despacho", "Control de calidad", "Transformación", "Entrega confirmada"
}


def _text(value: Any, field: str, max_length: int = 160, required: bool = True) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ValueError(f"El campo {field} es obligatorio.")
    if len(result) > max_length:
        raise ValueError(f"El campo {field} supera {max_length} caracteres.")
    return result


def create_app(db_path: str | Path | None = None, seed_demo: bool = True) -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
    app.config["PUBLIC_BASE_URL"] = os.environ.get("ORIGINCHAIN_PUBLIC_URL", "http://127.0.0.1:5000").rstrip("/")
    database_path = Path(db_path) if db_path else Path(
        os.environ.get("ORIGINCHAIN_DB", BASE_DIR / "instance" / "originchain.db")
    )
    ledger = Blockchain(database_path)
    app.extensions["originchain_ledger"] = ledger

    if seed_demo and not ledger.get_lots():
        _seed_demo(ledger)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/summary")
    def api_summary():
        lots = ledger.get_lots()
        integrity = ledger.verify()
        total_events = sum(max(0, len(lot["events"]) - 1) for lot in lots)
        return jsonify({
            "lots": len(lots),
            "events": total_events,
            "blocks": len(ledger.get_blocks()),
            "integrity": integrity,
            "recent_lots": lots[:5],
        })

    @app.get("/api/lots")
    def api_lots():
        search = request.args.get("search", "").strip().casefold()
        lots = ledger.get_lots()
        if search:
            lots = [lot for lot in lots if search in " ".join([
                lot.get("lot_id", ""), lot.get("lot_code", ""), lot.get("product", ""),
                lot.get("producer", ""), lot.get("origin", ""),
            ]).casefold()]
        return jsonify({"lots": lots})

    @app.post("/api/lots")
    def api_create_lot():
        payload = request.get_json(silent=True) or {}
        try:
            product = _text(payload.get("product"), "producto", 30)
            if product not in ALLOWED_PRODUCTS:
                raise ValueError("El producto debe ser Café o Cacao.")
            producer = _text(payload.get("producer"), "productor", 120)
            origin = _text(payload.get("origin"), "origen", 120)
            lot_code = _text(payload.get("lot_code"), "código del lote", 40)
            variety = _text(payload.get("variety"), "variedad", 80, required=False)
            harvest_date = _text(payload.get("harvest_date"), "fecha de cosecha", 10)
            date.fromisoformat(harvest_date)
            weight_kg = float(payload.get("weight_kg", 0))
            if not (0 < weight_kg <= 1_000_000):
                raise ValueError("El peso debe ser mayor que 0 y no superar 1.000.000 kg.")
            actor = _text(payload.get("actor", producer), "responsable", 100)
            role = _text(payload.get("role", "Productor"), "rol", 30)
            if role not in ALLOWED_ROLES:
                raise ValueError("Selecciona un rol válido.")
            notes = _text(payload.get("notes"), "notas", 300, required=False)

            if any(lot.get("lot_code", "").casefold() == lot_code.casefold() for lot in ledger.get_lots()):
                raise ValueError("Ya existe un lote con ese código.")

            lot_id = f"OC-{secrets.token_hex(4).upper()}"
            ledger.append({
                "type": "LOT_CREATED",
                "lot_id": lot_id,
                "actor": actor,
                "role": role,
                "details": {
                    "lot_code": lot_code,
                    "product": product,
                    "producer": producer,
                    "origin": origin,
                    "harvest_date": harvest_date,
                    "variety": variety,
                    "weight_kg": round(weight_kg, 2),
                    "notes": notes,
                },
            })
            return jsonify({"ok": True, "lot": ledger.get_lot(lot_id)}), 201
        except (ValueError, TypeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get("/api/lots/<lot_id>")
    def api_lot_detail(lot_id: str):
        lot = ledger.get_lot(lot_id)
        if not lot:
            return jsonify({"error": "No encontramos ese lote."}), 404
        return jsonify({"lot": lot})

    @app.post("/api/lots/<lot_id>/events")
    def api_add_event(lot_id: str):
        if not ledger.get_lot(lot_id):
            return jsonify({"ok": False, "error": "El lote no existe."}), 404
        payload = request.get_json(silent=True) or {}
        try:
            event_type = _text(payload.get("event_type"), "tipo de evento", 50)
            if event_type not in ALLOWED_EVENT_TYPES:
                raise ValueError("Selecciona un tipo de evento válido.")
            location = _text(payload.get("location"), "ubicación", 120)
            description = _text(payload.get("description"), "descripción", 300)
            actor = _text(payload.get("actor"), "responsable", 100)
            role = _text(payload.get("role"), "rol", 30)
            if role not in ALLOWED_ROLES:
                raise ValueError("Selecciona un rol válido.")
            block = ledger.append({
                "type": "TRACE_EVENT",
                "lot_id": lot_id,
                "event_type": event_type,
                "location": location,
                "description": description,
                "actor": actor,
                "role": role,
            })
            return jsonify({"ok": True, "block_index": block["index"], "lot": ledger.get_lot(lot_id)}), 201
        except (ValueError, TypeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get("/api/chain/verify")
    def api_verify_chain():
        return jsonify(ledger.verify())

    @app.get("/api/chain/blocks")
    def api_blocks():
        blocks = ledger.get_blocks()
        return jsonify({"blocks": list(reversed(blocks[-30:]))})

    @app.get("/qr/<lot_id>.png")
    def qr_code(lot_id: str):
        lot = ledger.get_lot(lot_id)
        if not lot:
            abort(404)
        public_url = f"{app.config['PUBLIC_BASE_URL']}/public/trace/{lot_id}"
        image = qrcode.make(public_url, box_size=7, border=2)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png", download_name=f"{lot_id}.png")

    @app.get("/public/trace/<lot_id>")
    def public_trace(lot_id: str):
        lot = ledger.get_lot(lot_id)
        if not lot:
            abort(404)
        return render_template("public_trace.html", lot=lot, integrity=ledger.verify())

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "OrigenChain demo"})

    return app


def _seed_demo(ledger: Blockchain) -> None:
    demo_lots = [
        {
            "lot_id": "OC-CAF-1042", "lot_code": "HUI-1042", "product": "Café",
            "producer": "Asociación Cafetera El Roble", "origin": "Pitalito, Huila",
            "harvest_date": "2026-10-14", "variety": "Castillo", "weight_kg": 180,
            "notes": "Café de especialidad; lote demostrativo.",
        },
        {
            "lot_id": "OC-CAC-2081", "lot_code": "TUM-2081", "product": "Cacao",
            "producer": "Cooperativa Río Mira", "origin": "Tumaco, Nariño",
            "harvest_date": "2026-10-20", "variety": "Cacao fino de aroma", "weight_kg": 95,
            "notes": "Cacao fermentado; lote demostrativo.",
        },
        {
            "lot_id": "OC-CAF-3310", "lot_code": "CAU-3310", "product": "Café",
            "producer": "Finca La Esperanza", "origin": "Popayán, Cauca",
            "harvest_date": "2026-10-27", "variety": "Caturra", "weight_kg": 125,
            "notes": "Lote pequeño de muestra para tostión.",
        },
    ]
    for lot in demo_lots:
        lot_id = lot.pop("lot_id")
        ledger.append({
            "type": "LOT_CREATED", "lot_id": lot_id,
            "actor": lot["producer"], "role": "Productor", "details": lot,
        })
    demo_events = [
        ("OC-CAF-1042", "Recepción", "Centro de acopio · Pitalito, Huila", "Peso y recepción registrados por la cooperativa.", "María Torres", "Cooperativa"),
        ("OC-CAF-1042", "Despacho", "Centro logístico · Neiva, Huila", "Lote despachado hacia la planta de tostión.", "Luis Gómez", "Transportador"),
        ("OC-CAC-2081", "Control de calidad", "Planta de proceso · Tumaco, Nariño", "Muestra recibida para evaluación de calidad.", "Ana Caicedo", "Procesador"),
        ("OC-CAF-3310", "Recepción", "Cooperativa · Popayán, Cauca", "Recepción inicial confirmada.", "Julián Paz", "Cooperativa"),
    ]
    for lot_id, event_type, location, description, actor, role in demo_events:
        ledger.append({
            "type": "TRACE_EVENT", "lot_id": lot_id, "event_type": event_type,
            "location": location, "description": description, "actor": actor, "role": role,
        })


app = create_app(seed_demo=os.environ.get("ORIGINCHAIN_SEED_DEMO", "1") != "0")


if __name__ == "__main__":
    # Local demonstration only. Use a production WSGI server and secure config for deployment.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
