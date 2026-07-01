#!/usr/bin/env python3
"""
FridaMCP GUI Application

一键启动 FridaMCP 图形界面，无需复杂命令行参数。
提供设备管理、进程管理、Hook、内存检查、网络监控、日志查看、APK 注入等全功能可视化操作。

用法:
    python app.py              # 启动 GUI（默认端口 7860）
    python app.py --port 8080  # 指定端口
    python app.py --mcp        # 同时启动 MCP 服务器（端口 8768）
"""

import sys
import os
import threading
import asyncio
import time
import json

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import gradio as gr

from fridamcp.config import config
from fridamcp.utils.logger import setup_logging, logger, get_log_buffer, clear_log_buffer
from fridamcp.core.device_manager import device_manager
from fridamcp.core.session_manager import session_manager
from fridamcp.core.frida_client import frida_client

# MCP 服务器后台线程
_mcp_thread = None
_mcp_running = False


# ============================================================
# 后台 MCP 服务器管理
# ============================================================

def start_mcp_server_background(host="0.0.0.0", port=8768, transport="sse"):
    """在后台线程启动 MCP 服务器"""
    global _mcp_thread, _mcp_running
    if _mcp_running:
        return "MCP 服务器已在运行中"

    def _run():
        global _mcp_running
        try:
            from fridamcp.server import create_mcp_server, run_sse_server, run_streamable_http_server
            mcp = create_mcp_server()
            _mcp_running = True
            logger.info(f"MCP server starting on {host}:{port} ({transport})")
            if transport == "sse":
                asyncio.run(run_sse_server(mcp, host, port))
            elif transport == "http":
                asyncio.run(run_streamable_http_server(mcp, host, port))
        except Exception as e:
            logger.error(f"MCP server error: {e}")
        finally:
            _mcp_running = False

    _mcp_thread = threading.Thread(target=_run, daemon=True)
    _mcp_thread.start()
    time.sleep(1)
    return f"MCP 服务器已启动: {host}:{port} ({transport})"


def stop_mcp_server():
    """停止 MCP 服务器"""
    global _mcp_running
    if not _mcp_running:
        return "MCP 服务器未运行"
    _mcp_running = False
    session_manager.close_all()
    return "MCP 服务器已停止（会话已清理）"


def get_mcp_status():
    """获取 MCP 服务器状态"""
    if _mcp_running:
        return "🟢 运行中"
    return "🔴 已停止"


# ============================================================
# 设备管理
# ============================================================

def refresh_devices():
    """刷新设备列表"""
    try:
        devices = device_manager.list_devices()
        if not devices:
            return "未发现设备", gr.Dropdown(choices=[], value=None)
        choices = [f"{d['id']} ({d['name']})" for d in devices]
        return f"发现 {len(devices)} 个设备", gr.Dropdown(choices=choices, value=choices[0])
    except Exception as e:
        return f"错误: {e}", gr.Dropdown(choices=[], value=None)


def connect_device(device_choice, device_type):
    """连接设备"""
    try:
        device_id = None
        if device_choice:
            device_id = device_choice.split(" (")[0]
        device = device_manager.get_device(device_id, device_type)
        info = device_manager.get_device_info()
        return f"✅ 已连接: {device.name}\n{json.dumps(info, indent=2, ensure_ascii=False)}"
    except Exception as e:
        return f"❌ 连接失败: {e}"


def reconnect_device():
    """重连设备"""
    try:
        device = device_manager.refresh()
        return f"✅ 重连成功: {device.name}"
    except Exception as e:
        return f"❌ 重连失败: {e}"


def get_device_status():
    """获取设备状态"""
    return device_manager.get_status()


# ============================================================
# 进程管理
# ============================================================

def list_processes():
    """列出进程"""
    try:
        procs = frida_client.list_processes()
        # 转换为 DataFrame 格式
        return procs[:200]  # 限制返回数量
    except Exception as e:
        return [{"pid": -1, "name": f"错误: {e}"}]


def list_apps():
    """列出应用"""
    try:
        apps = frida_client.list_applications()
        running = [a for a in apps if a.get("pid", 0) > 0]
        return apps[:200], f"共 {len(apps)} 个应用，{len(running)} 个运行中"
    except Exception as e:
        return [{"identifier": "error", "name": str(e), "pid": 0}], f"错误: {e}"


