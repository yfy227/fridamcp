"""REST API 测试（供 Android 原生 App 的接口层）

用 starlette TestClient 直调全部端点；frida_client 等单例
全部 mock——验证路由、参数解析、impl 透传与错误契约。
"""
from unittest.mock import MagicMock, patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from fridamcp import rest_api  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(rest_api.app)


def _fake_frida_client():
    fc = MagicMock()
    fc.list_devices.return_value = [{"id": "usb1", "name": "Pixel", "type": "usb"}]
    fc.list_processes.return_value = [{"pid": 1, "name": "init"}]
    fc.list_applications.return_value = [{"identifier": "com.x", "name": "X", "pid": 0}]
    fc.spawn.return_value = {"session_id": "s1", "pid": 100}
    fc.attach.return_value = {"session_id": "s1", "pid": 100, "name": "com.x"}
    fc.resume.return_value = {"success": True}
    fc.kill.return_value = {"success": True}
    fc.get_messages.return_value = [{"message": {"type": "ssl_write", "data": "hi"}}]
    fc.execute_script.return_value = {"script_id": "scr_1"}
    # memory modules(list) 返回数组、read 返回 dict
    fc.call_script_function.side_effect = (
        lambda sid, scr, fn, args:
        [{"name": "libx.so", "base": "0x1000"}] if fn == "list" else {"hex": "00ff"}
    )
    fc.select_device.return_value = {"id": "usb1", "name": "Pixel", "type": "usb"}
    return fc


@pytest.fixture(autouse=True)
def mocked_deps():
    fc = _fake_frida_client()
    sm = MagicMock()
    sm.get_status.return_value = {"total_sessions": 1}
    sm.list_sessions.return_value = [{"id": "s1", "pid": 100}]
    sm.close_session.return_value = True
    dm = MagicMock()
    dm.get_status.return_value = {"connected": True}
    with patch.object(rest_api, "frida_client", fc), \
         patch.object(rest_api, "session_manager", sm), \
         patch.object(rest_api, "device_manager", dm):
        yield {"frida_client": fc, "session_manager": sm}


def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "3.0.0"
    assert body["device"]["connected"] is True


def test_devices_and_select(client):
    assert client.get("/api/devices").json()[0]["id"] == "usb1"
    r = client.post("/api/device/select", json={"device_id": "usb1"})
    assert r.json()["id"] == "usb1"


def test_processes_applications(client):
    assert client.get("/api/processes").json()[0]["name"] == "init"
    assert client.get("/api/applications").json()[0]["identifier"] == "com.x"


def test_spawn_attach_resume_kill(client, mocked_deps):
    fc = mocked_deps["frida_client"]
    r = client.post("/api/spawn", json={"package": "com.x", "paused": True})
    assert r.json()["session_id"] == "s1"
    fc.spawn.assert_called_once_with("com.x", paused=True)

    r = client.post("/api/attach", json={"pid": 100})
    assert r.json()["pid"] == 100

    r = client.post("/api/attach", json={})
    assert "error" in r.json()

    client.post("/api/resume", json={"pid": 100})
    fc.resume.assert_called_once_with(100)
    client.post("/api/kill", json={"pid": 100})
    fc.kill.assert_called_once_with(100)


def test_sessions_management(client, mocked_deps):
    r = client.get("/api/sessions")
    assert r.json()[0]["id"] == "s1"
    r = client.post("/api/session/close", json={"session_id": "s1"})
    assert r.json()["success"] is True
    mocked_deps["session_manager"].close_session.assert_called_once_with("s1")


def test_hook_endpoints_delegate_to_impl(client):
    calls = []
    with patch.object(rest_api, "hook_java_method_impl",
                      side_effect=lambda s, c, m: calls.append((s, c, m)) or {"ok": 1}), \
         patch.object(rest_api, "hook_native_impl", return_value={"ok": 1}), \
         patch.object(rest_api, "trace_method_impl", return_value={"ok": 1}):
        client.post("/api/hook/java",
                    json={"session_id": "s1", "class_name": "a.b.C",
                          "method_name": "run"})
        client.post("/api/hook/native",
                    json={"session_id": "s1", "module_name": "libx.so",
                          "func_name": "fn", "offset": 8})
        client.post("/api/hook/trace",
                    json={"session_id": "s1", "class_name": "a.b.C",
                          "method_name": "x"})
    assert calls == [("s1", "a.b.C", "run")]


def test_messages_network_logs(client):
    r = client.get("/api/messages", params={"session_id": "s1"})
    assert r.json()[0]["message"]["type"] == "ssl_write"

    with patch.object(rest_api, "start_capture_impl") as sci, \
         patch.object(rest_api, "stop_capture_impl") as sco, \
         patch.object(rest_api, "get_capture_impl") as gci:
        sci.return_value = {"hooks": [{"type": "ssl"}]}
        sco.return_value = {"success": True, "captured_count": 3}
        gci.return_value = [{"type": "ssl_write"}]
        r = client.post("/api/network/start",
                        json={"session_id": "s1", "capture_ssl": True})
        assert r.json()["hooks"][0]["type"] == "ssl"
        r = client.post("/api/network/stop", json={"session_id": "s1"})
        assert r.json()["captured_count"] == 3
        r = client.get("/api/network/capture", params={"session_id": "s1"})
        assert r.json()[0]["type"] == "ssl_write"


def test_memory_endpoints(client, mocked_deps):
    fc = mocked_deps["frida_client"]
    r = client.get("/api/memory/modules", params={"session_id": "s1"})
    assert r.json() == [{"name": "libx.so", "base": "0x1000"}]
    r = client.post("/api/memory/read",
                    json={"session_id": "s1", "address": "0x1000", "size": 32})
    fc.call_script_function.assert_called()
    assert r.json() == {"hex": "00ff"}


def test_server_logs(client):
    r = client.get("/api/logs/server", params={"max_entries": 10})
    assert r.status_code == 200
    assert isinstance(r.json(), list)
