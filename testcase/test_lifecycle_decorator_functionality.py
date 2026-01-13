#!/usr/bin/env python3
"""
AgentBase 生命周期装饰器系统 - 功能完整性验证测试

本脚本验证装饰器系统的所有功能点：
1. 核心装饰器功能
2. 签名验证功能
3. 方法组合功能
4. 生命周期方法支持
"""

import asyncio
import inspect
import sys
from typing import Any

# 添加项目路径
sys.path.insert(0, '/home/gmh/桌面/IDIOT')

from api.agent.life_cycle_decorators import (
    lifecycle_hook,
    agent_decorator,
    HookPosition,
    SignatureMismatchError,
)
from api.agent.base_agent import AgentBase
from unittest.mock import MagicMock


# ============ 辅助函数 ============

def create_test_agent(cls, **kwargs):
    """创建测试用的 agent 实例，提供必要的 mock 参数"""
    cancel_event = asyncio.Event()
    tools = []
    tool_call_function = {}
    return cls(cancel_event, tools, tool_call_function, **kwargs)


# ============ 测试收集器 ============
test_results = []


def test_case(name: str, category: str):
    """测试用例装饰器"""
    def decorator(func):
        def wrapper():
            try:
                result = func()
                test_results.append({
                    'name': name,
                    'category': category,
                    'status': 'PASS',
                    'message': 'OK'
                })
                print(f"  [PASS] {name}")
                return result
            except AssertionError as e:
                test_results.append({
                    'name': name,
                    'category': category,
                    'status': 'FAIL',
                    'message': str(e)
                })
                print(f"  [FAIL] {name}: {e}")
                return False
            except Exception as e:
                test_results.append({
                    'name': name,
                    'category': category,
                    'status': 'ERROR',
                    'message': f'{type(e).__name__}: {e}'
                })
                print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
                return False
        wrapper.test_name = name
        return wrapper
    return decorator


# ============ 1. 核心装饰器功能测试 ============

@test_case("lifecycle_hook 装饰器能正确创建钩子函数", "核心装饰器功能")
def test_lifecycle_hook_creates_hook():
    @lifecycle_hook('on_agent_start')
    async def my_hook(self, memories):
        pass

    assert hasattr(my_hook, '_lifecycle_hook'), "钩子函数应具有 _lifecycle_hook 属性"
    hook = my_hook._lifecycle_hook
    assert hook.method_name == 'on_agent_start', "方法名应正确"
    assert hook.wrapper_func is my_hook, "包装函数应正确"
    return True


@test_case("钩子函数能正确附加元数据", "核心装饰器功能")
def test_hook_metadata():
    @lifecycle_hook('on_generate_delta', modifies_return=False, position='after')
    async def my_hook(self, delta: str):
        pass

    hook = my_hook._lifecycle_hook
    assert hook.method_name == 'on_generate_delta'
    assert hook.modifies_return is False
    assert hook.position == HookPosition.AFTER
    return True


@test_case("agent_decorator 能正确将钩子应用到类方法", "核心装饰器功能")
def test_agent_decorator_applies_hooks():
    execution_order = []

    @lifecycle_hook('on_agent_start')
    async def hook1(self, memories):
        execution_order.append('hook1')

    @agent_decorator(hook1)
    class TestAgent(AgentBase):
        async def on_agent_start(self, memories):
            execution_order.append('original')

    # 检查方法已被组合
    assert hasattr(TestAgent, 'on_agent_start')
    return True


@test_case("多个钩子按书写顺序执行（after hooks）", "核心装饰器功能")
def test_multiple_hooks_execution_order():
    execution_order = []

    @lifecycle_hook('on_agent_start', position='after')
    async def hook1(self, memories):
        execution_order.append('hook1')

    @lifecycle_hook('on_agent_start', position='after')
    async def hook2(self, memories):
        execution_order.append('hook2')

    @agent_decorator(hook1, hook2)
    class TestAgent(AgentBase):
        async def on_agent_start(self, memories):
            execution_order.append('original')

    async def run_test():
        agent = create_test_agent(TestAgent)
        await agent.on_agent_start([])
        assert execution_order == ['original', 'hook1', 'hook2'], \
            f"执行顺序应为 [original, hook1, hook2]，实际为 {execution_order}"

    asyncio.run(run_test())
    return True


