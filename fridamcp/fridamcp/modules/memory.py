"""
内存检查模块

提供内存读取、写入、搜索、模块列表、导出函数列表等工具。
"""

import uuid
from typing import Dict, Any, List, Optional

from ..core.frida_client import frida_client
from ..utils.logger import logger


MEMORY_READ_TEMPLATE = """
(function() {
    rpc.exports = {
        read: function(address, size) {
            try {
                var ptr = new Ptr(address);
                var bytes = Memory.readByteArray(ptr, size);
                return Array.from(new Uint8Array(bytes)).map(function(b) {
                    return ('00' + b.toString(16)).slice(-2);
                }).join('');
            } catch(e) {
                return { error: e.message };
            }
        }
    };
})();
"""

MEMORY_WRITE_TEMPLATE = """
(function() {
    rpc.exports = {
        write: function(address, hexData) {
            try {
                var ptr = new Ptr(address);
                var bytes = [];
                for (var i = 0; i < hexData.length; i += 2) {
                    bytes.push(parseInt(hexData.substr(i, 2), 16));
                }
                var buf = Memory.allocUtf8String("");
                for (var i = 0; i < bytes.length; i++) {
                    buf.add(i).writeU8(bytes[i]);
                }
                Memory.copy(ptr, buf, bytes.length);
                return { success: true, written: bytes.length };
            } catch(e) {
                return { error: e.message };
            }
        }
    };
})();
"""

MEMORY_SEARCH_TEMPLATE = """
(function() {
    rpc.exports = {
        search: function(pattern, maxResults) {
            maxResults = maxResults || 100;
            var results = [];
            var ranges = Process.enumerateRanges('r--');
            for (var i = 0; i < ranges.length; i++) {
                var range = ranges[i];
                try {
                    var matches = Memory.scanSync(range.base, range.size, pattern);
                    for (var j = 0; j < matches.length; j++) {
                        results.push({
                            address: matches[j].address.toString(),
                            size: matches[j].size
                        });
                        if (results.length >= maxResults) {
                            return { results: results, truncated: true };
                        }
                    }
                } catch(e) {
                    // skip unreadable ranges
                }
            }
            return { results: results, truncated: false };
        }
    };
})();
"""

LIST_MODULES_TEMPLATE = """
(function() {
    rpc.exports = {
        list: function() {
            var modules = Process.enumerateModules();
            return modules.map(function(m) {
                return {
                    name: m.name,
                    base: m.base.toString(),
                    size: m.size,
                    path: m.path
                };
            });
        }
    };
})();
"""

LIST_EXPORTS_TEMPLATE = """
(function() {
    rpc.exports = {
        list: function(moduleName) {
            var module = Process.findModuleByName(moduleName);
            if (!module) {
                return { error: "Module not found: " + moduleName };
            }
            var exports = module.enumerateExports();
            return exports.map(function(e) {
                return {
                    name: e.name,
                    address: e.address.toString(),
                    type: e.type
                };
            });
        }
    };
})();
"""


