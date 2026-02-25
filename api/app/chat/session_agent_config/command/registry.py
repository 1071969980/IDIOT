from typing import Dict, Any, Type
import importlib
import pkgutil
from pathlib import Path

COMMAND_REGISTRY: Dict[str, Dict[str, Any]] = {}


def _discover_commands() -> None:
    """
    使用 importlib 动态遍历 command/ 目录，自动发现并注册命令。

    约定：
    - 每个命令包内的 __init__.py 应导出：
      - Command = 具体命令类
      - Input = 输入模型
      - Output = 输出模型
    """
    # 获取当前包的路径
    current_dir = Path(__file__).parent
    package_name = __name__.rsplit('.', 1)[0]

    # 遍历当前目录下的所有子模块/子包
    for _, module_name, is_pkg in pkgutil.iter_modules([str(current_dir)]):
        # 跳过当前模块和非包目录
        if module_name == 'registry' or module_name == 'base' or not is_pkg:
            continue

        try:
            # 动态导入命令包
            module = importlib.import_module(f'.{module_name}', package=package_name)

            # 获取导出的 Command、Input、Output
            if hasattr(module, 'Command') and hasattr(module, 'Input') and hasattr(module, 'Output'):
                COMMAND_REGISTRY[module_name] = {
                    'command_class': module.Command,
                    'input_model': module.Input,
                    'output_model': module.Output
                }
            else:
                print(f"Command module '{module_name}' missing required exports (Command, Input, Output)")
        except Exception as e:
            print(f"Failed to load command module '{module_name}': {e}")


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
_discover_commands()