@test_case("before hooks 在原方法之前执行", "核心装饰器功能")
def test_before_hook_execution():
    execution_order = []

    @lifecycle_hook('on_agent_start', position='before')
    async def hook1(self, memories):
        execution_order.append('before_hook')

    @agent_decorator(hook1)
    class TestAgent(AgentBase):
        async def on_agent_start(self, memories):
            execution_order.append('original')

    async def run_test():
        agent = create_test_agent(TestAgent)
        await agent.on_agent_start([])
        assert execution_order == ['before_hook', 'original'], \
            f"执行顺序应为 [before_hook, original]，实际为 {execution_order}"

    asyncio.run(run_test())
    return True


@test_case("before 和 after hooks 混合执行", "核心装饰器功能")
def test_before_after_hooks_mixed():
    execution_order = []

    @lifecycle_hook('on_agent_start', position='before')
    async def before_hook(self, memories):
        execution_order.append('before')

    @lifecycle_hook('on_agent_start', position='after')
    async def after_hook(self, memories):
        execution_order.append('after')

    @agent_decorator(before_hook, after_hook)
    class TestAgent(AgentBase):
        async def on_agent_start(self, memories):
            execution_order.append('original')

    async def run_test():
        agent = create_test_agent(TestAgent)
        await agent.on_agent_start([])
        assert execution_order == ['before', 'original', 'after'], \
            f"执行顺序应为 [before, original, after]，实际为 {execution_order}"

    asyncio.run(run_test())
    return True


# ============ 2. 签名验证功能测试 ============

@test_case("验证参数个数是否匹配", "签名验证功能")
def test_signature_validation_param_count():
    try:
        @lifecycle_hook('on_agent_start')
        async def wrong_hook(self, memories, extra_param):  # 参数过多
            pass
        assert False, "应该抛出 SignatureMismatchError"
    except SignatureMismatchError as e:
        assert "parameters" in str(e).lower()
        return True


@test_case("验证异步/同步是否一致", "签名验证功能")
def test_signature_validation_async_sync():
    try:
        @lifecycle_hook('on_agent_start')  # on_agent_start 是异步的
        def wrong_hook(self, memories):  # 同步函数
            pass
        assert False, "应该抛出 SignatureMismatchError"
    except SignatureMismatchError as e:
        assert "async" in str(e).lower() or "sync" in str(e).lower()
        return True


@test_case("modifies_return=True 时验证额外参数", "签名验证功能")
def test_signature_validation_modifies_return():
    # on_create_assistant_memory 返回值
    @lifecycle_hook('on_create_assistant_memory', modifies_return=True)
    async def modify_return_hook(self, return_value, content, reasoning_content, tool_calls=None):
        return return_value

    # 检查钩子已创建
    assert hasattr(modify_return_hook, '_lifecycle_hook')
    return True


@test_case("提供清晰的错误信息", "签名验证功能")
def test_signature_validation_error_message():
    try:
        @lifecycle_hook('unknown_method')
        async def hook(self):
            pass
        assert False, "应该抛出异常"
    except ValueError as e:
        assert "unknown" in str(e).lower() or "lifecycle method" in str(e).lower()
        return True


# ============ 3. 方法组合功能测试 ============

