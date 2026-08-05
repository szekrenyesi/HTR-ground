"""
Projekt-statisztika tesztek: `count_statuses` és a `list_folder.stats` mező.
"""
import pytest

from app import auth, projects, meta as pair_meta


@pytest.fixture
def tmp_projects(tmp_path, monkeypatch):
    """Kicsi projekt-fa több almappával, hogy a rekurzió lássa őket."""
    tree = tmp_path / "projects"

    # /Projekt1/1949 → 3 pár, 2 „új", 1 „folyamatban"
    f1 = tree / "Projekt1" / "1949"
    f1.mkdir(parents=True)
    for i in range(3):
        (f1 / f"p{i}.jpg").write_bytes(b"fake")
        (f1 / f"p{i}.json").write_text('{"regions":[]}', encoding="utf-8")
    pair_meta.set_status(f1, "p0", "folyamatban", "admin")  # a többi default "új"

    # /Projekt1/1950 → 2 pár, mindkettő „kész"
    f2 = tree / "Projekt1" / "1950"
    f2.mkdir(parents=True)
    for i in range(2):
        (f2 / f"q{i}.jpg").write_bytes(b"fake")
        (f2 / f"q{i}.json").write_text('{"regions":[]}', encoding="utf-8")
        pair_meta.set_status(f2, f"q{i}", "kész", "admin")

    # /Projekt2/root → 1 pár, „ellenőrzésre vár"
    f3 = tree / "Projekt2"
    f3.mkdir(parents=True)
    (f3 / "r.jpg").write_bytes(b"fake")
    (f3 / "r.json").write_text('{"regions":[]}', encoding="utf-8")
    pair_meta.set_status(f3, "r", "ellenőrzésre vár", "admin")

    monkeypatch.setattr(projects, "PROJECTS_ROOT", tree)
    auth.AUTH_CONFIG["projects"] = {}
    return tree


def test_stats_at_root_aggregates_everything(tmp_projects):
    stats = projects.count_statuses("", username="anna")
    assert stats["total"] == 6
    assert stats["counts"]["új"] == 2
    assert stats["counts"]["folyamatban"] == 1
    assert stats["counts"]["ellenőrzésre vár"] == 1
    assert stats["counts"]["kész"] == 2


def test_stats_at_project_level(tmp_projects):
    stats = projects.count_statuses("Projekt1", username="anna")
    assert stats["total"] == 5
    assert stats["counts"]["új"] == 2
    assert stats["counts"]["folyamatban"] == 1
    assert stats["counts"]["kész"] == 2
    # Projekt2-ből semmi nem szivárgott be
    assert "ellenőrzésre vár" not in stats["counts"]


def test_stats_at_leaf_folder(tmp_projects):
    stats = projects.count_statuses("Projekt1/1950", username="anna")
    assert stats["total"] == 2
    assert stats["counts"] == {"kész": 2}


def test_stats_zero_status_excluded(tmp_projects):
    """A 0 értékű státuszok nincsenek a válaszban — csak amit tényleg használunk."""
    stats = projects.count_statuses("Projekt1/1950", username="anna")
    assert set(stats["counts"].keys()) == {"kész"}
    assert "új" not in stats["counts"]
    assert "folyamatban" not in stats["counts"]


def test_stats_respects_acl(tmp_projects):
    """Ha a user nem lát egy projektet, annak státuszait nem számoljuk."""
    auth.AUTH_CONFIG["projects"] = {"Projekt2": {"visible_to": ["admin"]}}
    try:
        # anna nem látja Projekt2-t → Projekt2 „ellenőrzésre vár" pár nem számít
        stats = projects.count_statuses("", username="anna")
        assert stats["total"] == 5  # csak Projekt1
        assert "ellenőrzésre vár" not in stats["counts"]

        # admin viszont mindet látja
        stats_admin = projects.count_statuses("", username="admin")
        assert stats_admin["total"] == 6
        assert stats_admin["counts"]["ellenőrzésre vár"] == 1
    finally:
        auth.AUTH_CONFIG["projects"] = {}


def test_stats_hidden_when_no_access(tmp_projects):
    """Ha a user nem látja MAGÁT a mappát, üres stats."""
    auth.AUTH_CONFIG["projects"] = {"Projekt2": {"visible_to": ["admin"]}}
    try:
        stats = projects.count_statuses("Projekt2", username="anna")
        assert stats == {"counts": {}, "total": 0}
    finally:
        auth.AUTH_CONFIG["projects"] = {}


def test_list_folder_includes_stats(tmp_projects, logged_in_client):
    """A `/api/projects/{path}` végpont válasza is tartalmazza a stats-ot."""
    r = logged_in_client.get("/api/projects/Projekt1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "stats" in body
    assert body["stats"]["total"] == 5
    assert body["stats"]["counts"]["új"] == 2


def test_list_folder_root_stats(tmp_projects, logged_in_client):
    r = logged_in_client.get("/api/projects")
    body = r.json()
    assert body["stats"]["total"] == 6


def test_empty_folder_zero_stats(tmp_projects, monkeypatch, logged_in_client):
    """Üres mappán a stats total: 0, counts üres."""
    empty = tmp_projects / "Ures"
    empty.mkdir()
    r = logged_in_client.get("/api/projects/Ures")
    body = r.json()
    assert body["stats"]["total"] == 0
    assert body["stats"]["counts"] == {}
