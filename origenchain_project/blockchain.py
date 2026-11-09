"""A small SQLite-backed, hash-linked ledger for the OrigenChain teaching demo.

This is an educational single-node blockchain prototype. It demonstrates block
linking and tamper detection; it is NOT a decentralized production network.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Blockchain:
    """Append-only hash chain persisted in SQLite."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def calculate_hash(
        cls, index: int, timestamp: str, data: dict[str, Any], previous_hash: str
    ) -> str:
        body = {
            "index": index,
            "timestamp": timestamp,
            "data": data,
            "previous_hash": previous_hash,
        }
        return hashlib.sha256(cls._canonical_json(body).encode("utf-8")).hexdigest()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS blocks (
                    block_index INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    block_hash TEXT NOT NULL UNIQUE
                )"""
            )
            row = conn.execute("SELECT COUNT(*) AS total FROM blocks").fetchone()
            if row["total"] == 0:
                timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                data = {"type": "GENESIS", "message": "OrigenChain demo ledger"}
                previous_hash = "0" * 64
                block_hash = self.calculate_hash(0, timestamp, data, previous_hash)
                conn.execute(
                    "INSERT INTO blocks VALUES (?, ?, ?, ?, ?)",
                    (0, timestamp, self._canonical_json(data), previous_hash, block_hash),
                )

    def append(self, data: dict[str, Any]) -> dict[str, Any]:
        """Append a new immutable event and return the created block."""
        if not isinstance(data, dict):
            raise TypeError("Block data must be a dictionary")

        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data_json = self._canonical_json(data)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            last = conn.execute(
                "SELECT block_index, block_hash FROM blocks ORDER BY block_index DESC LIMIT 1"
            ).fetchone()
            if last is None:
                raise RuntimeError("Ledger has no genesis block")
            index = int(last["block_index"]) + 1
            previous_hash = str(last["block_hash"])
            block_hash = self.calculate_hash(index, timestamp, data, previous_hash)
            conn.execute(
                "INSERT INTO blocks VALUES (?, ?, ?, ?, ?)",
                (index, timestamp, data_json, previous_hash, block_hash),
            )
        return {
            "index": index,
            "timestamp": timestamp,
            "data": data,
            "previous_hash": previous_hash,
            "hash": block_hash,
        }

    def get_blocks(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM blocks ORDER BY block_index ASC"
            ).fetchall()
        return [
            {
                "index": row["block_index"],
                "timestamp": row["timestamp"],
                "data": json.loads(row["data_json"]),
                "previous_hash": row["previous_hash"],
                "hash": row["block_hash"],
            }
            for row in rows
        ]

    def verify(self) -> dict[str, Any]:
        """Check sequential indexes, previous-hash links and each block hash."""
        blocks = self.get_blocks()
        if not blocks:
            return {"valid": False, "checked": 0, "message": "El libro está vacío."}

        expected_previous = "0" * 64
        for expected_index, block in enumerate(blocks):
            if block["index"] != expected_index:
                return {
                    "valid": False,
                    "checked": expected_index,
                    "message": f"Secuencia inválida en el bloque {expected_index}.",
                }
            if block["previous_hash"] != expected_previous:
                return {
                    "valid": False,
                    "checked": expected_index,
                    "message": f"El enlace anterior del bloque {expected_index} no coincide.",
                }
            expected_hash = self.calculate_hash(
                block["index"], block["timestamp"], block["data"], block["previous_hash"]
            )
            if block["hash"] != expected_hash:
                return {
                    "valid": False,
                    "checked": expected_index + 1,
                    "message": f"La huella del bloque {expected_index} fue alterada.",
                }
            expected_previous = block["hash"]

        return {
            "valid": True,
            "checked": len(blocks),
            "message": "Todos los bloques y sus enlaces son íntegros.",
        }

    def get_lots(self) -> list[dict[str, Any]]:
        """Rebuild the lot view from immutable ledger events."""
        lots: dict[str, dict[str, Any]] = {}
        for block in self.get_blocks():
            data = block["data"]
            lot_id = data.get("lot_id")
            if not lot_id:
                continue
            if data.get("type") == "LOT_CREATED":
                details = data.get("details", {})
                lots[lot_id] = {
                    "lot_id": lot_id,
                    **details,
                    "created_at": block["timestamp"],
                    "events": [],
                    "status": "Lote creado",
                    "last_updated": block["timestamp"],
                }
                lots[lot_id]["events"].append(
                    {
                        "type": "Lote creado",
                        "actor": data.get("actor", "Participante"),
                        "role": data.get("role", "Productor"),
                        "location": details.get("origin", "Origen registrado"),
                        "description": "Registro inicial del lote en el libro de trazabilidad.",
                        "timestamp": block["timestamp"],
                        "block_index": block["index"],
                        "hash": block["hash"],
                    }
                )
            elif lot_id in lots:
                event = {
                    "type": data.get("event_type", "Actualización"),
                    "actor": data.get("actor", "Participante"),
                    "role": data.get("role", "Operador"),
                    "location": data.get("location", "Sin ubicación"),
                    "description": data.get("description", ""),
                    "timestamp": block["timestamp"],
                    "block_index": block["index"],
                    "hash": block["hash"],
                }
                lots[lot_id]["events"].append(event)
                lots[lot_id]["status"] = event["type"]
                lots[lot_id]["last_updated"] = block["timestamp"]

        return sorted(lots.values(), key=lambda lot: lot["last_updated"], reverse=True)

    def get_lot(self, lot_id: str) -> dict[str, Any] | None:
        return next((lot for lot in self.get_lots() if lot["lot_id"] == lot_id), None)
