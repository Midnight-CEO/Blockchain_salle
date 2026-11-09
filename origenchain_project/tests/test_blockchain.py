import tempfile
import unittest
from pathlib import Path

from blockchain import Blockchain


class BlockchainTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = Blockchain(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_genesis_block_is_valid(self):
        result = self.ledger.verify()
        self.assertTrue(result["valid"])
        self.assertEqual(result["checked"], 1)

    def test_appended_blocks_keep_chain_valid(self):
        self.ledger.append({"type": "TEST", "message": "primer registro"})
        self.ledger.append({"type": "TEST", "message": "segundo registro"})
        result = self.ledger.verify()
        self.assertTrue(result["valid"])
        self.assertEqual(result["checked"], 3)

    def test_lot_is_rebuilt_from_events(self):
        self.ledger.append({
            "type": "LOT_CREATED", "lot_id": "OC-TEST-01", "actor": "Productor",
            "role": "Productor", "details": {
                "lot_code": "TEST-01", "product": "Café", "producer": "Finca Demo",
                "origin": "Huila", "harvest_date": "2026-10-01", "variety": "Castillo",
                "weight_kg": 50, "notes": "",
            },
        })
        self.ledger.append({
            "type": "TRACE_EVENT", "lot_id": "OC-TEST-01", "event_type": "Recepción",
            "location": "Cooperativa", "description": "Recibido", "actor": "Operador",
            "role": "Cooperativa",
        })
        lot = self.ledger.get_lot("OC-TEST-01")
        self.assertIsNotNone(lot)
        self.assertEqual(len(lot["events"]), 2)
        self.assertEqual(lot["status"], "Recepción")

    def test_unknown_lot_returns_none(self):
        self.assertIsNone(self.ledger.get_lot("NO-EXISTE"))


if __name__ == "__main__":
    unittest.main()
