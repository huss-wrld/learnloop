"""One backend process serves every profile (11 Nov: the Learn page read the default profile's data)."""
import learnloop


def test_store_follows_the_profile(monkeypatch, tmp_path):
    homes = {"a": tmp_path / "a", "b": tmp_path / "b"}
    current = {"home": "a"}
    monkeypatch.setattr(learnloop, "_stores", {})
    monkeypatch.setattr(learnloop, "_hermes_home", lambda: str(homes[current["home"]]))
    import sqlite3
    import sys
    import types

    def plugin_db(name, fn):
        homes[current["home"]].mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(homes[current["home"]] / fn), check_same_thread=False)
    fake = types.ModuleType("plugins.plugin_storage")
    fake.plugin_db = plugin_db
    monkeypatch.setitem(sys.modules, "plugins", types.ModuleType("plugins"))
    monkeypatch.setitem(sys.modules, "plugins.plugin_storage", fake)
    a = learnloop.get_store()
    a.record("s1", [{"name": "Only in A", "statement": "Lives in profile a."}])
    current["home"] = "b"
    b = learnloop.get_store()
    assert b is not a and b.graph()["propositions"] == []
    current["home"] = "a"
    assert learnloop.get_store() is a
