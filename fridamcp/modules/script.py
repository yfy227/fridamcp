"""
脚本执行模块

提供直接运行 Frida JavaScript 脚本的能力，让 AI 可以灵活地
编写和执行自定义 Frida 脚本，而不局限于预置的 Hook 模板。

核心工具:
  - run_script: 在会话中加载并执行 Frida JS 脚本
  - call_script_rpc: 调用脚本中 rpc.exports 导出的函数
  - unload_script: 卸载已加载的脚本
  - list_scripts: 列出会话中所有已加载的脚本
  - load_script_file: 从本地文件加载脚本
"""

import os
import uuid
from typing import Dict, Any, List, Optional

from ..core.frida_client import frida_client
from ..core.session_manager import session_manager
from ..utils.logger import logger


def register_tools(mcp):
    """向 MCP 服务器注册脚本执行工具"""

    @mcp.tool()
    def run_script(
        session_id: str,
        script_source: str,
        script_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """在目标会话中执行 Frida JavaScript 脚本

        这是核心工具，允许 AI 直接编写并运行任意 Frida JS 脚本。
        脚本可以通过 send() 发送消息回 MCP，也可以定义 rpc.exports
        供后续调用。

        常见用法:
          - Java Hook: Java.perform(() => { ... })
          - Native Hook: Interceptor.attach(Module.findExportByName(...), {...})
          - 内存读写: Memory.readByteArray / Memory.writeByteArray
          - 调用 RPC: rpc.exports = { myFunc: function() { ... } }

        Args:
            session_id: 会话 ID（通过 attach_process 或 spawn_app 获取）
            script_source: Frida JavaScript 脚本源码
            script_name: 可选，脚本名称（便于标识，默认自动生成）

        Returns:
            包含 script_id 和 session_id 的字典

        示例:
            # Hook Java 方法并发送消息
            run_script("sess_abc", \"""
                Java.perform(function() {
                    var Login = Java.use("com.example.LoginActivity");
                    Login.checkPassword.implementation = function(pwd) {
                        send({type: "hook", args: [pwd], retval: this.checkPassword(pwd)});
                        return true;
                    };
                });
            \""")
        """
        try:
            if not script_source or not script_source.strip():
                return {"error": "script_source is empty"}

            name = script_name or f"script_{uuid.uuid4().hex[:8]}"
            result = frida_client.execute_script(
                session_id, script_source, script_name=name
            )
            logger.info(f"Script '{name}' loaded in session {session_id}")
            return {
                "script_id": result["script_id"],
                "session_id": session_id,
                "script_name": name,
                "status": "loaded",
            }
        except Exception as e:
            logger.error(f"run_script failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def call_script_rpc(
        session_id: str,
        script_id: str,
        function_name: str,
        args: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """调用已加载脚本中 rpc.exports 导出的函数

        脚本通过 run_script 加载后，如果定义了 rpc.exports，
        可以用此工具调用其中的函数。

        Args:
            session_id: 会话 ID
            script_id: 脚本 ID（由 run_script 返回）
            function_name: rpc.exports 中定义的函数名
            args: 可选，参数列表

        Returns:
            包含函数返回值的字典

        示例:
            # 脚本中定义: rpc.exports = { getMemory: function(addr, size) { ... } }
            call_script_rpc("sess_abc", "script_xyz", "getMemory", ["0x1234", 64])
        """
        try:
            result = frida_client.call_script_function(
                session_id, script_id, function_name, args or []
            )
            return {
                "success": True,
                "result": result,
                "function_name": function_name,
                "script_id": script_id,
            }
        except Exception as e:
            logger.error(f"call_script_rpc failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def unload_script(
        session_id: str,
        script_id: str,
    ) -> Dict[str, Any]:
        """卸载已加载的 Frida 脚本

        卸载后脚本中的 Hook 将被移除，rpc.exports 也不再可用。

        Args:
            session_id: 会话 ID
            script_id: 脚本 ID

        Returns:
            操作结果
        """
        try:
            success = frida_client.unload_script(session_id, script_id)
            return {
                "success": success,
                "script_id": script_id,
                "session_id": session_id,
            }
        except Exception as e:
            logger.error(f"unload_script failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def list_scripts(session_id: str) -> List[Dict[str, Any]]:
        """列出会话中所有已加载的脚本

        Args:
            session_id: 会话 ID

        Returns:
            脚本列表，每个脚本包含 script_id 和名称
        """
        try:
            session = session_manager.get_session(session_id)
            if session is None:
                return [{"error": f"Session not found: {session_id}"}]

            scripts = []
            # session.scripts 是 dict: {script_id: frida_script}
            for sid, script in session.scripts.items():
                info = {"script_id": sid}
                # 尝试获取脚本名称
                try:
                    if hasattr(script, "name"):
                        info["name"] = script.name
                except Exception:
                    pass
                scripts.append(info)
            return scripts
        except Exception as e:
            logger.error(f"list_scripts failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def load_script_file(
        session_id: str,
        file_path: str,
    ) -> Dict[str, Any]:
        """从本地文件加载 Frida JavaScript 脚本

        读取指定路径的 .js 文件内容并在会话中执行。

        Args:
            session_id: 会话 ID
            file_path: 本地 JS 文件路径

        Returns:
            包含 script_id 的字典
        """
        try:
            if not os.path.isfile(file_path):
                return {"error": f"File not found: {file_path}"}

            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            name = os.path.basename(file_path)
            result = frida_client.execute_script(
                session_id, source, script_name=name
            )
            logger.info(f"Script file '{name}' loaded in session {session_id}")
            return {
                "script_id": result["script_id"],
                "session_id": session_id,
                "script_name": name,
                "file_path": file_path,
                "status": "loaded",
            }
        except Exception as e:
            logger.error(f"load_script_file failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def get_script_messages(
        session_id: str,
        clear: bool = False,
    ) -> List[Dict[str, Any]]:
        """获取会话中脚本通过 send() 发送的消息

        Frida 脚本中的 send() 消息会被缓存在会话中，
        通过此工具读取。这在 run_script 执行后用来获取脚本输出。

        Args:
            session_id: 会话 ID
            clear: 是否在读取后清空消息缓冲区（默认 False）

        Returns:
            消息列表
        """
        try:
            messages = frida_client.get_messages(session_id, clear=clear)
            return messages
        except Exception as e:
            logger.error(f"get_script_messages failed: {e}")
            return [{"error": str(e)}]

    logger.info("Script module tools registered")
