"""FridaMCP REST API

为 Android 原生 App（android-app/）等原生客户端提供轻量 REST 接口。
全部端点直接复用 modules 的共享 impl 层与 core 单例——与 MCP 工具、
GUI 共享同一份业务逻辑（单一事实来源）。

默认端口 8770（FRIDAMCP_REST_PORT 覆盖），独立于 MCP 协议端口。
"""

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from .config import config
from .core.device_manager import device_manager
from .core.frida_client import frida_client
from .core.session_manager import session_manager
from .modules.hook import (
    hook_java_method_impl,
    hook_native_impl,
    trace_method_impl,
)
from .modules.network import (
    start_capture_impl,
    stop_capture_impl,
    get_capture_impl,
)
from .utils.logger import logger, get_log_buffer


app = FastAPI(title="FridaMCP REST API", version="1.0.0")


# ---------- 请求模型 ----------

class DeviceSelectReq(BaseModel):
    device_id: Optional[str] = None
    device_type: Optional[str] = None


class SpawnReq(BaseModel):
    package: str
    paused: bool = True


class AttachReq(BaseModel):
    pid: Optional[int] = None
    name: Optional[str] = None


class PidReq(BaseModel):
    pid: int


class SessionIdReq(BaseModel):
    session_id: str


class HookJavaReq(BaseModel):
    session_id: str
    class_name: str
    method_name: str


class HookNativeReq(BaseModel):
    session_id: str
    module_name: str
    func_name: Optional[str] = None
    offset: int = 0


class NetworkStartReq(BaseModel):
    session_id: str
    capture_ssl: bool = True
    capture_socket: bool = False


class LogStartReq(BaseModel):
    session_id: Optional[str] = None
    package: Optional[str] = None


class MemoryReadReq(BaseModel):
    session_id: str
    address: str
    size: int = 64


# ---------- 状态 / 设备 ----------

@app.get("/api/status")
def get_status() -> Dict[str, Any]:
    """总览：MCP/设备/会话状态"""
    return {
        "version": "3.0.0",
        "device": device_manager.get_status(),
        "sessions": session_manager.get_status(),
    }


@app.get("/api/devices")
def list_devices() -> List[Dict[str, Any]]:
    return frida_client.list_devices()


@app.post("/api/device/select")
def select_device(req: DeviceSelectReq) -> Dict[str, Any]:
    return frida_client.select_device(req.device_id, req.device_type)


# ---------- 进程 / 应用 ----------

@app.get("/api/processes")
def list_processes() -> List[Dict[str, Any]]:
    return frida_client.list_processes()


@app.get("/api/applications")
def list_applications() -> List[Dict[str, Any]]:
    return frida_client.list_applications()


@app.post("/api/spawn")
def spawn_app(req: SpawnReq) -> Dict[str, Any]:
    return frida_client.spawn(req.package, paused=req.paused)


@app.post("/api/attach")
def attach_process(req: AttachReq) -> Dict[str, Any]:
    if req.pid is not None:
        return frida_client.attach(req.pid)
    if req.name:
        return frida_client.attach(req.name)
    return {"error": "pid or name required"}


@app.post("/api/resume")
def resume_process(req: PidReq) -> Dict[str, Any]:
    return frida_client.resume(req.pid)


@app.post("/api/kill")
def kill_process(req: PidReq) -> Dict[str, Any]:
    return frida_client.kill(req.pid)


# ---------- 会话 ----------

@app.get("/api/sessions")
def list_sessions() -> List[Dict[str, Any]]:
    return session_manager.list_sessions()


@app.post("/api/session/close")
def close_session(req: SessionIdReq) -> Dict[str, Any]:
    ok = session_manager.close_session(req.session_id)
    return {"success": ok}


@app.post("/api/session/close-all")
def close_all_sessions() -> Dict[str, Any]:
    session_manager.close_all()
    return {"success": True}


# ---------- Hook ----------

