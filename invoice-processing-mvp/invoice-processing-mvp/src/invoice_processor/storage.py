import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

class AuditStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self):
        with self._connect() as con:
            con.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, created_at TEXT, filename TEXT,
                vendor_name TEXT, invoice_number TEXT, po_number TEXT,
                total_amount REAL, decision TEXT, summary TEXT,
                fingerprint TEXT, result_json TEXT
            )""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_invoice ON runs(vendor_name, invoice_number)")

    def find_duplicate(self, vendor_name, invoice_number, fingerprint):
        with self._connect() as con:
            row = con.execute(
                """SELECT run_id, vendor_name, invoice_number FROM runs
                   WHERE fingerprint = ? OR
                   (lower(trim(coalesce(vendor_name,''))) = lower(trim(coalesce(?,'')))
                    AND lower(trim(coalesce(invoice_number,''))) = lower(trim(coalesce(?,'')))
                    AND coalesce(?, '') <> '') LIMIT 1""",
                (fingerprint, vendor_name, invoice_number, invoice_number)
            ).fetchone()
        if row:
            return {"is_duplicate": True, "reason": f"matches previous run {row['run_id']}",
                    "previous_run_id": row["run_id"]}
        return {"is_duplicate": False, "reason": None, "previous_run_id": None}

    def save_run(self, result, filename, fingerprint):
        inv = result["invoice"]
        decision = result["decision"]
        po = result["po_match"].get("po_number")
        with self._connect() as con:
            con.execute("""INSERT INTO runs
                (run_id, created_at, filename, vendor_name, invoice_number, po_number,
                 total_amount, decision, summary, fingerprint, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (result["run_id"], datetime.now(timezone.utc).isoformat(), filename,
                 inv.get("vendor_name"), inv.get("invoice_number"), po,
                 inv.get("total_amount"), decision["status"], decision["summary"],
                 fingerprint, json.dumps(result, default=str)))

    def update_result(self, result, filename, fingerprint):
        inv = result["invoice"]
        with self._connect() as con:
            con.execute("UPDATE runs SET result_json=? WHERE run_id=?",
                        (json.dumps(result, default=str), result["run_id"]))

    def list_runs(self, limit=500):
        with self._connect() as con:
            rows = con.execute("SELECT run_id, created_at, filename, vendor_name, invoice_number, "
                               "po_number, total_amount, decision, summary FROM runs "
                               "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id):
        with self._connect() as con:
            row = con.execute("SELECT result_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row["result_json"]) if row else None