def spawn_app(package, paused=True):
    """启动应用"""
    try:
        result = frida_client.spawn(package, paused)
        return f"✅ 已启动: {package}\nPID: {result['pid']}\n会话ID: {result['session_id']}"
    except Exception as e:
        return f"❌ 启动失败: {e}"


def attach_process(target):
    """附加进程"""
    try:
        # 尝试转换为 int
        try:
            target = int(target)
        except ValueError:
            pass
        result = frida_client.attach(target)
        return f"✅ 已附加: {result['name']}\nPID: {result['pid']}\n会话ID: {result['session_id']}"
    except Exception as e:
        return f"❌ 附加失败: {e}"


def resume_process(pid):
    """恢复进程"""
    try:
        frida_client.resume(int(pid))
        return f"✅ 已恢复 PID {pid}"
    except Exception as e:
        return f"❌ 恢复失败: {e}"


def kill_process(pid):
    """杀死进程"""
    try:
        frida_client.kill(int(pid))
        return f"✅ 已杀死 PID {pid}"
    except Exception as e:
        return f"❌ 失败: {e}"


def list_sessions():
    """列出会话"""
    try:
        sessions = frida_client.list_sessions()
        if not sessions:
            return "无活跃会话"
        lines = []
        for s in sessions:
            lines.append(f"ID: {s['id']} | PID: {s['pid']} | 名称: {s['name']} | 脚本: {len(s['scripts'])} | Hook: {len(s['hooks'])} | 消息: {s['message_count']}")
        return "\n".join(lines)
    except Exception as e:
        return f"错误: {e}"


def close_session(session_id):
    """关闭会话"""
    try:
        frida_client.close_session(session_id)
        return f"✅ 已关闭会话: {session_id}"
    except Exception as e:
        return f"❌ 失败: {e}"


def close_all_sessions():
    """关闭所有会话"""
    try:
        count = len(session_manager.list_sessions())
        session_manager.close_all()
        return f"✅ 已关闭 {count} 个会话"
    except Exception as e:
        return f"❌ 失败: {e}"


# ============================================================
# Hook 管理
# ============================================================

def hook_java_method(session_id, class_name, method_name):
    """Hook Java 方法"""
    try:
        import uuid
        from fridamcp.modules.hook import HOOK_JAVA_METHOD_TEMPLATE
        hook_id = f"hook_{uuid.uuid4().hex[:8]}"
        source = HOOK_JAVA_METHOD_TEMPLATE % {
            "hook_id": hook_id,
            "class_name": class_name,
            "method_name": method_name,
        }
        result = frida_client.execute_script(session_id, source, script_name=hook_id)
        session = session_manager.get_session(session_id)
        if session:
            session.add_hook(hook_id, {
                "type": "java_method",
                "class_name": class_name,
                "method_name": method_name,
                "script_id": result["script_id"],
            })
        return f"✅ Hook 已安装\nHook ID: {hook_id}\nScript ID: {result['script_id']}"
    except Exception as e:
        return f"❌ Hook 失败: {e}"


def hook_native_func(session_id, module_name, func_name, offset):
    """Hook Native 函数"""
    try:
        import uuid
        from fridamcp.modules.hook import HOOK_NATIVE_TEMPLATE
        hook_id = f"native_{uuid.uuid4().hex[:8]}"
        off = int(offset) if offset else 0
        source = HOOK_NATIVE_TEMPLATE % {
            "hook_id": hook_id,
            "module_name": module_name,
            "func_name": func_name or "",
            "offset": off,
        }
        result = frida_client.execute_script(session_id, source, script_name=hook_id)
        session = session_manager.get_session(session_id)
        if session:
            session.add_hook(hook_id, {
                "type": "native",
                "module_name": module_name,
                "func_name": func_name,
                "offset": off,
                "script_id": result["script_id"],
            })
        return f"✅ Native Hook 已安装\nHook ID: {hook_id}"
    except Exception as e:
        return f"❌ Hook 失败: {e}"


def get_hook_messages(session_id, clear=False):
    """获取 Hook 消息"""
    try:
        messages = frida_client.get_messages(session_id, clear=clear)
        if not messages:
            return "无消息"
        lines = []
        for m in messages[-50:]:  # 最近50条
            msg = m.get("message", {})
            mtype = msg.get("type", "unknown")
            if mtype == "hook_call":
                lines.append(f"[CALL] {msg.get('className','')}.{msg.get('methodName','')} args={msg.get('args',[])}")
            elif mtype == "hook_return":
                lines.append(f"[RET]  {msg.get('className','')}.{msg.get('methodName','')} -> {msg.get('retval','')}")
            elif mtype == "hook_attached":
                lines.append(f"[INFO] Hook attached: {msg.get('hookId','')}")
            elif mtype == "error":
                lines.append(f"[ERR]  {msg.get('message','')}")
            else:
                lines.append(f"[{mtype}] {json.dumps(msg, ensure_ascii=False)[:200]}")
        return "\n".join(lines)
    except Exception as e:
        return f"错误: {e}"


