"""
设备管理模块

负责管理 Frida 设备连接，支持 USB 设备、远程设备、本地设备。
包含自动重连、连接状态监控和错误恢复机制。
"""

import time
import threading
from typing import List, Optional, Dict, Any

import frida

from ..config import config
from ..utils.logger import logger


class DeviceManager:
    """Frida 设备管理器（单例）

    提供设备连接管理，支持自动重连和连接状态监控。
    """

    _instance: Optional["DeviceManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._device = None
            cls._instance._device_type = None
            cls._instance._device_id = None
            cls._instance._connected_at = None
            cls._instance._reconnect_count = 0
        return cls._instance

    @classmethod
    def get_instance(cls) -> "DeviceManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def list_devices(self) -> List[Dict[str, Any]]:
        """列出所有可用设备

        Returns:
            设备列表，每个设备包含 id, name, type 信息
        """
        try:
            devices = frida.enumerate_devices()
            result = []
            for dev in devices:
                result.append(
                    {
                        "id": dev.id,
                        "name": dev.name,
                        "type": dev.type,
                    }
                )
            logger.info(f"Found {len(result)} devices")
            return result
        except Exception as e:
            logger.error(f"Failed to list devices: {e}")
            raise

    def get_device(
        self,
        device_id: Optional[str] = None,
        device_type: Optional[str] = None,
    ) -> frida.core.Device:
        """获取指定设备（带重试机制）

        Args:
            device_id: 设备 ID，None 表示使用配置中的默认设备
            device_type: 设备类型 (usb/remote/local)，None 表示使用配置默认值

        Returns:
            Frida Device 对象

        Raises:
            RuntimeError: 当所有重试均失败时
        """
        dtype = device_type or config.FRIDA_DEVICE_TYPE
        did = device_id or config.FRIDA_DEVICE_ID

        # 如果已有连接且参数一致，直接返回
        if self._device is not None and self._is_same_target(dtype, did):
            try:
                # 验证连接是否仍然有效
                self._device.query_system_parameters()
                return self._device
            except Exception as e:
                logger.warning(f"Existing device connection lost: {e}, reconnecting...")
                self._device = None

        # 带重试的连接
        max_retries = max(1, config.DEVICE_RECONNECT_MAX_RETRIES)
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                if dtype == "remote":
                    host = f"{config.FRIDA_REMOTE_HOST}:{config.FRIDA_REMOTE_PORT}"
                    logger.info(f"Connecting to remote device: {host} (attempt {attempt}/{max_retries})")
                    self._device = frida.get_device_manager().add_remote_device(host)
                elif did:
                    logger.info(f"Getting device by id: {did} (attempt {attempt}/{max_retries})")
                    self._device = frida.get_device(did)
                else:
                    logger.info(f"Getting {dtype} device (attempt {attempt}/{max_retries})")
                    self._device = frida.get_device_manager().get_device(dtype)

                # 验证连接
                self._device.query_system_parameters()

                self._device_type = dtype
                self._device_id = self._normalise_device_id(dtype, did)
                self._connected_at = time.time()
                self._reconnect_count = attempt - 1

                logger.info(
                    f"Using device: {self._device.name} "
                    f"(id={self._device.id}, type={self._device.type})"
                )
                return self._device

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Device connection attempt {attempt}/{max_retries} failed: {e}"
                )
                self._device = None
                if attempt < max_retries:
                    time.sleep(config.DEVICE_RECONNECT_INTERVAL)

        raise RuntimeError(
            f"Failed to connect to device after {max_retries} attempts: {last_error}"
        )

    def _is_same_target(self, dtype: str, did: Optional[str]) -> bool:
        """检查目标设备是否与当前连接一致。"""
        return self._device_type == dtype and self._device_id == self._normalise_device_id(dtype, did)

    def _normalise_device_id(self, dtype: str, did: Optional[str]) -> Optional[str]:
        """规范化缓存中的设备标识。"""
        if dtype == "remote":
            return f"{config.FRIDA_REMOTE_HOST}:{config.FRIDA_REMOTE_PORT}"
        return did

    def get_current_device(self) -> Optional[frida.core.Device]:
        """获取当前已连接的设备（不触发重连）

        如果设备未连接，返回 None 而不是阻塞重连。
        调用方应检查返回值并提示用户先 select_device。
        """
        if self._device is None:
            return None
        # 验证现有连接是否仍然有效
        try:
            self._device.query_system_parameters()
            return self._device
        except Exception:
            self._device = None
            return None

    def get_device_info(self) -> Dict[str, Any]:
        """获取当前设备详细信息"""
        dev = self.get_current_device()
        if dev is None:
            return {"error": "No device connected", "connected": False}

        try:
            params = dev.query_system_parameters()
            return {
                "id": dev.id,
                "name": dev.name,
                "type": dev.type,
                "os": params.get("os", {}),
                "arch": params.get("arch"),
                "frida_version": params.get("frida-version"),
                "hostname": params.get("hostname"),
                "connected": True,
                "connected_at": self._connected_at,
                "reconnect_count": self._reconnect_count,
            }
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            # 连接失效，清除缓存
            self._device = None
            return {"error": str(e), "connected": False}

    def is_connected(self) -> bool:
        """检查设备是否已连接且可用"""
        if self._device is None:
            return False
        try:
            self._device.query_system_parameters()
            return True
        except Exception:
            self._device = None
            return False

    def refresh(self) -> frida.core.Device:
        """刷新设备连接（强制重新连接）。

        remote 连接的缓存 ID 是 host:port，不能作为 device_id 传回
        get_device；local/usb 且未显式指定 ID 时也应保持 device_id=None。
        """
        with self._lock:
            dtype = self._device_type or config.FRIDA_DEVICE_TYPE
            did = self._device_id if dtype != "remote" else None
            self._device = None
            self._connected_at = None
        return self.get_device(device_id=did, device_type=dtype)

    def get_status(self) -> Dict[str, Any]:
        """获取设备管理器状态"""
        return {
            "connected": self._device is not None and self.is_connected(),
            "device_type": self._device_type,
            "device_id": self._device_id,
            "connected_at": self._connected_at,
            "reconnect_count": self._reconnect_count,
        }


# 全局设备管理器单例
device_manager = DeviceManager.get_instance()
