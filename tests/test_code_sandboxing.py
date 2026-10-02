"""D19: Builder's test execution is a bare subprocess, not a sandbox. These tests document exactly what
containment exists (the tempfile module lands inside the change folder) and what does not (an absolute path
still escapes). If the second test ever starts failing, that is real sandboxing landing, not a regression:
update D19 and this file together, do not just delete the test."""

from pathlib import Path

from factory import code


def propose(tmp_path, name, new_file_body):
    return code.propose(code.APP, tmp_path, name, [], {"tests/test_x.py": new_file_body})


def test_a_test_using_tempfile_lands_inside_the_sandbox(tmp_path):
    result = propose(tmp_path, "contained", """
import tempfile, pathlib
def test_writes_via_tempfile():
    p = pathlib.Path(tempfile.gettempdir()) / "sandboxing_probe.txt"
    p.write_text("contained")
    assert p.exists()
""")
    assert result["tests"]["passed"], result["tests"]["output"]
    assert (tmp_path / "contained" / ".tmp" / "sandboxing_probe.txt").exists()


def test_a_hardcoded_absolute_path_still_escapes_the_sandbox(tmp_path):
    """Known, disclosed limitation (D19): nothing stops a test from writing anywhere this OS user can reach if it
    names the path directly instead of asking the OS for a temp directory. No in-process fix closes this; it
    needs real containment (a container or VM), which is why D19 says to run Builder only where that is accepted."""
    canary = tmp_path / "outside_the_changes_folder.txt"
    result = propose(tmp_path, "escapes", f"""
import pathlib
def test_writes_an_absolute_path():
    pathlib.Path(r"{canary}").write_text("escaped")
""")
    assert result["tests"]["passed"], result["tests"]["output"]
    assert canary.exists()  # proves the escape, not a success condition to defend


def test_resource_limits_are_set_on_posix_and_skipped_on_windows():
    import sys

    limit = code._resource_limits()
    if sys.platform == "win32":
        assert limit is None
    else:
        assert callable(limit)


# D19, the rest of the sweep -------------------------------------------------------------------------------

def test_warehouse_cuts_off_a_query_that_does_too_much_work_before_its_first_row(tmp_path, now_run):
    from factory import warehouse

    r = warehouse.query(now_run / "world" / "world.db", "SELECT a.event_id, b.event_id FROM events a, events b ORDER BY a.ts DESC, b.ts DESC")
    assert r["status"] == "rejection" and r["code"] == "query_too_expensive"


def test_warehouse_still_answers_a_normal_query(now_run):
    from factory import warehouse

    r = warehouse.query(now_run / "world" / "world.db", "SELECT COUNT(*) FROM workspaces")
    assert r["status"] == "value" and r["rows"][0][0] > 0


def test_design_rejects_a_script_tag_and_an_inline_event_handler():
    from factory import design

    assert any("script" in p for p in design.static_problems("<div class=\"tb-card\"><script>1</script></div>"))
    assert any("event handler" in p for p in design.static_problems("<button class=\"tb-btn\" onclick=\"go()\">Go</button>"))
