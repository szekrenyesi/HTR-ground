"""
Integrációs tesztek: az `app.projects.list_folder` ACL-lel.

Egy tmp `projects/` fát építünk, és megkerüljük a valós `projects/Minta`-t,
hogy a tesztek reprodukálhatók legyenek.
"""
import json
from pathlib import Path

import pytest

from app import auth, projects


@pytest.fixture
def tmp_projects_tree(tmp_path, monkeypatch):
    """Ideiglenes projects/ fa a teszthez, ACL config-gal."""
    tree = tmp_path / "projects"
    (tree / "Nyilvanos" / "1900").mkdir(parents=True)
    (tree / "Nyilvanos" / "1900" / "a.jpg").write_bytes(b"fake-jpg")
    (tree / "Nyilvanos" / "1900" / "a.json").write_text(
        '{"regions":[],"image_width":100,"image_height":100}', encoding="utf-8"
    )
    (tree / "Titkos" / "1901").mkdir(parents=True)
    (tree / "Titkos" / "1901" / "b.jpg").write_bytes(b"fake-jpg")
    (tree / "Titkos" / "1901" / "b.json").write_text(
        '{"regions":[],"image_width":100,"image_height":100}', encoding="utf-8"
    )
    (tree / "Bakonykuti" / "part1").mkdir(parents=True)
    (tree / "Bakonykuti" / "part1" / "c.jpg").write_bytes(b"fake-jpg")
    (tree / "Bakonykuti" / "part1" / "c.json").write_text(
        '{"regions":[],"image_width":100,"image_height":100}', encoding="utf-8"
    )
    (tree / "Bakonykuti" / "part2").mkdir(parents=True)
    (tree / "Bakonykuti" / "part2" / "d.jpg").write_bytes(b"fake-jpg")
    (tree / "Bakonykuti" / "part2" / "d.json").write_text(
        '{"regions":[],"image_width":100,"image_height":100}', encoding="utf-8"
    )

    monkeypatch.setattr(projects, "PROJECTS_ROOT", tree)

    # ACL config: Titkos csak annának, Bakonykuti/part2 csak annának
    auth.AUTH_CONFIG["projects"] = {
        "Titkos":            {"visible_to": ["anna"]},
        "Bakonykuti/part2":  {"visible_to": ["anna"]},
    }
    yield tree
    auth.AUTH_CONFIG["projects"] = {}


def test_root_listing_filters_titkos(tmp_projects_tree):
    """Bela nem látja a `Titkos`-t a gyökérben."""
    result = projects.list_folder("", username="bela")
    names = [f["name"] for f in result["subfolders"]]
    assert "Titkos" not in names
    assert "Nyilvanos" in names
    assert "Bakonykuti" in names


def test_root_listing_admin_sees_everything(tmp_projects_tree):
    result = projects.list_folder("", username="admin")
    names = [f["name"] for f in result["subfolders"]]
    assert set(names) == {"Nyilvanos", "Titkos", "Bakonykuti"}


def test_deep_listing_denies_direct_access(tmp_projects_tree):
    """Bela közvetlenül próbál a Titkos-ba lépni → AccessDeniedError."""
    with pytest.raises(projects.AccessDeniedError):
        projects.list_folder("Titkos", username="bela")


def test_deep_listing_bakonykuti_part1_ok_for_bela(tmp_projects_tree):
    """Bakonykuti/part1 nincs korlátozva, Bakonykuti szintén nem → bela láthatja."""
    result = projects.list_folder("Bakonykuti/part1", username="bela")
    assert len(result["pairs"]) == 1
    assert result["pairs"][0]["basename"] == "c"


def test_deep_listing_bakonykuti_part2_hidden_for_bela(tmp_projects_tree):
    with pytest.raises(projects.AccessDeniedError):
        projects.list_folder("Bakonykuti/part2", username="bela")


def test_bakonykuti_root_shows_only_visible_subfolders(tmp_projects_tree):
    """Bela a Bakonykuti-ban lát: part1, de NEM lát part2-t."""
    result = projects.list_folder("Bakonykuti", username="bela")
    names = [f["name"] for f in result["subfolders"]]
    assert "part1" in names
    assert "part2" not in names


def test_find_pair_respects_acl(tmp_projects_tree):
    """find_pair ellenőrzi az ACL-t ha username adva van."""
    with pytest.raises(projects.AccessDeniedError):
        projects.find_pair("Titkos/1901", "b", username="bela")
    # De anna hozzáfér
    result = projects.find_pair("Titkos/1901", "b", username="anna")
    assert result["image"] is not None
