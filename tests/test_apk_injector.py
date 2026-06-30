"""
APK 注入器模块单元测试
"""
import os
import json
import zipfile
import tempfile
import pytest
from fridamcp.utils.apk_injector import (
    detect_packer,
    detect_apk_arch,
    GADGET_CONFIG_TEMPLATE,
    PACKER_SIGNATURES,
)


@pytest.fixture
def minimal_apk(tmp_path):
    """创建一个最小化的 APK 文件用于测试"""
    apk_path = tmp_path / "test.apk"
    with zipfile.ZipFile(apk_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("AndroidManifest.xml", b"\x00" * 100)
        zf.writestr("classes.dex", b"\x00" * 100)
        zf.writestr("lib/arm64-v8a/libtest.so", b"\x00" * 100)
        zf.writestr("lib/armeabi-v7a/libtest.so", b"\x00" * 100)
        zf.writestr("resources.arsc", b"\x00" * 100)
    return str(apk_path)


@pytest.fixture
def packed_apk(tmp_path):
    """创建一个模拟加固的 APK"""
    apk_path = tmp_path / "packed.apk"
    with zipfile.ZipFile(apk_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("AndroidManifest.xml", b"\x00" * 100)
        zf.writestr("classes.dex", b"\x00" * 100)
        # 梆梆加固特征
        zf.writestr("lib/armeabi-v7a/libsecexe.so", b"\x00" * 100)
        zf.writestr("lib/armeabi-v7a/libsecmain.so", b"\x00" * 100)
    return str(apk_path)


class TestPackerSignatures:
    """加固特征配置测试"""

    def test_packer_signatures_loaded(self):
        """应加载加固特征列表"""
        assert len(PACKER_SIGNATURES) > 0

    def test_known_packers_present(self):
        """应包含常见加固方案"""
        names = [name for name, _ in PACKER_SIGNATURES]
        assert "梆梆加固 (Bangcle)" in names
        assert "360 加固" in names
        assert any("腾讯" in n or "Legu" in n for n in names)

    def test_each_packer_has_signatures(self):
        """每个加固方案应有至少一个特征"""
        for name, sigs in PACKER_SIGNATURES:
            assert len(sigs) > 0, f"{name} has no signatures"


class TestDetectPacker:
    """加固检测测试"""

    def test_detect_no_packer(self, minimal_apk):
        """普通 APK 应检测为未加固"""
        result = detect_packer(minimal_apk)
        assert result["is_packed"] is False
        assert result["packer_name"] is None

    def test_detect_bangcle(self, packed_apk):
        """梆梆加固特征应被检测"""
        result = detect_packer(packed_apk)
        assert result["is_packed"] is True
        assert "Bangcle" in result["packer_name"] or "梆梆" in result["packer_name"]

    def test_detect_result_structure(self, minimal_apk):
        """检测结果应包含所有字段"""
        result = detect_packer(minimal_apk)
        assert "is_packed" in result
        assert "packer_name" in result
        assert "matched_signatures" in result
        assert "recommendation" in result


class TestDetectArch:
    """架构检测测试"""

    def test_detect_multi_arch(self, minimal_apk):
        """应检测出多个 ABI"""
        archs = detect_apk_arch(minimal_apk)
        assert "arm64-v8a" in archs
        assert "armeabi-v7a" in archs

    def test_detect_empty_apk(self, tmp_path):
        """无 lib 目录的 APK 应返回空列表"""
        apk_path = tmp_path / "empty.apk"
        with zipfile.ZipFile(apk_path, "w") as zf:
            zf.writestr("AndroidManifest.xml", b"\x00")
        archs = detect_apk_arch(str(apk_path))
        assert archs == []


class TestGadgetConfig:
    """Gadget 配置模板测试"""

    def test_config_has_interaction(self):
        """配置应包含 interaction 部分"""
        assert "interaction" in GADGET_CONFIG_TEMPLATE

    def test_config_default_port(self):
        """默认端口应为 27042"""
        assert GADGET_CONFIG_TEMPLATE["interaction"]["port"] == 27042

    def test_config_type_listen(self):
        """默认类型应为 listen"""
        assert GADGET_CONFIG_TEMPLATE["interaction"]["type"] == "listen"
