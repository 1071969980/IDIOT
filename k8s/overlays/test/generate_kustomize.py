#!/usr/bin/env python3
"""
Kustomize 资源分拆生成脚本

功能：
1. 读取 k8s/base/kustomization.yaml 的 resources 列表
2. 备份原文件
3. 对每个 resource 单独执行 kubectl kustomize，生成独立的 yaml 文件
4. 恢复原始 kustomization.yaml
"""

import shutil
import subprocess
from pathlib import Path

import yaml

# 配置路径
# 使用 resolve() 获取绝对路径，parent 向上导航到项目根目录
SCRIPT_DIR = Path(__file__).resolve().parent  # k8s/overlays/test/
BASE_DIR = SCRIPT_DIR.parent.parent.parent  # 项目根目录
KUSTOMIZATION_FILE = BASE_DIR / "k8s" / "base" / "kustomization.yaml"
BACKUP_FILE = BASE_DIR / "k8s" / "base" / "kustomization_bak.yaml"
OUTPUT_DIR = SCRIPT_DIR  # 输出到当前目录 k8s/overlays/test/
OVERLAY_DIR = "k8s/overlays/test/"


def read_kustomization() -> dict:
    """读取 kustomization.yaml 文件"""
    with open(KUSTOMIZATION_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_kustomization(data: dict) -> None:
    """写入 kustomization.yaml 文件"""
    with open(KUSTOMIZATION_FILE, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def backup_kustomization() -> None:
    """备份原始 kustomization.yaml"""
    shutil.copy2(KUSTOMIZATION_FILE, BACKUP_FILE)
    print(f"已备份: {BACKUP_FILE}")


def restore_kustomization() -> None:
    """恢复原始 kustomization.yaml 并删除备份"""
    shutil.copy2(BACKUP_FILE, KUSTOMIZATION_FILE)
    print(f"已恢复: {KUSTOMIZATION_FILE}")
    BACKUP_FILE.unlink()
    print(f"已删除备份: {BACKUP_FILE}")


def run_kustomize(output_file: str) -> bool:
    """执行 kubectl kustomize 命令"""
    output_path = OUTPUT_DIR / output_file
    cmd = ["kubectl", "kustomize", OVERLAY_DIR, "--output", str(output_path)]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=BASE_DIR)
        print(f"  ✓ 生成成功: {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ 生成失败: {output_file}")
        print(f"    错误: {e.stderr}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("Kustomize 资源分拆生成脚本")
    print("=" * 60)

    # 1. 读取原始配置
    original_data = read_kustomization()
    resources = original_data.get("resources", [])
    print(f"\n发现 {len(resources)} 个资源文件:")
    for res in resources:
        print(f"  - {res}")

    # 2. 备份原始文件
    print(f"\n备份原始文件...")
    backup_kustomization()

    # 3. 创建基础 kustomization 模板（不含 resources）
    base_kustomization = {
        "apiVersion": original_data.get("apiVersion"),
        "kind": original_data.get("kind"),
        "resources": [],
    }

    # 保留其他字段（如 commonLabels, patches 等）
    for key in original_data:
        if key not in ["apiVersion", "kind", "resources"]:
            base_kustomization[key] = original_data[key]

    # 4. 遍历每个资源文件
    print(f"\n开始逐个生成资源文件...")
    success_count = 0
    fail_count = 0

    for resource in resources:
        print(f"\n处理: {resource}")

        # 生成输出文件名（使用原文件名）
        output_filename = resource  # 如 "00-namespace.yaml"

        # 创建只包含当前资源的 kustomization.yaml
        current_kustomization = base_kustomization.copy()
        current_kustomization["resources"] = [resource]
        write_kustomization(current_kustomization)

        # 执行 kustomize
        if run_kustomize(output_filename):
            success_count += 1
        else:
            fail_count += 1

    # 5. 恢复原始文件
    print(f"\n恢复原始 kustomization.yaml...")
    restore_kustomization()

    # 6. 输出统计
    print("\n" + "=" * 60)
    print(f"完成! 成功: {success_count}, 失败: {fail_count}")
    print("=" * 60)

    return fail_count == 0


if __name__ == "__main__":
    import sys

    success = main()
    sys.exit(0 if success else 1)