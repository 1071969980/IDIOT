import inspect
import os
import sys
from functools import wraps
from typing import Callable

import logfire
from constant import JAEGER_LOG_API, LOG_DIR
from loguru import logger


def init_logger():
    # file log
    logger.add(str(LOG_DIR / "app.log"), rotation="100 MB", level="DEBUG")
    # stderr log
    logger.add(sink=sys.stderr, level="WARNING")
    logger.info("Logger initialized")

    if JAEGER_LOG_API:
        os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = JAEGER_LOG_API
        logfire.configure(
            # Setting a service name is good practice in general, but especially
            # important for Jaeger, otherwise spans will be labeled as 'unknown_service'
            service_name="test_service",

            # Sending to Logfire is on by default regardless of the OTEL env vars.
            # Keep this line here if you don't want to send to both Jaeger and Logfire.
            send_to_logfire=False,
        )

def log_span(message: str, 
             args_captured_as_tags:list[str] | None = None,
             only_tags_kwargs:list[str] | None = None) -> Callable:
    """创建用于分布式跟踪的日志跨度装饰器

    该装饰器工厂函数会为被装饰的函数创建一个 logfire 跟踪 span，并支持将指定参数作为标签附加到 span 中。

    Args:
        message (str): 跨度(span)的描述信息，将作为 span 名称显示。
        args_captured_as_tags (list[str], optional): 需要捕获并作为 span 标签的函数参数名列表。
            默认为空列表，表示不捕获任何参数。
        only_tags_kwargs: (list[str], optional): 需要作为 span 标签的函数参数名列表,。
            这个列表中的参数不会被传递到被装饰的函数中。

    Returns:
        function: 装饰器函数，可应用于同步或异步函数：
            - 对于异步函数：返回 `wrapper_async`
            - 对于同步函数：返回 `wrapper`

    Example:
        >>> @log_span("处理用户请求", args_captured_as_tags=['user_id'], only_tags_kwargs=['!uuid'])
        >>> def handle_request(user_id: int):
        >>>     # 函数执行时会产生名为"处理用户请求"的 span
        >>>     # 并附带标签 {'user_id': 实际参数值}
        >>>
        >>> handle_request(user_id=123,
        >>>     **{"!uuid": "fd0bc3b2-934a-41e4-b623-afa3435a4cc3"})
    """
    if args_captured_as_tags is None:
        args_captured_as_tags = []
    if only_tags_kwargs is None:
        only_tags_kwargs = []
    for only_tag_kw_name in only_tags_kwargs:
        if not only_tag_kw_name.startswith("!"):
            msg = f'{only_tag_kw_name} in only_tags_kwargs should start with "!", and should be pass as "func(..., **{{"!kwargs": value}})" when calling the function'
            raise ValueError(msg)
        
    frame = inspect.currentframe()
    caller_frame = frame.f_back
    decorator_filename = caller_frame.f_code.co_filename
    decorator_lineno = caller_frame.f_lineno
    def decorator(func):
        decorated_func_name = func.__name__
        decorator_detail_tag = {
            "decorator_detail.decorator_filename": decorator_filename,
            "decorator_detail.decorator_lineno": decorator_lineno,
            "decorator_detail.decorated_func_name": decorated_func_name,
        }

        def filter_kwargs(kwargs: dict):
            tags = {}
            if not only_tags_kwargs:
                return tags
            for kwarg in only_tags_kwargs:
                if kwarg in kwargs:
                    tags[kwarg] = str(kwargs[kwarg])
                    kwargs.pop(kwarg)
            return tags
        def capture_tags(func, args, kwargs):
            if not args_captured_as_tags:
                return {}
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()  # 应用默认值（如果有）
            params_dict = dict(bound.arguments)
            return {key: str(params_dict[key]) for key in args_captured_as_tags if key in params_dict}
        @wraps(func)
        async def wrapper_async(*args, **kwargs):
            # 捕获被声明在tag_key中的参数
            only_tags = filter_kwargs(kwargs)
            tags = capture_tags(func, args, kwargs)
            with logfire.span(message, **tags, **only_tags, **decorator_detail_tag) :
                return await func(*args, **kwargs)
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 捕获被声明在tag_key中的参数
            only_tags = filter_kwargs(kwargs)
            tags = capture_tags(func, args, kwargs)
            with logfire.span(message, **tags, **only_tags, **decorator_detail_tag) :
                return func(*args, **kwargs)

        if inspect.iscoroutinefunction(func):
            return wrapper_async
        else:
            return wrapper
    return decorator