@test_case("异步方法正确组合（不修改返回值）", "方法组合功能")
def test_async_compose_no_return():
    execution_log = []

    @lifecycle_hook('on_generate_delta', position='after')
    async def log_hook(self, delta: str):
        execution_log.append(f'hook: {delta}')

    @agent_decorator(log_hook)
    class TestAgent(AgentBase):
        async def on_generate_delta(self, delta: str):
            execution_log.append(f'original: {delta}')

    async def run_test():
        agent = create_test_agent(TestAgent)
        await agent.on_generate_delta('test_delta')
        assert execution_log == ['original: test_delta', 'hook: test_delta'], \
            f"执行日志: {execution_log}"

    asyncio.run(run_test())
    return True


@test_case("异步方法正确组合（修改返回值）", "方法组合功能")
def test_async_compose_with_return():
    @lifecycle_hook('on_create_assistant_memory', modifies_return=True)
    async def modify_memory_hook(self, return_value, content, reasoning_content, tool_calls=None):
        # 修改返回值
        modified = dict(return_value)
        modified['content'] = f"[MODIFIED] {modified['content']}"
        return modified

    @agent_decorator(modify_memory_hook)
    class TestAgent(AgentBase):
        async def on_create_assistant_memory(self, content, reasoning_content, tool_calls=None):
            return {'role': 'assistant', 'content': content}

    async def run_test():
        agent = create_test_agent(TestAgent)
        result = await agent.on_create_assistant_memory('test content', 'reasoning')
        assert result['content'] == '[MODIFIED] test content', \
            f"返回值应被修改，实际: {result['content']}"

    asyncio.run(run_test())
    return True


@test_case("同步方法正确组合（不修改返回值）", "方法组合功能")
def test_sync_compose_no_return():
    execution_log = []

    @lifecycle_hook('loop_flag_init', position='after')
    def log_hook(self):
        execution_log.append('hook_executed')

    @agent_decorator(log_hook)
    class TestAgent(AgentBase):
        def loop_flag_init(self):
            execution_log.append('original_executed')
            return None

    agent = create_test_agent(TestAgent)
    result = agent.loop_flag_init()
    assert execution_log == ['original_executed', 'hook_executed']
    return True


@test_case("同步方法正确组合（修改返回值）", "方法组合功能")
def test_sync_compose_with_return():
    @lifecycle_hook('loop_flag_should_continue', modifies_return=True)
    def modify_return_hook(self, return_value, current_value):
        return not return_value  # 反转返回值

    @agent_decorator(modify_return_hook)
    class TestAgent(AgentBase):
        def loop_flag_should_continue(self, current_value):
            return True

    agent = create_test_agent(TestAgent)
    result = agent.loop_flag_should_continue(None)
    assert result is False, "返回值应被反转"
    return True


@test_case("钩子函数和原方法都正确执行", "方法组合功能")
def test_both_hooks_and_original_execute():
    execution_log = []

    @lifecycle_hook('on_agent_start', position='before')
    async def before_hook(self, memories):
        execution_log.append('before')

    @lifecycle_hook('on_agent_start', position='after')
    async def after_hook(self, memories):
        execution_log.append('after')

    @agent_decorator(before_hook, after_hook)
    class TestAgent(AgentBase):
        async def on_agent_start(self, memories):
            execution_log.append('original')

    async def run_test():
        agent = create_test_agent(TestAgent)
        await agent.on_agent_start([])
        assert 'before' in execution_log
        assert 'original' in execution_log
        assert 'after' in execution_log
        assert len(execution_log) == 3

    asyncio.run(run_test())
    return True


@test_case("返回值正确传递", "方法组合功能")
def test_return_value_correctly_passed():
    @lifecycle_hook('prepare_kwargs', modifies_return=True)
    async def add_extra_param(self, return_value, thinking=True):
        return_value['extra_param'] = 'added'
        return return_value

    @agent_decorator(add_extra_param)
    class TestAgent(AgentBase):
        async def prepare_kwargs(self, thinking=True):
            return {'base_param': 'value'}

    async def run_test():
        agent = create_test_agent(TestAgent)
        result = await agent.prepare_kwargs()
        assert result == {'base_param': 'value', 'extra_param': 'added'}, \
            f"返回值: {result}"

    asyncio.run(run_test())
    return True


