"""Utility backup staging SQLite dengan verifikasi logical, bukan byte identity."""

import hashlib
import json
from pathlib import Path
import sqlite3


def _quote_identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


def _json_value(value):
    if isinstance(value, bytes):
        return {"blob_sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    return value


def logical_sqlite_manifest(path):
    resolved = Path(path).expanduser().resolve()
    connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    try:
        objects = connection.execute(
            "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        tables = [row[1] for row in objects if row[0] == "table"]
        row_counts = {}
        table_checksums = {}
        for table in tables:
            columns = [row[1] for row in connection.execute(
                f"PRAGMA table_info({_quote_identifier(table)})"
            ).fetchall()]
            quoted_columns = ",".join(_quote_identifier(column) for column in columns)
            order_clause = ",".join(_quote_identifier(column) for column in columns)
            rows = connection.execute(
                f"SELECT {quoted_columns} FROM {_quote_identifier(table)} ORDER BY {order_clause}"
            ).fetchall() if columns else []
            normalized = [[_json_value(value) for value in row] for row in rows]
            row_counts[table] = len(rows)
            table_checksums[table] = hashlib.sha256(
                json.dumps(normalized, ensure_ascii=True, separators=(",", ":"), default=str).encode("ascii")
            ).hexdigest()
        object_checksum = hashlib.sha256(
            json.dumps(objects, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
        return {
            "path": str(resolved),
            "object_count": len(objects),
            "object_checksum": object_checksum,
            "row_counts": row_counts,
            "table_checksums": table_checksums,
            "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_errors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
        }
    finally:
        connection.close()


def create_logical_sqlite_backup(source_path, backup_path):
    source = Path(source_path).expanduser().resolve()
    backup = Path(backup_path).expanduser().resolve()
    if source == backup:
        raise ValueError("Path backup harus berbeda dari database sumber.")
    backup.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    backup_connection = sqlite3.connect(backup)
    try:
        source_connection.backup(backup_connection)
    finally:
        backup_connection.close()
        source_connection.close()
    source_manifest = logical_sqlite_manifest(source)
    backup_manifest = logical_sqlite_manifest(backup)
    comparable_keys = ("object_count", "object_checksum", "row_counts", "table_checksums")
    if any(source_manifest[key] != backup_manifest[key] for key in comparable_keys):
        raise ValueError("Logical SQLite backup tidak cocok dengan sumber.")
    if backup_manifest["integrity_check"] != "ok" or backup_manifest["foreign_key_errors"]:
        raise ValueError("Logical SQLite backup gagal integrity verification.")
    return {"method": "sqlite_backup_api", "source": source_manifest, "backup": backup_manifest}


def restore_logical_sqlite_backup(backup_path, restored_path):
    backup = Path(backup_path).expanduser().resolve()
    restored = Path(restored_path).expanduser().resolve()
    if backup == restored:
        raise ValueError("Path restore harus berbeda dari backup.")
    restored.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{backup.as_posix()}?mode=ro", uri=True)
    restored_connection = sqlite3.connect(restored)
    try:
        source_connection.backup(restored_connection)
    finally:
        restored_connection.close()
        source_connection.close()
    backup_manifest = logical_sqlite_manifest(backup)
    restored_manifest = logical_sqlite_manifest(restored)
    for key in ("object_count", "object_checksum", "row_counts", "table_checksums"):
        if backup_manifest[key] != restored_manifest[key]:
            raise ValueError("Restore SQLite tidak cocok dengan backup.")
    if restored_manifest["integrity_check"] != "ok" or restored_manifest["foreign_key_errors"]:
        raise ValueError("Database hasil restore tidak valid.")
    return restored_manifest
