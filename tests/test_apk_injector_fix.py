"""
APK 注入器修复验证测试

验证 v2.2 修复的关键问题：
  1. 重新打包保留原始 zip 条目顺序和压缩方式
  2. 注入前剥离原签名（META-INF/*.SF|*.RSA|*.MF）
  3. smali 注入正确处理 .locals 寄存器分配
  4. smali 注入跳过 .annotation 行
  5. APK 完整性验证
"""
import os
import io
import json
import zipfile
import tempfile
import pytest
from fridamcp.utils.apk_injector import (
    _is_signature_file,
    _repack_apk_safe,
    _patch_smali,
    _inject_into_method,
    _verify_apk_integrity,
    detect_apk_arch,
    detect_packer,
    GADGET_CONFIG_TEMPLATE,
)


@pytest.fixture
def sample_apk(tmp_path):
    """创建一个模拟 APK 文件（包含签名文件，测试剥离逻辑）"""
    apk_path = tmp_path / "sample.apk"
    with zipfile.ZipFile(apk_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 基本结构
        zf.writestr("AndroidManifest.xml", b"\x00" * 100)
        zf.writestr("classes.dex", b"\x00" * 200)
        zf.writestr("resources.arsc", b"\x00" * 100)
        # native libs（应保留 STORED）
        zf.writestr("lib/arm64-v8a/libnative.so", b"\x7fELF" + b"\x00" * 200, zipfile.ZIP_STORED)
        zf.writestr("lib/armeabi-v7a/libnative.so", b"\x7fELF" + b"\x00" * 200, zipfile.ZIP_STORED)
        # 签名文件（应被剥离）
        zf.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\n")
        zf.writestr("META-INF/CERT.SF", b"Signature-Version: 1.0\n")
        zf.writestr("META-INF/CERT.RSA", b"\x00" * 100)
    return str(apk_path)


@pytest.fixture
def gadget_dir(tmp_path, monkeypatch):
    """创建模拟 gadget 目录"""
    gadget_dir = tmp_path / "gadgets"
    gadget_dir.mkdir()
    # 创建模拟 gadget .so 文件
    for arch in ["arm64-v8a", "armeabi-v7a"]:
        gadget_path = gadget_dir / f"libfrida-gadget-{arch}.so"
        gadget_path.write_bytes(b"\x7fELF" + b"\x00" * 500)
    # patch config
    from fridamcp.config import config
    monkeypatch.setattr(config, "GADGET_DIR", str(gadget_dir))
    return str(gadget_dir)


class TestSignatureFileDetection:
    """签名文件检测测试"""

    def test_detect_manifest_mf(self):
        assert _is_signature_file("META-INF/MANIFEST.MF") is True

    def test_detect_cert_sf(self):
        assert _is_signature_file("META-INF/CERT.SF") is True

    def test_detect_cert_rsa(self):
        assert _is_signature_file("META-INF/CERT.RSA") is True

    def test_detect_cert_dsa(self):
        assert _is_signature_file("META-INF/CERT.DSA") is True

    def test_detect_lowercase(self):
        assert _is_signature_file("META-INF/cert.rsa") is True

    def test_not_signature_classes_dex(self):
        assert _is_signature_file("classes.dex") is False

    def test_not_signature_lib(self):
        assert _is_signature_file("lib/arm64-v8a/libnative.so") is False

    def test_not_signature_manifest(self):
        assert _is_signature_file("AndroidManifest.xml") is False


class TestRepackApkSafe:
    """安全重新打包测试"""

    def test_repack_strips_signature_files(self, sample_apk, tmp_path):
        """重新打包应剥离签名文件"""
        output = str(tmp_path / "output.apk")
        result = _repack_apk_safe(sample_apk, output, {})
        assert result["success"] is True
        assert result["stripped_signatures"] == 3  # MANIFEST.MF, CERT.SF, CERT.RSA

        # 验证输出 APK 不含签名文件
        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            assert "META-INF/MANIFEST.MF" not in names
            assert "META-INF/CERT.SF" not in names
            assert "META-INF/CERT.RSA" not in names

    def test_repack_preserves_entries(self, sample_apk, tmp_path):
        """重新打包应保留原始条目"""
        output = str(tmp_path / "output.apk")
        _repack_apk_safe(sample_apk, output, {})

        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            assert "AndroidManifest.xml" in names
            assert "classes.dex" in names
            assert "resources.arsc" in names
            assert "lib/arm64-v8a/libnative.so" in names
            assert "lib/armeabi-v7a/libnative.so" in names

    def test_repack_so_files_stored(self, sample_apk, tmp_path):
        """重新打包后 .so 文件应为 STORED 压缩方式"""
        output = str(tmp_path / "output.apk")
        _repack_apk_safe(sample_apk, output, {})

        with zipfile.ZipFile(output) as zf:
            for info in zf.infolist():
                if info.filename.endswith(".so"):
                    assert info.compress_type == zipfile.ZIP_STORED, \
                        f"{info.filename} should be STORED, got {info.compress_type}"

    def test_repack_adds_new_files(self, sample_apk, tmp_path):
        """重新打包应添加新文件"""
        # 创建一个临时 gadget 文件
        gadget_path = str(tmp_path / "libfrida-gadget.so")
        with open(gadget_path, "wb") as f:
            f.write(b"\x7fELF" + b"\x00" * 100)

        output = str(tmp_path / "output.apk")
        added = {"lib/arm64-v8a/libfrida-gadget.so": gadget_path}
        _repack_apk_safe(sample_apk, output, added)

        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            assert "lib/arm64-v8a/libfrida-gadget.so" in names
            # 验证内容
            data = zf.read("lib/arm64-v8a/libfrida-gadget.so")
            assert data.startswith(b"\x7fELF")

    def test_repack_added_so_is_stored(self, sample_apk, tmp_path):
        """添加的 .so 文件应为 STORED"""
        gadget_path = str(tmp_path / "libfrida-gadget.so")
        with open(gadget_path, "wb") as f:
            f.write(b"\x7fELF" + b"\x00" * 100)

        output = str(tmp_path / "output.apk")
        added = {"lib/arm64-v8a/libfrida-gadget.so": gadget_path}
        _repack_apk_safe(sample_apk, output, added)

        with zipfile.ZipFile(output) as zf:
            for info in zf.infolist():
                if "libfrida-gadget.so" in info.filename:
                    assert info.compress_type == zipfile.ZIP_STORED


class TestSmaliPatching:
    """smali 注入测试"""

    @pytest.fixture
    def smali_file(self, tmp_path):
        """创建一个模拟 smali 文件"""
        smali_path = tmp_path / "App.smali"
        smali_content = """.class public Lcom/example/App;
.super Landroid/app/Application;

.method public onCreate()V
    .locals 0

    invoke-super {p0}, Landroid/app/Application;->onCreate()V

    return-void
.end method
"""
        smali_path.write_text(smali_content)
        return str(smali_path)

    @pytest.fixture
    def smali_file_with_annotations(self, tmp_path):
        """创建带 annotation 的 smali 文件"""
        smali_path = tmp_path / "App2.smali"
        smali_content = """.class public Lcom/example/App2;
.super Landroid/app/Application;

.method public onCreate()V
    .locals 0
    .annotation build Landroidx/annotation/CallSuper;
    .end annotation

    invoke-super {p0}, Landroid/app/Application;->onCreate()V

    return-void
.end method
"""
        smali_path.write_text(smali_content)
        return str(smali_path)

    def test_patch_oncreate(self, smali_file):
        """应注入到 onCreate 方法"""
        result = _patch_smali(smali_file)
        assert result["success"] is True
        assert result["location"] == "onCreate"

        with open(smali_file) as f:
            content = f.read()
        assert 'const-string v0, "frida-gadget"' in content
        assert "loadLibrary" in content

    def test_patch_creates_backup(self, smali_file):
        """应创建备份文件"""
        _patch_smali(smali_file)
        assert os.path.exists(smali_file + ".bak")

    def test_patch_expands_locals(self, smali_file):
        """应自动扩容 .locals（0 -> 1）"""
        _patch_smali(smali_file)
        with open(smali_file) as f:
            content = f.read()
        # 原 .locals 0 应变为 .locals 1
        assert ".locals 1" in content

    def test_patch_skips_annotations(self, smali_file_with_annotations):
        """应跳过 .annotation 块，注入到正确位置"""
        _patch_smali(smali_file_with_annotations)
        with open(smali_file_with_annotations) as f:
            content = f.read()

        # loadLibrary 应在 .end annotation 之后
        end_annotation_idx = content.find(".end annotation")
        load_library_idx = content.find("loadLibrary")
        assert end_annotation_idx < load_library_idx

    def test_patch_preserves_original_code(self, smali_file):
        """应保留原始代码"""
        original = open(smali_file).read()
        _patch_smali(smali_file)
        patched = open(smali_file).read()
        # 原始的 invoke-super 应保留
        assert "invoke-super" in patched
        assert "return-void" in patched

    def test_inject_into_method_handles_no_locals(self):
        """_inject_into_method 应处理无 .locals 的情况"""
        content = """.method public foo()V

    invoke-super {p0}, Ljava/lang/Object;->foo()V
    return-void
.end method"""
        result = _inject_into_method(content, ".method public foo()V", "    nop\n")
        assert ".locals 1" in result or ".registers" in result

    def test_inject_into_method_expands_locals_zero(self):
        """_inject_into_method 应将 .locals 0 扩容为 1"""
        content = """.method public foo()V
    .locals 0

    return-void
.end method"""
        result = _inject_into_method(content, ".method public foo()V", "    nop\n")
        assert ".locals 1" in result


class TestVerifyApkIntegrity:
    """APK 完整性验证测试"""

    def test_verify_valid_apk(self, sample_apk):
        """应验证有效 APK"""
        result = _verify_apk_integrity(sample_apk)
        # aapt 可能不可用，但 zip 检查应通过
        assert result["apk_valid"] is True

    def test_verify_corrupted_apk(self, tmp_path):
        """应检测损坏的 APK"""
        bad_apk = str(tmp_path / "bad.apk")
        with open(bad_apk, "wb") as f:
            f.write(b"not a zip file")
        result = _verify_apk_integrity(bad_apk)
        assert result["apk_valid"] is False
        assert len(result["errors"]) > 0

    def test_verify_missing_manifest(self, tmp_path):
        """应检测缺少 AndroidManifest.xml 的 APK"""
        bad_apk = str(tmp_path / "no_manifest.apk")
        with zipfile.ZipFile(bad_apk, "w") as zf:
            zf.writestr("classes.dex", b"\x00")
        result = _verify_apk_integrity(bad_apk)
        assert result["apk_valid"] is False


class TestInjectGadgetIntegration:
    """inject_gadget 集成测试"""

    def test_inject_gadget_simple_mode(self, sample_apk, gadget_dir, tmp_path):
        """simple 模式应成功注入 gadget（不签名，无 apksigner）"""
        output = str(tmp_path / "injected.apk")
        from fridamcp.utils.apk_injector import inject_gadget
        result = inject_gadget(
            sample_apk,
            output,
            sign=False,  # 不签名（测试环境无 apksigner）
            skip_packer_check=True,
        )
        assert result.get("success") is True
        assert os.path.exists(output)
        assert result["archs"] == ["arm64-v8a", "armeabi-v7a"]
        assert result["stripped_signatures"] == 3

        # 验证输出 APK 包含 gadget
        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            assert "lib/arm64-v8a/libfrida-gadget.so" in names
            assert "lib/armeabi-v7a/libfrida-gadget.so" in names
            # 签名文件应被剥离
            assert "META-INF/MANIFEST.MF" not in names
            assert "META-INF/CERT.SF" not in names

    def test_inject_gadget_integrity_check(self, sample_apk, gadget_dir, tmp_path):
        """注入后应进行完整性检查"""
        output = str(tmp_path / "injected.apk")
        from fridamcp.utils.apk_injector import inject_gadget
        result = inject_gadget(
            sample_apk,
            output,
            sign=False,
            skip_packer_check=True,
        )
        assert result.get("success") is True
        assert "integrity_check" in result
        assert result["integrity_check"]["apk_valid"] is True

    def test_inject_gadget_so_files_stored(self, sample_apk, gadget_dir, tmp_path):
        """注入后 gadget .so 应为 STORED 压缩"""
        output = str(tmp_path / "injected.apk")
        from fridamcp.utils.apk_injector import inject_gadget
        inject_gadget(
            sample_apk,
            output,
            sign=False,
            skip_packer_check=True,
        )
        with zipfile.ZipFile(output) as zf:
            for info in zf.infolist():
                if info.filename.endswith(".so"):
                    assert info.compress_type == zipfile.ZIP_STORED, \
                        f"{info.filename} should be STORED"