# ============ 4. 生命周期方法支持测试 ============

# 测试所有 15 个异步生命周期方法
async_methods = [
    'on_agent_start',
    'on_iteration_start',
    'on_iteration_end',
    'on_generate_start',
    'on_generate_delta',
    'on_generate_complete',
    'on_tool_calls_start_batch',
    'on_tool_calls_complete_batch',
    'on_tool_call_start',
    'on_tool_call_complete',
    'on_tool_call_error',
    'on_agent_complete',
    'on_agent_cancel',
    'on_create_assistant_memory',
    'prepare_kwargs',
    'prepare_tools',
]

sync_methods = [
    'loop_flag_init',
    'loop_flag_unset_on_iter_start',
    'loop_flag_set_on_tool_calls',
    'loop_flag_should_continue',
]


@test_case("所有 15 个异步生命周期方法都能被装饰", "生命周期方法支持")
def test_all_async_methods_decoratable():
    success_count = 0

    for method_name in async_methods:
        try:
            # 获取方法签名以确定钩子参数
            sig = inspect.signature(getattr(AgentBase, method_name))
            params = [p for p in sig.parameters.values() if p.name != 'self']
            param_str = ', '.join([f'{p.name}' for p in params])

            # 创建钩子
            hook_code = f"""
@lifecycle_hook('{method_name}')
async def test_hook(self, {param_str}):
    pass
"""
            exec(hook_code, {'lifecycle_hook': lifecycle_hook})
            success_count += 1
        except Exception as e:
            print(f"    警告: {method_name} 装饰失败: {e}")

    assert success_count == len(async_methods), \
        f"成功装饰 {success_count}/{len(async_methods)} 个异步方法"
    return True


@test_case("所有 4 个同步生命周期方法都能被装饰", "生命周期方法支持")
def test_all_sync_methods_decoratable():
    success_count = 0

    for method_name in sync_methods:
        try:
            sig = inspect.signature(getattr(AgentBase, method_name))
            params = [p for p in sig.parameters.values() if p.name != 'self']
            param_str = ', '.join([f'{p.name}' for p in params])

            hook_code = f"""
@lifecycle_hook('{method_name}')
def test_hook(self, {param_str}):
    pass
"""
            exec(hook_code, {'lifecycle_hook': lifecycle_hook})
            success_count += 1
        except Exception as e:
            print(f"    警告: {method_name} 装饰失败: {e}")

    assert success_count == len(sync_methods), \
        f"成功装饰 {success_count}/{len(sync_methods)} 个同步方法"
    return True


@test_case("有返回值的方法正确处理（prepare_kwargs）", "生命周期方法支持")
def test_return_method_prepare_kwargs():
    @lifecycle_hook('prepare_kwargs', modifies_return=True)
    async def modify_kwargs(self, return_value, thinking=True):
        return_value['modified'] = True
        return return_value

    @agent_decorator(modify_kwargs)
    class TestAgent(AgentBase):
        async def prepare_kwargs(self, thinking=True):
            return {'thinking': thinking}

    async def run_test():
        agent = create_test_agent(TestAgent)
        result = await agent.prepare_kwargs(thinking=False)
        assert result == {'thinking': False, 'modified': True}

    asyncio.run(run_test())
    return True


@test_case("有返回值的方法正确处理（prepare_tools）", "生命周期方法支持")
def test_return_method_prepare_tools():
    @lifecycle_hook('prepare_tools', modifies_return=True)
    async def modify_tools(self, return_value, memories):
        tools, closures = return_value
        # 添加一个虚拟工具
        tools.append({'type': 'function', 'function': {'name': 'extra_tool'}})
        return (tools, closures)

    @agent_decorator(modify_tools)
    class TestAgent(AgentBase):
        async def prepare_tools(self, memories):
            return ([], {})

    async def run_test():
        agent = create_test_agent(TestAgent)
        tools, closures = await agent.prepare_tools([])
        assert len(tools) == 1
        assert tools[0]['function']['name'] == 'extra_tool'

    asyncio.run(run_test())
    return True