@app.post("/api/hook/java")
def hook_java(req: HookJavaReq) -> Dict[str, Any]:
    return hook_java_method_impl(req.session_id, req.class_name, req.method_name)


@app.post("/api/hook/native")
def hook_native(req: HookNativeReq) -> Dict[str, Any]:
    return hook_native_impl(
        req.session_id, req.module_name, req.func_name, req.offset
    )


@app.post("/api/hook/trace")
def hook_trace(req: HookJavaReq) -> Dict[str, Any]:
    return trace_method_impl(req.session_id, req.class_name)


# ---------- 消息 / 网络 / 日志 ----------

@app.get("/api/messages")
def get_messages(session_id: str, clear: bool = False) -> List[Dict[str, Any]]:
    return frida_client.get_messages(session_id, clear=clear)


@app.post("/api/network/start")
def network_start(req: NetworkStartReq) -> Dict[str, Any]:
    return start_capture_impl(
        req.session_id, capture_ssl=req.capture_ssl,
        capture_socket=req.capture_socket,
    )


@app.post("/api/network/stop")
def network_stop(req: SessionIdReq) -> Dict[str, Any]:
    return stop_capture_impl(req.session_id)


@app.get("/api/network/capture")
def network_capture(session_id: str, clear: bool = False) -> List[Dict[str, Any]]:
    return get_capture_impl(session_id, clear=clear)


@app.get("/api/logs/server")
def server_logs(max_entries: int = 100) -> List[Dict[str, Any]]:
    entries = list(get_log_buffer())[-max_entries:]
    return [
        {
            "time": str(e.get("time", "")),
            "level": e.get("level", None).name
            if hasattr(e.get("level", None), "name") else str(e.get("level")),
            "message": e.get("message", ""),
        }
        for e in entries
    ]


@app.post("/api/log/start")
def log_start(req: LogStartReq) -> Dict[str, Any]:
    from .modules.log import start_log
    key = req.session_id or "default"
    return start_log(key, package=req.package)


@app.post("/api/log/stop")
def log_stop(session_id: Optional[str] = None) -> Dict[str, Any]:
    from .modules.log import stop_log
    return stop_log(session_id or "default")


# ---------- 内存 ----------

@app.get("/api/memory/modules")
def memory_modules(session_id: str) -> List[Dict[str, Any]]:
    from .modules.memory import LIST_MODULES_TEMPLATE
    result = frida_client.execute_script(
        session_id, LIST_MODULES_TEMPLATE, script_name="list_modules"
    )
    return frida_client.call_script_function(
        session_id, result["script_id"], "list", []
    )


@app.post("/api/memory/read")
def memory_read(req: MemoryReadReq) -> Dict[str, Any]:
    from .modules.memory import MEMORY_READ_TEMPLATE
    import uuid
    script_id = f"read_{uuid.uuid4().hex[:8]}"
    result = frida_client.execute_script(
        req.session_id, MEMORY_READ_TEMPLATE, script_name=script_id
    )
    return frida_client.call_script_function(
        req.session_id, result["script_id"], "read", [req.address, req.size]
    )


# ---------- 生命周期 ----------

async def run_rest_server(host: str = None, port: int = None):
    """以 uvicorn 运行 REST API（供 app.py / desktop_app.py 后台启动）"""
    import uvicorn

    host = host or config.REST_HOST
    port = port or config.REST_PORT
    logger.info(f"REST API starting on {host}:{port}")
    config_uv = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config_uv)
    # 非主线程运行时跳过信号注册（与 MCP server 同款守卫）
    server.install_signal_handlers = lambda: None
    await server.serve()


def start_rest_background(host: str = None, port: int = None):
    """在后台线程启动 REST API（阻塞调用方友好）"""
    import threading

    def _run():
        try:
            asyncio.run(run_rest_server(host, port))
        except Exception as e:
            logger.error(f"REST API error: {e}")

    t = threading.Thread(target=_run, daemon=True, name="fridamcp-rest")
    t.start()
    return t
