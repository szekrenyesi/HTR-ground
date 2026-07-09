"""
Unit tesztek az `app.meta` modulra: sidecar olvasás/írás, status/edit audit.
"""
import json

import pytest

from app import meta


def test_default_meta_when_no_sidecar(tmp_path):
    m = meta.read(tmp_path, "sample")
    assert m["status"] == "új"
    assert m["status_changed_by"] is None
    assert m["edited_by"] is None


def test_set_status_creates_sidecar(tmp_path):
    result = meta.set_status(tmp_path, "sample", "folyamatban", "anna")
    assert result["status"] == "folyamatban"
    assert result["status_changed_by"] == "anna"
    assert result["status_changed_at"] is not None
    # Fájl tényleg létezik
    p = meta.sidecar_path(tmp_path, "sample")
    assert p.exists()
    # Tartalma parse-elhető és egyezik
    with p.open() as fh:
        data = json.load(fh)
    assert data["status"] == "folyamatban"


def test_set_status_preserves_edit_audit(tmp_path):
    """Ha van már edit_by/edit_at, státusz-váltásnál nem törlődik."""
    meta.record_edit(tmp_path, "sample", "bela")
    result = meta.set_status(tmp_path, "sample", "kész", "anna")
    assert result["status"] == "kész"
    assert result["status_changed_by"] == "anna"
    assert result["edited_by"] == "bela"


def test_record_edit_preserves_status(tmp_path):
    """Ha valaki csak elment: a status nem változik."""
    meta.set_status(tmp_path, "sample", "folyamatban", "anna")
    result = meta.record_edit(tmp_path, "sample", "bela")
    assert result["status"] == "folyamatban"
    assert result["status_changed_by"] == "anna"
    assert result["edited_by"] == "bela"


def test_invalid_status_rejected(tmp_path):
    with pytest.raises(ValueError):
        meta.set_status(tmp_path, "sample", "kitalált", "anna")


def test_corrupted_sidecar_falls_back_to_default(tmp_path):
    """Ha valaki elrontotta a sidecart, ne szakítsuk meg a listázást."""
    p = meta.sidecar_path(tmp_path, "sample")
    p.write_text("nem-json { rossz", encoding="utf-8")
    m = meta.read(tmp_path, "sample")
    assert m["status"] == "új"


def test_status_history_iso_format(tmp_path):
    result = meta.set_status(tmp_path, "sample", "folyamatban", "anna")
    ts = result["status_changed_at"]
    # ISO 8601, Z-vel a végén
    assert ts.endswith("Z")
    assert "T" in ts


def test_all_valid_statuses_accepted(tmp_path):
    for status in meta.VALID_STATUSES:
        meta.set_status(tmp_path, f"s_{status}", status, "anna")


def test_notes_field(tmp_path):
    result = meta.set_status(tmp_path, "sample", "folyamatban", "anna", notes="Erre később rá kell nézni")
    assert result["notes"] == "Erre később rá kell nézni"