@test_case("有返回值的方法正确处理（on_create_assistant_memory）", "生命周期方法支持")
def test_return_method_on_create_assistant_memory():
    @lifecycle_hook('on_create_assistant_memory', modifies_return=True)
    async def modify_memory(self, return_value, content, reasoning_content, tool_calls=None):
        modified = dict(return_value)
        modified['custom_field'] = 'custom_value'
        return modified

    @agent_decorator(modify_memory)
    class TestAgent(AgentBase):
        async def on_create_assistant_memory(self, content, reasoning_content, tool_calls=None):
            return {'role': 'assistant', 'content': content}

    async def run_test():
        agent = create_test_agent(TestAgent)
        result = await agent.on_create_assistant_memory('test', 'reasoning')
        assert result['custom_field'] == 'custom_value'

    asyncio.run(run_test())
    return True


@test_case("有返回值的方法正确处理（loop_flag_*）", "生命周期方法支持")
def test_return_method_loop_flags():
    @lifecycle_hook('loop_flag_should_continue', modifies_return=True)
    def modify_flag(self, return_value, current_value):
        # 可以根据 current_value 修改返回值
        return True if current_value is None else return_value

    @agent_decorator(modify_flag)
    class TestAgent(AgentBase):
        def loop_flag_should_continue(self, current_value):
            return False

    agent = create_test_agent(TestAgent)
    # None 时应返回 True
    assert agent.loop_flag_should_continue(None) is True
    # 其他值时应保持原返回值
    assert agent.loop_flag_should_continue('some_value') is False
    return True


# ============ 运行所有测试 ============

def run_all_tests():
    """运行所有测试用例"""
    print("=" * 80)
    print("AgentBase 生命周期装饰器系统 - 功能完整性验证测试")
    print("=" * 80)
    print()

    # 获取所有测试函数
    test_functions = [
        # 核心装饰器功能
        test_lifecycle_hook_creates_hook,
        test_hook_metadata,
        test_agent_decorator_applies_hooks,
        test_multiple_hooks_execution_order,
        test_before_hook_execution,
        test_before_after_hooks_mixed,

        # 签名验证功能
        test_signature_validation_param_count,
        test_signature_validation_async_sync,
        test_signature_validation_modifies_return,
        test_signature_validation_error_message,

        # 方法组合功能
        test_async_compose_no_return,
        test_async_compose_with_return,
        test_sync_compose_no_return,
        test_sync_compose_with_return,
        test_both_hooks_and_original_execute,
        test_return_value_correctly_passed,

        # 生命周期方法支持
        test_all_async_methods_decoratable,
        test_all_sync_methods_decoratable,
        test_return_method_prepare_kwargs,
        test_return_method_prepare_tools,
        test_return_method_on_create_assistant_memory,
        test_return_method_loop_flags,
    ]

    print("运行测试...\n")

    for test_func in test_functions:
        test_func()

    # 打印结果汇总
    print()
    print("=" * 80)
    print("测试结果汇总")
    print("=" * 80)

    by_category = {}
    for result in test_results:
        category = result['category']
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(result)

    for category, results in by_category.items():
        print(f"\n【{category}】")
        passed = sum(1 for r in results if r['status'] == 'PASS')
        total = len(results)
        print(f"  通过: {passed}/{total}")

        for result in results:
            status_icon = "✓" if result['status'] == 'PASS' else "✗"
            print(f"    {status_icon} {result['name']}")
            if result['status'] != 'PASS':
                print(f"       错误: {result['message']}")

    print()
    total_passed = sum(1 for r in test_results if r['status'] == 'PASS')
    total_tests = len(test_results)
    print(f"总计通过: {total_passed}/{total_tests}")
    print("=" * 80)

    return total_passed == total_tests


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