def register_tools(mcp):
    """向 MCP 服务器注册内存检查工具"""

    @mcp.tool()
    def list_modules(session_id: str) -> List[Dict[str, Any]]:
        """列出进程加载的所有模块（.so 库等）

        Args:
            session_id: 会话 ID

        Returns:
            模块列表，每个模块包含 name、base、size、path
        """
        try:
            result = frida_client.execute_script(
                session_id, LIST_MODULES_TEMPLATE, script_name="list_modules"
            )
            modules = frida_client.call_script_function(
                session_id, result["script_id"], "list", []
            )
            return modules
        except Exception as e:
            logger.error(f"list_modules failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def list_exports(
        session_id: str,
        module_name: str,
    ) -> List[Dict[str, Any]]:
        """列出模块的导出函数

        Args:
            session_id: 会话 ID
            module_name: 模块名，例如 libnative.so

        Returns:
            导出函数列表，每个函数包含 name、address、type
        """
        try:
            script_id = f"exports_{uuid.uuid4().hex[:8]}"
            result = frida_client.execute_script(
                session_id, LIST_EXPORTS_TEMPLATE, script_name=script_id
            )
            exports = frida_client.call_script_function(
                session_id, result["script_id"], "list", [module_name]
            )
            if isinstance(exports, dict) and "error" in exports:
                return [exports]
            return exports
        except Exception as e:
            logger.error(f"list_exports failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    def read_memory(
        session_id: str,
        address: str,
        size: int = 64,
    ) -> Dict[str, Any]:
        """读取进程内存

        Args:
            session_id: 会话 ID
            address: 内存地址（十六进制字符串，例如 0x12345678 或 12345678）
            size: 读取字节数（默认 64）

        Returns:
            包含 hex（十六进制数据）和 ascii（ASCII 表示）的字典
        """
        try:
            script_id = f"read_{uuid.uuid4().hex[:8]}"
            result = frida_client.execute_script(
                session_id, MEMORY_READ_TEMPLATE, script_name=script_id
            )
            hex_data = frida_client.call_script_function(
                session_id, result["script_id"], "read", [address, size]
            )
            if isinstance(hex_data, dict) and "error" in hex_data:
                return hex_data
            # 转换为 ASCII
            ascii_str = ""
            for i in range(0, len(hex_data), 2):
                byte = int(hex_data[i:i+2], 16)
                ascii_str += chr(byte) if 32 <= byte < 127 else "."
            return {
                "address": address,
                "size": size,
                "hex": hex_data,
                "ascii": ascii_str,
            }
        except Exception as e:
            logger.error(f"read_memory failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def write_memory(
        session_id: str,
        address: str,
        hex_data: str,
    ) -> Dict[str, Any]:
        """写入进程内存

        Args:
            session_id: 会话 ID
            address: 内存地址（十六进制字符串）
            hex_data: 要写入的十六进制数据（例如 41424344）

        Returns:
            操作结果
        """
        try:
            script_id = f"write_{uuid.uuid4().hex[:8]}"
            result = frida_client.execute_script(
                session_id, MEMORY_WRITE_TEMPLATE, script_name=script_id
            )
            ret = frida_client.call_script_function(
                session_id, result["script_id"], "write", [address, hex_data]
            )
            return ret
        except Exception as e:
            logger.error(f"write_memory failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    def search_memory(
        session_id: str,
        pattern: str,
        max_results: int = 100,
    ) -> Dict[str, Any]:
        """在进程内存中搜索模式

        Args:
            session_id: 会话 ID
            pattern: 搜索模式，支持十六进制（例如 48 65 6c 6c 6f）或 ASCII 字符串
            max_results: 最大结果数（默认 100）

        Returns:
            包含 results（匹配地址列表）和 truncated 的字典
        """
        try:
            # 如果 pattern 不是十六进制格式，转换为十六进制
            clean = pattern.replace(" ", "").replace("\\x", "")
            is_hex = all(c in "0123456789abcdefABCDEF" for c in clean) and len(clean) % 2 == 0
            if not is_hex:
                # 当作 ASCII 字符串处理
                hex_pattern = " ".join(
                    f"{ord(c):02x}" for c in pattern
                )
            else:
                hex_pattern = " ".join(
                    clean[i:i+2] for i in range(0, len(clean), 2)
                )

            script_id = f"search_{uuid.uuid4().hex[:8]}"
            result = frida_client.execute_script(
                session_id, MEMORY_SEARCH_TEMPLATE, script_name=script_id
            )
            ret = frida_client.call_script_function(
                session_id, result["script_id"], "search",
                [hex_pattern, max_results]
            )
            return ret
        except Exception as e:
            logger.error(f"search_memory failed: {e}")
            return {"error": str(e)}

    logger.info("Memory module tools registered")
