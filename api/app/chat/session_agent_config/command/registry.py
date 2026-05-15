from typing import Dict, Any, Type
import importlib
import pkgutil
from pathlib import Path

COMMAND_REGISTRY: Dict[str, Dict[str, Any]] = {}

_SKIP_MODULES = frozenset(['registry', 'base'])


def _discover_commands(dir_path: Path, prefix: str = '') -> None:
    """
    递归遍历 command/ 目录，自动发现并注册命令。

    约定：
    - 每个命令包内的 __init__.py 应导出：
      - Command = 具体命令类
      - Input = 输入模型
      - Output = 输出模型
    - 嵌套命令的注册 key 使用点号分隔，如 file_system.project.create
    """
    package_name = __name__.rsplit('.', 1)[0]

    for _, module_name, is_pkg in pkgutil.iter_modules([str(dir_path)]):
        if module_name in _SKIP_MODULES or not is_pkg:
            continue

        full_name = f"{prefix}.{module_name}" if prefix else module_name
        import_name = f'.{prefix}.{module_name}' if prefix else f'.{module_name}'

        try:
            module = importlib.import_module(import_name, package=package_name)

            if hasattr(module, 'Command') and hasattr(module, 'Input') and hasattr(module, 'Output'):
                COMMAND_REGISTRY[full_name] = {
                    'command_class': module.Command,
                    'input_model': module.Input,
                    'output_model': module.Output
                }
            else:
                print(f"Command module '{full_name}' missing required exports (Command, Input, Output)")
        except Exception as e:
            print(f"Failed to load command module '{full_name}': {e}")

        # 递归进入子目录
        _discover_commands(dir_path / module_name, full_name)


def register_command(name: str, command_class: Type, input_model: Type, output_model: Type):
    """
    注册新命令的辅助函数
    """
    COMMAND_REGISTRY[name] = {
        'command_class': command_class,
        'input_model': input_model,
        'output_model': output_model
    }


# 初始化时自动发现命令
_discover_commands(Path(__file__).parent)
