import io
import os
import threading


def test_main_runs_uvicorn_on_loopback_fixed_port(client, monkeypatch):
    import uvicorn
    import desktop_entry
    from main import app

    calls = {}
    watched = []
    monkeypatch.setattr(uvicorn, "run", lambda a, **kw: calls.update(app=a, **kw))
    monkeypatch.setattr(desktop_entry, "watch_parent", lambda *a, **kw: watched.append(True))
    desktop_entry.main()
    assert calls["app"] is app
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 18001
    assert watched == [True]


def test_watch_parent_exits_when_stdin_closes():
    import desktop_entry

    exited = threading.Event()
    desktop_entry.watch_parent(io.StringIO(""), exited.set)
    assert exited.wait(2)


def test_watch_parent_waits_while_stdin_open():
    import desktop_entry

    r, w = os.pipe()
    exited = threading.Event()
    desktop_entry.watch_parent(os.fdopen(r), exited.set)
    assert not exited.wait(0.3)
    os.close(w)
    assert exited.wait(2)


def test_watch_parent_ignores_unreadable_stdin():
    import desktop_entry

    class Broken:
        def read(self):
            raise OSError("no stdin")

    exited = threading.Event()
    desktop_entry.watch_parent(Broken(), exited.set).join(2)
    assert not exited.is_set()