def list_hooks(session_id):
    """列出 Hook"""
    try:
        session = session_manager.get_session(session_id)
        if session is None:
            return "会话不存在"
        if not session.hooks:
            return "无 Hook"
        lines = []
        for hid, info in session.hooks.items():
            lines.append(f"ID: {hid} | 类型: {info.get('type','')} | 详情: {json.dumps(info, ensure_ascii=False)}")
        return "\n".join(lines)
    except Exception as e:
        return f"错误: {e}"


def unhook(session_id, hook_id):
    """移除 Hook"""
    try:
        session = session_manager.get_session(session_id)
        if session is None:
            return "会话不存在"
        if not hook_id:
            count = len(session.hooks)
            session.unload_all_scripts()
            session.hooks.clear()
            return f"✅ 已移除所有 Hook（{count} 个）"
        info = session.hooks.get(hook_id)
        if info:
            session.unload_script(info["script_id"])
            session.remove_hook(hook_id)
            return f"✅ 已移除 Hook: {hook_id}"
        return f"Hook 不存在: {hook_id}"
    except Exception as e:
        return f"❌ 失败: {e}"


# ============================================================
# 内存检查
# ============================================================

def list_modules(session_id):
    """列出模块"""
    try:
        from fridamcp.modules.memory import LIST_MODULES_TEMPLATE
        result = frida_client.execute_script(session_id, LIST_MODULES_TEMPLATE, script_name="list_modules")
        modules = frida_client.call_script_function(session_id, result["script_id"], "list", [])
        return modules[:200] if modules else []
    except Exception as e:
        return [{"name": "error", "base": str(e), "size": 0, "path": ""}]


