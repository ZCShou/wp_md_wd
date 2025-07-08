import inspect

def printf(*args, **kwargs):
    """根据实际函数调用层级自动缩进的打印函数"""
    # 获取当前栈帧
    current_frame = inspect.currentframe()
    try:
        # 获取调用者的栈帧
        caller_frame = current_frame.f_back
        # 计算实际函数调用层级（排除iprint自身和上下文管理器等非函数调用）
        level = 0
        while caller_frame:
            if caller_frame.f_code.co_name != '<module>':
                level += 1
            caller_frame = caller_frame.f_back
        # 生成缩进字符串
        indent = ' ' * (level * 4)
        # 打印带有缩进的内容
        print(indent, *args, **kwargs)
    finally:
        # 避免内存泄漏
        del current_frame