"""
constructor.py 集成代码示例

在 UpdateConversationStrategiesOfRole 工具的 __call__ 方法中，
写入缓存成功后，立即发起后台更新任务。
"""

async def __call__(self, **kwargs):
    """更新角色对话策略工具的主入口"""
    # 1. 参数验证
    param = UpdateConversationStrategiesOfRoleParam(**kwargs)

    # 2. 读取现有缓存
    async with user_agent_role_strategies_update_cache_file(self.user_id, param.role_name, "r") as f:
        cache_content = f.read().decode("utf-8")
        update_cache = ujson.loads(cache_content) if cache_content else {}

    # 3. 添加新更新请求到缓存
    if "strategies_update_cache" not in update_cache:
        update_cache["strategies_update_cache"] = []
    update_cache["strategies_update_cache"].append({
        "update_content": param.update_content,
        "context": param.context
    })

    # 4. 写入缓存文件
    async with user_agent_role_strategies_update_cache_file(self.user_id, param.role_name, "r+") as f:
        f.write(ujson.dumps(update_cache).encode("utf-8"))

    # 5. 【关键位置】写入缓存成功后，立即发起后台更新任务
    from api.agent.tools.agent_roles.update_role_conversation_strategies.background_update.task_runner import run_background_update_task

    task = asyncio.create_task(
        run_background_update_task(
            user_id=self.user_id,
            role_name=param.role_name
        )
    )

    # 6. 返回成功消息（不等待任务完成）
    return ToolTaskResult(
        str_content="更新任务已提交，后台将自动处理。"
    )