def search_memory(session_id, pattern, max_results=100):
    """搜索内存"""
    try:
        from fridamcp.modules.memory import MEMORY_SEARCH_TEMPLATE
        import uuid
        clean = pattern.replace(" ", "").replace("\\x", "")
        is_hex = all(c in "0123456789abcdefABCDEF" for c in clean) and len(clean) % 2 == 0
        if not is_hex:
            hex_pattern = " ".join(f"{ord(c):02x}" for c in pattern)
        else:
            hex_pattern = " ".join(clean[i:i+2] for i in range(0, len(clean), 2))

        script_id = f"search_{uuid.uuid4().hex[:8]}"
        result = frida_client.execute_script(session_id, MEMORY_SEARCH_TEMPLATE, script_name=script_id)
        ret = frida_client.call_script_function(session_id, result["script_id"], "search", [hex_pattern, int(max_results)])
        return json.dumps(ret, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"错误: {e}"


def read_memory(session_id, address, size=64):
    """读取内存"""
    try:
        from fridamcp.modules.memory import MEMORY_READ_TEMPLATE
        import uuid
        script_id = f"read_{uuid.uuid4().hex[:8]}"
        result = frida_client.execute_script(session_id, MEMORY_READ_TEMPLATE, script_name=script_id)
        ret = frida_client.call_script_function(session_id, result["script_id"], "read", [address, int(size)])
        return json.dumps(ret, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"错误: {e}"


# ============================================================
# 网络监控
# ============================================================

_network_capturing = False

def start_network_capture(session_id, capture_ssl=True):
    """开始网络捕获"""
    global _network_capturing
    try:
        from fridamcp.modules.network import SSL_HOOK_TEMPLATE, _capture_buffer, _capture_active
        import uuid
        _capture_buffer.clear()
        _capture_active[session_id] = True
        _network_capturing = True

        if capture_ssl:
            hook_id = f"ssl_{uuid.uuid4().hex[:8]}"
            source = SSL_HOOK_TEMPLATE % {"hook_id": hook_id}
            frida_client.execute_script(session_id, source, script_name=hook_id)

        return f"✅ 网络捕获已启动 (SSL={'开' if capture_ssl else '关'})"
    except Exception as e:
        return f"❌ 失败: {e}"


def stop_network_capture(session_id):
    """停止网络捕获"""
    global _network_capturing
    try:
        from fridamcp.modules.network import _capture_active
        _capture_active.pop(session_id, None)
        _network_capturing = False
        return "✅ 网络捕获已停止"
    except Exception as e:
        return f"❌ 失败: {e}"


def get_network_capture(session_id, clear=False):
    """获取网络捕获"""
    try:
        from fridamcp.modules.network import _capture_buffer
        items = list(_capture_buffer)
        if clear:
            _capture_buffer.clear()
        if not items:
            return "无捕获数据"
        lines = []
        for item in items[-100:]:
            t = item.get("type", "")
            data = item.get("data", "")
            if len(data) > 200:
                data = data[:200] + "..."
            ip = item.get("ip", "")
            port = item.get("port", "")
            size = item.get("size", "")
            if t == "ssl_write":
                lines.append(f"[SSL→] {size}B: {data}")
            elif t == "ssl_read":
                lines.append(f"[SSL←] {size}B: {data}")
            elif t == "socket_connect":
                lines.append(f"[CONN] {ip}:{port}")
            elif t == "socket_send":
                lines.append(f"[SEND] {size}B: {data}")
            else:
                lines.append(f"[{t}] {data}")
        return "\n".join(lines)
    except Exception as e:
        return f"错误: {e}"


# ============================================================
# 日志查看
# ============================================================

def get_server_logs(max_entries=100):
    """获取服务器日志"""
    try:
        buf = get_log_buffer()
        entries = list(buf)[-max_entries:]
        lines = []
        for e in entries:
            time_obj = e.get("time")
            level_obj = e.get("level")
            time_str = time_obj.isoformat() if hasattr(time_obj, "isoformat") else str(time_obj)
            level_str = level_obj.name if hasattr(level_obj, "name") else str(level_obj)
            msg = e.get("message", "")
            lines.append(f"[{time_str}] {level_str}: {msg}")
        return "\n".join(lines) if lines else "无日志"
    except Exception as e:
        return f"错误: {e}"


def clear_logs():
    """清空日志"""
    clear_log_buffer()
    return "日志已清空"


def get_frida_messages(session_id, clear=False):
    """获取 Frida 消息"""
    try:
        messages = frida_client.get_messages(session_id, clear=clear)
        if not messages:
            return "无消息"
        lines = []
        for m in messages[-100:]:
            msg = m.get("message", {})
            lines.append(json.dumps(msg, ensure_ascii=False)[:300])
        return "\n".join(lines)
    except Exception as e:
        return f"错误: {e}"


# ============================================================
# APK 注入器
# ============================================================

def inject_apk(input_apk, output_apk, arch, use_apktool, application_class):
    """注入 APK"""
    try:
        from fridamcp.utils.apk_injector import inject_gadget, inject_with_apktool
        if not input_apk:
            return "❌ 请选择输入 APK"
        if not output_apk:
            output_apk = input_apk.replace(".apk", "_injected.apk")

        if use_apktool:
            result = inject_with_apktool(input_apk, output_apk, arch=arch or None, application_class=application_class or None)
        else:
            result = inject_gadget(input_apk, output_apk, arch=arch or None)

        if result.get("success"):
            return f"✅ 注入成功!\n输出: {result.get('output_apk', output_apk)}\n架构: {result.get('archs', [])}"
        else:
            return f"❌ 注入失败: {result.get('error', '未知错误')}\n{result.get('detail','')}\n{result.get('note','')}"
    except Exception as e:
        return f"❌ 错误: {e}"


# ============================================================
# 构建 GUI 界面
# ============================================================

def create_app():
    """创建 Gradio 应用"""
    with gr.Blocks(
        title="FridaMCP - Android Frida 动态分析平台",
        theme=gr.themes.Soft(),
        css="""
        .header { text-align: center; margin-bottom: 20px; }
        .status-box { padding: 10px; border-radius: 8px; }
        """
    ) as app:

        # ===== 标题栏 =====
        gr.HTML("""
        <div class="header">
            <h1>🔧 FridaMCP - Android Frida 动态分析平台</h1>
            <p>AI-Powered Frida MCP Server | 端口 8768 | GUI 端口 7860</p>
        </div>
        """)

        with gr.Tabs():

            # ===== Tab 1: 仪表盘 =====
            with gr.Tab("📊 仪表盘"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### MCP 服务器")
                        mcp_status_display = gr.Textbox(label="MCP 状态", value=get_mcp_status(), interactive=False)
                        with gr.Row():
                            btn_start_mcp = gr.Button("启动 MCP", variant="primary")
                            btn_stop_mcp = gr.Button("停止 MCP", variant="stop")
                        mcp_result = gr.Textbox(label="操作结果", interactive=False)

                    with gr.Column(scale=1):
                        gr.Markdown("### 设备状态")
                        device_status_display = gr.JSON(label="设备状态", value=get_device_status)
                        btn_refresh_status = gr.Button("刷新状态")

                    with gr.Column(scale=1):
                        gr.Markdown("### 会话状态")
                        session_status_display = gr.JSON(label="会话状态", value=session_manager.get_status)
                        btn_refresh_session = gr.Button("刷新会话")

                with gr.Row():
                    gr.Markdown("### 快速操作")
                with gr.Row():
                    btn_close_all = gr.Button("关闭所有会话", variant="stop")
                    btn_reconnect = gr.Button("重连设备")
                    quick_result = gr.Textbox(label="结果", interactive=False)

                btn_start_mcp.click(fn=lambda: start_mcp_server_background(), outputs=mcp_result)
                btn_stop_mcp.click(fn=stop_mcp_server, outputs=mcp_result)
                btn_refresh_status.click(fn=get_device_status, outputs=device_status_display)
                btn_refresh_session.click(fn=session_manager.get_status, outputs=session_status_display)
                btn_close_all.click(fn=close_all_sessions, outputs=quick_result)
                btn_reconnect.click(fn=reconnect_device, outputs=quick_result)

            # ===== Tab 2: 设备 & 进程 =====
            with gr.Tab("📱 设备 & 进程"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 设备管理")
                        device_count = gr.Textbox(label="设备数量", interactive=False)
                        device_dropdown = gr.Dropdown(label="选择设备", choices=[])
                        device_type_radio = gr.Radio(["usb", "remote", "local"], label="设备类型", value="usb")
                        with gr.Row():
                            btn_refresh_dev = gr.Button("刷新设备")
                            btn_connect_dev = gr.Button("连接", variant="primary")
                            btn_reconnect_dev = gr.Button("重连")
                        device_info = gr.Textbox(label="设备信息", lines=8, interactive=False)

                    with gr.Column(scale=2):
                        gr.Markdown("### 进程管理")
                        with gr.Tab("进程列表"):
                            process_df = gr.Dataframe(
                                headers=["pid", "name"],
                                label="进程列表（前200个）",
                                value=list_processes,
                                interactive=False,
                            )
                            btn_refresh_proc = gr.Button("刷新进程")
                            btn_refresh_proc.click(fn=list_processes, outputs=process_df)

                        with gr.Tab("应用列表"):
                            app_df = gr.Dataframe(
                                headers=["identifier", "name", "pid"],
                                label="应用列表",
                                interactive=False,
                            )
                            app_count = gr.Textbox(label="统计", interactive=False)
                            btn_refresh_apps = gr.Button("刷新应用")
                            btn_refresh_apps.click(fn=list_apps, outputs=[app_df, app_count])

                        with gr.Tab("启动/附加"):
                            with gr.Row():
                                spawn_package = gr.Textbox(label="包名", placeholder="com.example.app")
                                btn_spawn = gr.Button("Spawn", variant="primary")
                                spawn_paused = gr.Checkbox(label="暂停启动", value=True)
                            with gr.Row():
                                attach_target = gr.Textbox(label="PID 或包名", placeholder="1234 或 com.example.app")
                                btn_attach = gr.Button("Attach", variant="primary")
                            with gr.Row():
                                resume_pid = gr.Textbox(label="PID", placeholder="恢复进程")
                                btn_resume = gr.Button("Resume")
                                kill_pid = gr.Textbox(label="PID", placeholder="杀死进程")
                                btn_kill = gr.Button("Kill", variant="stop")
                            proc_result = gr.Textbox(label="操作结果", lines=4, interactive=False)

                btn_refresh_dev.click(fn=refresh_devices, outputs=[device_count, device_dropdown])
                btn_connect_dev.click(fn=connect_device, inputs=[device_dropdown, device_type_radio], outputs=device_info)
                btn_reconnect_dev.click(fn=reconnect_device, outputs=device_info)
                btn_spawn.click(fn=spawn_app, inputs=[spawn_package, spawn_paused], outputs=proc_result)
                btn_attach.click(fn=attach_process, inputs=attach_target, outputs=proc_result)
                btn_resume.click(fn=resume_process, inputs=resume_pid, outputs=proc_result)
                btn_kill.click(fn=kill_process, inputs=kill_pid, outputs=proc_result)

            # ===== Tab 3: 会话管理 =====
            with gr.Tab("🔗 会话管理"):
                with gr.Row():
                    with gr.Column(scale=2):
                        session_display = gr.Textbox(label="活跃会话", lines=12, interactive=False, value=list_sessions)
                        with gr.Row():
                            btn_refresh_sessions = gr.Button("刷新")
                            btn_close_all_sess = gr.Button("关闭所有", variant="stop")
                        session_result = gr.Textbox(label="操作结果", interactive=False)
                    with gr.Column(scale=1):
                        gr.Markdown("### 关闭会话")
                        close_session_id = gr.Textbox(label="会话 ID", placeholder="sess_xxxx")
                        btn_close_session = gr.Button("关闭会话")

                btn_refresh_sessions.click(fn=list_sessions, outputs=session_display)
                btn_close_all_sess.click(fn=close_all_sessions, outputs=session_result)
                btn_close_session.click(fn=close_session, inputs=close_session_id, outputs=session_result)

            # ===== Tab 4: Hook 管理 =====
            with gr.Tab("🎣 Hook 管理"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Java 方法 Hook")
                        hook_session = gr.Textbox(label="会话 ID", placeholder="sess_xxxx")
                        hook_class = gr.Textbox(label="类名", placeholder="com.example.app.LoginActivity")
                        hook_method = gr.Textbox(label="方法名", placeholder="checkPassword")
                        btn_hook_java = gr.Button("安装 Hook", variant="primary")
                        hook_result = gr.Textbox(label="结果", lines=3, interactive=False)

                    with gr.Column(scale=1):
                        gr.Markdown("### Native 函数 Hook")
                        native_module = gr.Textbox(label="模块名", placeholder="libnative.so")
                        native_func = gr.Textbox(label="函数名（可选）", placeholder="Java_com_example_NativeMethod")
                        native_offset = gr.Textbox(label="偏移量（可选）", placeholder="0")
                        btn_hook_native = gr.Button("安装 Native Hook", variant="primary")
                        native_result = gr.Textbox(label="结果", lines=3, interactive=False)

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Hook 列表 & 管理")
                        hooks_display = gr.Textbox(label="已安装 Hook", lines=8, interactive=False)
                        with gr.Row():
                            btn_list_hooks = gr.Button("列出 Hook")
                            unhook_id = gr.Textbox(label="Hook ID（留空移除全部）")
                            btn_unhook = gr.Button("移除 Hook", variant="stop")

                    with gr.Column(scale=1):
                        gr.Markdown("### Hook 消息")
                        hook_msgs = gr.Textbox(label="捕获消息", lines=12, interactive=False)
                        with gr.Row():
                            btn_get_hook_msgs = gr.Button("获取消息")
                            btn_clear_hook_msgs = gr.Button("获取并清空")

                btn_hook_java.click(fn=hook_java_method, inputs=[hook_session, hook_class, hook_method], outputs=hook_result)
                btn_hook_native.click(fn=hook_native_func, inputs=[hook_session, native_module, native_func, native_offset], outputs=native_result)
                btn_list_hooks.click(fn=list_hooks, inputs=hook_session, outputs=hooks_display)
                btn_unhook.click(fn=unhook, inputs=[hook_session, unhook_id], outputs=hook_result)
                btn_get_hook_msgs.click(fn=get_hook_messages, inputs=[hook_session, gr.State(False)], outputs=hook_msgs)
                btn_clear_hook_msgs.click(fn=get_hook_messages, inputs=[hook_session, gr.State(True)], outputs=hook_msgs)

            # ===== Tab 5: 内存检查 =====
            with gr.Tab("🧠 内存检查"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 模块列表")
                        mem_session = gr.Textbox(label="会话 ID", placeholder="sess_xxxx")
                        btn_list_modules = gr.Button("列出模块")
                        modules_df = gr.Dataframe(
                            headers=["name", "base", "size", "path"],
                            label="已加载模块",
                            interactive=False,
                        )

                    with gr.Column(scale=1):
                        gr.Markdown("### 内存搜索")
                        search_pattern = gr.Textbox(label="搜索模式", placeholder="password 或 48 65 6c 6c 6f")
                        search_max = gr.Slider(10, 500, value=100, label="最大结果数")
                        btn_search_mem = gr.Button("搜索", variant="primary")
                        search_result = gr.Textbox(label="搜索结果", lines=8, interactive=False)

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### 内存读取")
                        with gr.Row():
                            read_addr = gr.Textbox(label="地址", placeholder="0x12345678")
                            read_size = gr.Slider(16, 4096, value=64, label="读取大小")
                        btn_read_mem = gr.Button("读取", variant="primary")
                        read_result = gr.Textbox(label="读取结果", lines=6, interactive=False)

                btn_list_modules.click(fn=list_modules, inputs=mem_session, outputs=modules_df)
                btn_search_mem.click(fn=search_memory, inputs=[mem_session, search_pattern, search_max], outputs=search_result)
                btn_read_mem.click(fn=read_memory, inputs=[mem_session, read_addr, read_size], outputs=read_result)

            # ===== Tab 6: 网络监控 =====
            with gr.Tab("🌐 网络监控"):
                gr.Markdown("### 网络流量捕获")
                net_session = gr.Textbox(label="会话 ID", placeholder="sess_xxxx")
                with gr.Row():
                    net_ssl = gr.Checkbox(label="捕获 SSL/HTTPS 明文", value=True)
                    btn_net_start = gr.Button("开始捕获", variant="primary")
                    btn_net_stop = gr.Button("停止捕获", variant="stop")
                    btn_net_get = gr.Button("获取数据")
                    btn_net_clear = gr.Button("获取并清空")
                net_result = gr.Textbox(label="操作结果", interactive=False)
                net_data = gr.Textbox(label="捕获数据", lines=15, interactive=False)

                btn_net_start.click(fn=start_network_capture, inputs=[net_session, net_ssl], outputs=net_result)
                btn_net_stop.click(fn=stop_network_capture, inputs=net_session, outputs=net_result)
                btn_net_get.click(fn=get_network_capture, inputs=[net_session, gr.State(False)], outputs=net_data)
                btn_net_clear.click(fn=get_network_capture, inputs=[net_session, gr.State(True)], outputs=net_data)

            # ===== Tab 7: 日志查看 =====
            with gr.Tab("📋 日志"):
                with gr.Tabs():
                    with gr.Tab("服务器日志"):
                        with gr.Row():
                            btn_get_logs = gr.Button("刷新日志")
                            btn_clear_logs = gr.Button("清空日志", variant="stop")
                        log_display = gr.Textbox(label="服务器日志", lines=20, interactive=False)
                        btn_get_logs.click(fn=get_server_logs, outputs=log_display)
                        btn_clear_logs.click(fn=clear_logs, outputs=log_display)

                    with gr.Tab("Frida 消息"):
                        frida_msg_session = gr.Textbox(label="会话 ID", placeholder="sess_xxxx")
                        with gr.Row():
                            btn_get_frida_msgs = gr.Button("获取消息")
                            btn_clear_frida_msgs = gr.Button("获取并清空")
                        frida_msg_display = gr.Textbox(label="Frida 消息", lines=20, interactive=False)
                        btn_get_frida_msgs.click(fn=get_frida_messages, inputs=[frida_msg_session, gr.State(False)], outputs=frida_msg_display)
                        btn_clear_frida_msgs.click(fn=get_frida_messages, inputs=[frida_msg_session, gr.State(True)], outputs=frida_msg_display)

            # ===== Tab 8: APK 注入器 =====
            with gr.Tab("💉 APK 注入器"):
                gr.Markdown("### Frida-Gadget APK 注入（无需 Root）")
                with gr.Row():
                    with gr.Column(scale=1):
                        inject_input = gr.Textbox(label="输入 APK 路径", placeholder="/path/to/app.apk")
                        inject_output = gr.Textbox(label="输出 APK 路径（留空自动）", placeholder="/path/to/app_injected.apk")
                        inject_arch = gr.Textbox(label="架构（留空自动）", placeholder="arm64-v8a")
                        inject_apktool = gr.Checkbox(label="使用 apktool（完整注入，推荐）", value=True)
                        inject_app_class = gr.Textbox(label="Application 类名（可选）", placeholder="com.example.app.MyApplication")
                        btn_inject = gr.Button("开始注入", variant="primary")

                    with gr.Column(scale=1):
                        inject_result = gr.Textbox(label="注入结果", lines=10, interactive=False)
                        gr.Markdown("""
                        ### 使用说明
                        1. 下载 frida-gadget 放入 `injector/frida_gadget/` 目录
                        2. 选择输入 APK
                        3. 勾选 apktool 进行完整注入
                        4. 注入后安装 APK: `adb install app_injected.apk`
                        5. 启动应用，frida-gadget 自动加载
                        6. 连接: `frida -U Gadget`
                        """)

                btn_inject.click(fn=inject_apk, inputs=[inject_input, inject_output, inject_arch, inject_apktool, inject_app_class], outputs=inject_result)

            # ===== Tab 9: 设置 =====
            with gr.Tab("⚙️ 设置"):
                gr.Markdown("### 配置信息")
                config_display = gr.JSON(label="当前配置", value={
                    "MCP_HOST": config.MCP_HOST,
                    "MCP_PORT": config.MCP_PORT,
                    "FRIDA_DEVICE_TYPE": config.FRIDA_DEVICE_TYPE,
                    "FRIDA_DEVICE_ID": config.FRIDA_DEVICE_ID,
                    "MAX_SESSIONS": config.MAX_SESSIONS,
                    "SCRIPT_TIMEOUT": config.SCRIPT_TIMEOUT,
                    "LOG_LEVEL": config.LOG_LEVEL,
                    "DEVICE_RECONNECT_MAX_RETRIES": config.DEVICE_RECONNECT_MAX_RETRIES,
                    "SESSION_KEEPALIVE_INTERVAL": config.SESSION_KEEPALIVE_INTERVAL,
                    "SERVER_AUTO_RESTART_MAX": config.SERVER_AUTO_RESTART_MAX,
                })
                gr.Markdown("""
                ### 环境变量配置

                | 变量 | 默认值 | 说明 |
                |------|--------|------|
                | FRIDAMCP_HOST | 0.0.0.0 | GUI 监听地址 |
                | FRIDAMCP_PORT | 8768 | MCP 服务器端口 |
                | FRIDA_DEVICE_TYPE | usb | 设备类型 |
                | FRIDA_DEVICE_ID | (空) | 设备 ID |
                | FRIDAMCP_LOG_LEVEL | INFO | 日志级别 |
                | FRIDAMCP_MAX_SESSIONS | 10 | 最大会话数 |
                | FRIDAMCP_RECONNECT_RETRIES | 5 | 设备重连次数 |
                | FRIDAMCP_KEEPALIVE_INTERVAL | 30 | 会话保活间隔 |
                | FRIDAMCP_AUTO_RESTART_MAX | 3 | 服务器自动重启次数 |

                ### 启动方式
                - **GUI 模式**: `python app.py`
                - **GUI + MCP**: `python app.py --mcp`
                - **仅 MCP**: `python -m fridamcp.server --transport sse`
                - **stdio 模式**: `python -m fridamcp.server --transport stdio`
                """)

    return app


# ============================================================
# 主入口
# ============================================================

def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="FridaMCP GUI - Android Frida 动态分析平台"
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="GUI 监听地址（默认 0.0.0.0）",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=7860,
        help="GUI 监听端口（默认 7860）",
    )
    parser.add_argument(
        "--mcp", action="store_true",
        help="同时启动 MCP 服务器（端口 8768）",
    )
    parser.add_argument(
        "--mcp-port", type=int, default=8768,
        help="MCP 服务器端口（默认 8768）",
    )
    parser.add_argument(
        "--device-type", default="usb",
        choices=["usb", "remote", "local"],
        help="Frida 设备类型（默认 usb）",
    )

    args = parser.parse_args()

    # 设置环境变量
    os.environ["FRIDA_DEVICE_TYPE"] = args.device_type

    # 初始化日志
    setup_logging()

    logger.info("=" * 60)
    logger.info("FridaMCP GUI - Android Frida 动态分析平台")
    logger.info("=" * 60)
    logger.info(f"GUI: http://0.0.0.0:{args.port}")
    if args.mcp:
        logger.info(f"MCP: http://0.0.0.0:{args.mcp_port}")
    logger.info("=" * 60)

    # 如果需要，启动 MCP 服务器
    if args.mcp:
        start_mcp_server_background(port=args.mcp_port)

    # 启动 GUI
    app = create_app()
    app.launch(
        server_name=args.host,
        server_port=args.port,
        share=False,
        inbrowser=True,
    )


if __name__ == "__main__":
    main()
