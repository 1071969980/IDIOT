import coredumpy
import threading
import sys
import logfire
from io import BytesIO

from api.s3_FS import upload_object, DEFAULT_BUCKET
from .time import now_iso

def save_exception_stack_async(exception: Exception, file_name: str) -> None:
    """
    异步保存异常堆栈到对象存储

    Args:
        exception: Exception对象
        file_name: 可选的文件名，如果不提供则使用当前时间
    """
    def _save_worker() -> None:
        try:
            # 获取异常的traceback对象
            _, _, exc_tb = sys.exc_info()

            # 如果没有当前异常信息（直接传入Exception对象），
            # 则从exception.__traceback__获取
            if exc_tb is None and exception.__traceback__ is not None:
                exc_tb = exception.__traceback__

            if exc_tb is None:
                return

            # 获取异常发生的帧
            frame = exc_tb.tb_frame

            # 使用coredumpy获取堆栈信息
            try:
                frames_as_str = coredumpy.dumps(frame)
            except Exception:
                return

            object_name = f"exception_dump/{file_name}.json"

            # 将coredumpy结果直接保存到S3
            dump_data = str(frames_as_str).encode("utf-8")
            dump_bytes = BytesIO(dump_data)

            upload_object(dump_bytes, DEFAULT_BUCKET, object_name)

            logfire.info(f"Exception dumped to S3 bucket {DEFAULT_BUCKET}",
                         object_name=object_name)

        except Exception:
            # 确保函数本身不抛出异常
            pass

    # 在单独的线程中执行
    thread = threading.Thread(target=_save_worker, daemon=True)
    thread.start()