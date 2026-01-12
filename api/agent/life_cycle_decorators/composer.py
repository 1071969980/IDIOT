"""
方法组合模块

将多个函数（钩子和原方法）组合成一个新的函数。
"""

import functools
from typing import Callable, Any


class MethodComposer:
    """组合生命周期方法实现"""

    @staticmethod
    def compose_async(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合异步方法，先执行 wrapper，再执行 base_method

        执行顺序：wrapper → base_method
        返回值：base_method 的返回值

        Args:
            base_method: 基础方法
            wrapper: 包装方法（钩子）

        Returns:
            组合后的方法
        """
        @functools.wraps(base_method)
        async def composed(self, *args, **kwargs):
            # 先执行钩子
            await wrapper(self, *args, **kwargs)
            # 再执行原方法
            result = await base_method(self, *args, **kwargs)
            return result

        return composed

    @staticmethod
    def compose_async_with_return(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合异步方法，将 base_method 的返回值传递给 wrapper

        执行顺序：base_method → wrapper（接收返回值）
        返回值：wrapper 的返回值

        Args:
            base_method: 基础方法
            wrapper: 包装方法（钩子），接收原方法的返回值

        Returns:
            组合后的方法
        """
        @functools.wraps(base_method)
        async def composed(self, *args, **kwargs):
            # 先执行原方法
            base_result = await base_method(self, *args, **kwargs)
            # 将返回值传给钩子
            result = await wrapper(self, base_result, *args, **kwargs)
            return result

        return composed

    @staticmethod
    def compose_sync(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合同步方法（不修改返回值）

        执行顺序：wrapper → base_method
        返回值：base_method 的返回值

        Args:
            base_method: 基础方法
            wrapper: 包装方法（钩子）

        Returns:
            组合后的方法
        """
        @functools.wraps(base_method)
        def composed(self, *args, **kwargs):
            wrapper(self, *args, **kwargs)
            result = base_method(self, *args, **kwargs)
            return result

        return composed

    @staticmethod
    def compose_sync_with_return(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合同步方法（修改返回值）

        执行顺序：base_method → wrapper（接收返回值）
        返回值：wrapper 的返回值

        Args:
            base_method: 基础方法
            wrapper: 包装方法（钩子），接收原方法的返回值

        Returns:
            组合后的方法
        """
        @functools.wraps(base_method)
        def composed(self, *args, **kwargs):
            base_result = base_method(self, *args, **kwargs)
            result = wrapper(self, base_result, *args, **kwargs)
            return result

        return composed

    @staticmethod
    def compose_async_after_no_return(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合异步方法，先执行 base_method，再执行 wrapper，不修改返回值

        执行顺序：base_method → wrapper
        返回值：base_method 的返回值

        Args:
            base_method: 基础方法
            wrapper: 包装方法（钩子）

        Returns:
            组合后的方法
        """
        @functools.wraps(base_method)
        async def composed(self, *args, **kwargs):
            # 先执行原方法
            result = await base_method(self, *args, **kwargs)
            # 再执行钩子
            await wrapper(self, *args, **kwargs)
            # 返回原方法的返回值
            return result

        return composed

    @staticmethod
    def compose_sync_after_no_return(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合同步方法，先执行 base_method，再执行 wrapper，不修改返回值

        执行顺序：base_method → wrapper
        返回值：base_method 的返回值

        Args:
            base_method: 基础方法
            wrapper: 包装方法（钩子）

        Returns:
            组合后的方法
        """
        @functools.wraps(base_method)
        def composed(self, *args, **kwargs):
            # 先执行原方法
            result = base_method(self, *args, **kwargs)
            # 再执行钩子
            wrapper(self, *args, **kwargs)
            # 返回原方法的返回值
            return result

        return composed
