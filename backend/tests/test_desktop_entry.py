def test_main_runs_uvicorn_on_loopback_fixed_port(client, monkeypatch):
    import uvicorn
    import desktop_entry
    from main import app

    calls = {}
    monkeypatch.setattr(uvicorn, "run", lambda a, **kw: calls.update(app=a, **kw))
    desktop_entry.main()
    assert calls["app"] is app
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 18001
