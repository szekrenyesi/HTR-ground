"""
Unit tesztek az `app.acl` modulra: longest-prefix match, admin bypass.
"""
from app import acl


def test_no_config_visible_to_everyone():
    assert acl.is_visible("Bakonykuti", "anna", projects_cfg={}) is True
    assert acl.is_visible("", "anna", projects_cfg={}) is True


def test_exact_match_restrict():
    cfg = {"Titkos": {"visible_to": ["anna"]}}
    assert acl.is_visible("Titkos", "anna", projects_cfg=cfg) is True
    assert acl.is_visible("Titkos", "bela", projects_cfg=cfg) is False
    assert acl.is_visible("Nem_Titkos", "bela", projects_cfg=cfg) is True


def test_child_inherits_parent_acl():
    cfg = {"Bakonykuti": {"visible_to": ["anna"]}}
    assert acl.is_visible("Bakonykuti/1949", "anna", projects_cfg=cfg) is True
    assert acl.is_visible("Bakonykuti/1949/oldal", "anna", projects_cfg=cfg) is True
    assert acl.is_visible("Bakonykuti/1949", "bela", projects_cfg=cfg) is False


def test_longest_prefix_wins():
    cfg = {
        "Bakonykuti":            {"visible_to": ["anna", "bela"]},
        "Bakonykuti/part2":      {"visible_to": ["anna"]},
    }
    # part2 → csak anna
    assert acl.is_visible("Bakonykuti/part2", "anna", projects_cfg=cfg) is True
    assert acl.is_visible("Bakonykuti/part2", "bela", projects_cfg=cfg) is False
    assert acl.is_visible("Bakonykuti/part2/inner", "bela", projects_cfg=cfg) is False
    # part1 → örökli a Bakonykuti-t → anna és bela
    assert acl.is_visible("Bakonykuti/part1", "anna", projects_cfg=cfg) is True
    assert acl.is_visible("Bakonykuti/part1", "bela", projects_cfg=cfg) is True
    # Bakonykuti maga → anna és bela
    assert acl.is_visible("Bakonykuti", "anna", projects_cfg=cfg) is True
    assert acl.is_visible("Bakonykuti", "bela", projects_cfg=cfg) is True


def test_admin_bypass():
    cfg = {"Titkos": {"visible_to": ["anna"]}}
    assert acl.is_visible("Titkos", "bela", is_admin=True, projects_cfg=cfg) is True
    assert acl.is_visible("Titkos", None,   is_admin=True, projects_cfg=cfg) is True


def test_wildcard_visible_to():
    cfg = {"NyilvanosBenn": {"visible_to": ["*"]}}
    assert acl.is_visible("NyilvanosBenn", "anna", projects_cfg=cfg) is True
    assert acl.is_visible("NyilvanosBenn", "bela", projects_cfg=cfg) is True
    # De None user (nem-belépett) továbbra sem lép be — a hívó szűri be az auth-ot


def test_malformed_config_fails_closed():
    # Rossz alakú entry → nem látja senki (biztonságos default)
    cfg = {"Beteg": {"nincs_visible_to_mezo": True}}
    assert acl.is_visible("Beteg", "anna", projects_cfg=cfg) is False


def test_filter_folder_names_root():
    cfg = {"Titkos": {"visible_to": ["anna"]}}
    names = ["Bakonykuti", "Titkos", "Nyilvanos"]
    # anna: mindent lát
    assert acl.filter_folder_names(names, "anna", projects_cfg=cfg) == names
    # bela: nem látja Titkos-t
    assert acl.filter_folder_names(names, "bela", projects_cfg=cfg) == ["Bakonykuti", "Nyilvanos"]


def test_filter_folder_names_deep():
    cfg = {
        "Bakonykuti":       {"visible_to": ["anna", "bela"]},
        "Bakonykuti/part2": {"visible_to": ["anna"]},
    }
    names = ["part1", "part2", "part3"]
    result = acl.filter_folder_names(names, "bela", parent_path="Bakonykuti", projects_cfg=cfg)
    assert result == ["part1", "part3"]  # part2 rejtve bela elől
