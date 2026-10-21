"""Report download state must reflect files available on this machine."""

from unittest.mock import MagicMock

from crawler import reports_store


def test_downloaded_keys_excludes_paths_missing_after_database_restore(
    monkeypatch, tmp_path
):
    existing = tmp_path / "report.pdf"
    existing.write_bytes(b"%PDF-test")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {"source_key": "present", "file_path": str(existing)},
        {"source_key": "old-host", "file_path": "/home/old/lgbr/report.pdf"},
    ]
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    connection = MagicMock()
    connection.cursor.return_value = cursor_context
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    monkeypatch.setattr(reports_store, "connect", lambda: connection_context)

    assert reports_store.downloaded_keys("fnguide") == {"present"}