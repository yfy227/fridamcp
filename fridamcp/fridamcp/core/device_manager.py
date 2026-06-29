"""
设备管理模块

负责管理 Frida 设备连接，支持 USB 设备、远程设备、本地设备。
"""

from typing import List, Optional, Dict, Any

import frida

from ..config import config
from ..utils.logger import logger


class DeviceManager:
    """Frida 设备管理器"""

    _instance: Optional["DeviceManager"] = None
    _device: Optional[frida.core.Device] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
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
                        "icon": None,  # 图标暂不处理
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
        """获取指定设备

        Args:
            device_id: 设备 ID，None 表示使用配置中的默认设备
            device_type: 设备类型 (usb/remote/local)，None 表示使用配置默认值

        Returns:
            Frida Device 对象
        """
        try:
            dtype = device_type or config.FRIDA_DEVICE_TYPE
            did = device_id or config.FRIDA_DEVICE_ID

            if dtype == "remote":
                host = f"{config.FRIDA_REMOTE_HOST}:{config.FRIDA_REMOTE_PORT}"
                logger.info(f"Connecting to remote device: {host}")
                self._device = frida.get_device_manager().add_remote_device(host)
            elif did:
                logger.info(f"Getting device by id: {did}")
                self._device = frida.get_device(did)
            else:
                logger.info(f"Getting {dtype} device")
                self._device = frida.get_device_manager().get_device(dtype)

            logger.info(
                f"Using device: {self._device.name} (id={self._device.id}, "
                f"type={self._device.type})"
            )
            return self._device
        except Exception as e:
            logger.error(f"Failed to get device: {e}")
            raise

    def get_current_device(self) -> Optional[frida.core.Device]:
        """获取当前已连接的设备"""
        if self._device is None:
            try:
                return self.get_device()
            except Exception:
                return None
        return self._device

    def get_device_info(self) -> Dict[str, Any]:
        """获取当前设备详细信息"""
        dev = self.get_current_device()
        if dev is None:
            return {"error": "No device connected"}

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
            }
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return {"error": str(e)}

    def refresh(self):
        """刷新设备连接"""
        self._device = None
        return self.get_device()


# 全局设备管理器单例
device_manager = DeviceManager.get_instance()
