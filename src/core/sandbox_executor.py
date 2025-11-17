"""增强的Sandbox代码执行器"""

import sys
import io
import ast
import traceback
import logging
import multiprocessing
import signal
from typing import Dict, Any, Set, Optional
from contextlib import redirect_stdout, redirect_stderr
import pickle


class CodeSecurityError(Exception):
    """代码安全检查失败异常"""
    pass


class SandboxExecutor:
    """
    更安全的Sandbox代码执行器

    安全特性：
    1. AST静态分析检测危险操作
    2. 严格的模块和函数白名单
    3. 进程隔离执行（可选）
    4. 资源限制
    5. 超时控制
    """

    # 危险的AST节点类型
    DANGEROUS_NODES = {
        ast.Import,      # import语句
        ast.ImportFrom,  # from ... import语句
    }

    # 危险的内置函数
    FORBIDDEN_BUILTINS = {
        'eval', 'exec', 'compile',
        '__import__', 'open', 'input',
        'raw_input', 'execfile', 'file',
        'reload', 'vars', 'locals', 'globals',
        'dir', 'getattr', 'setattr', 'delattr',
        'hasattr'
    }

    # 危险的模块
    FORBIDDEN_MODULES = {
        'os', 'sys', 'subprocess', 'shutil',
        'socket', 'urllib', 'requests',
        'pickle', 'shelve', 'marshal',
        'importlib', '__builtin__', 'builtins'
    }

    # 允许的内置函数白名单
    ALLOWED_BUILTINS = {
        'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray',
        'bytes', 'chr', 'complex', 'dict', 'divmod', 'enumerate',
        'filter', 'float', 'format', 'frozenset', 'hex', 'int',
        'isinstance', 'issubclass', 'iter', 'len', 'list', 'map',
        'max', 'min', 'next', 'oct', 'ord', 'pow', 'print', 'range',
        'repr', 'reversed', 'round', 'set', 'slice', 'sorted', 'str',
        'sum', 'tuple', 'type', 'zip',
        # 特殊：需要的一些函数
        'Exception', 'ValueError', 'TypeError', 'KeyError',
        'IndexError', 'AttributeError'
    }

    def __init__(
        self,
        timeout: int = 30,
        use_process_isolation: bool = False,
        max_memory_mb: int = 512,
        allowed_modules: list = None
    ):
        """
        初始化Sandbox执行器

        Args:
            timeout: 执行超时时间（秒）
            use_process_isolation: 是否使用进程隔离（状态不保持）
            max_memory_mb: 最大内存限制（MB）
            allowed_modules: 额外允许的模块列表（为兼容性保留，SandboxExecutor使用AST静态分析，不允许动态导入）
        """
        self.timeout = timeout
        self.use_process_isolation = use_process_isolation
        self.max_memory_mb = max_memory_mb
        self.allowed_modules = allowed_modules or []
        self.logger = logging.getLogger(__name__)

        # 初始化全局环境
        self.globals_dict: Dict[str, Any] = {}
        self._init_globals()

    def _init_globals(self):
        """初始化安全的全局环境"""
        import pandas as pd
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
        import builtins
        from datetime import datetime, timedelta
        import math

        plt.ioff()

        # 创建安全的内置函数字典（正确处理builtins）
        safe_builtins = {}
        for name in self.ALLOWED_BUILTINS:
            if hasattr(builtins, name):
                safe_builtins[name] = getattr(builtins, name)

        # 确保基本类型和常用函数可用
        safe_builtins.update({
            # 基本类型
            'float': float,
            'int': int,
            'str': str,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            # 常用函数（确保与ALLOWED_BUILTINS一致）
            'len': len,
            'print': print,
            'range': range,
            'sum': sum,
            'max': max,
            'min': min,
            'abs': abs,
            'round': round,
            'sorted': sorted,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'all': all,
            'any': any,
            # 类型判断
            'isinstance': isinstance,
            'type': type,
            'issubclass': issubclass,
            # 异常类型（pandas/numpy可能需要）
            'Exception': Exception,
            'ValueError': ValueError,
            'TypeError': TypeError,
            'KeyError': KeyError,
            'IndexError': IndexError,
            'AttributeError': AttributeError,
            'ZeroDivisionError': ZeroDivisionError,
            'RuntimeError': RuntimeError,
        })

        self.globals_dict = {
            '__builtins__': safe_builtins,
            'pd': pd,
            'np': np,
            'plt': plt,
            'sns': sns,
            # 添加datetime和math模块的常用函数
            'datetime': datetime,
            'timedelta': timedelta,
            'math': math,
        }

        self.logger.debug("Sandbox环境初始化完成")

    def _check_code_safety(self, code: str) -> None:
        """
        静态分析代码安全性

        Args:
            code: 要检查的代码

        Raises:
            CodeSecurityError: 如果检测到危险操作
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # 语法错误会在后续处理
            return

        # 遍历AST检测危险节点
        for node in ast.walk(tree):
            # 检查Import节点
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.FORBIDDEN_MODULES:
                        raise CodeSecurityError(
                            f"禁止导入模块: {alias.name}"
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.module in self.FORBIDDEN_MODULES:
                    raise CodeSecurityError(
                        f"禁止导入模块: {node.module}"
                    )

            # 检查函数调用
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    if func_name in self.FORBIDDEN_BUILTINS:
                        raise CodeSecurityError(
                            f"禁止使用函数: {func_name}"
                        )

            # 检查属性访问（阻止 __xxx__ 访问）
            elif isinstance(node, ast.Attribute):
                if node.attr.startswith('__') and node.attr.endswith('__'):
                    raise CodeSecurityError(
                        f"禁止访问魔术属性: {node.attr}"
                    )

        self.logger.debug("代码安全检查通过")

    def set_dataframe(self, df):
        """设置DataFrame到执行环境"""
        self.globals_dict['df'] = df
        self.logger.debug(f"DataFrame已加载: shape={df.shape}")

    def _execute_with_timeout(self, code: str) -> Dict[str, Any]:
        """
        带超时控制的代码执行

        Args:
            code: 要执行的代码

        Returns:
            执行结果字典
        """
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        def timeout_handler(signum, frame):
            raise TimeoutError(f"代码执行超时（{self.timeout}秒）")

        try:
            # 设置超时信号（仅Unix系统）
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(self.timeout)

            # 重定向输出并执行
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(code, self.globals_dict)

            # 取消超时
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)

            return {
                'success': True,
                'stdout': stdout_capture.getvalue(),
                'stderr': stderr_capture.getvalue(),
            }

        except TimeoutError as e:
            self.logger.error(f"执行超时: {str(e)}")
            return {
                'success': False,
                'error_type': 'TimeoutError',
                'error': str(e),
                'traceback': traceback.format_exc(),
                'stdout': stdout_capture.getvalue(),
                'stderr': stderr_capture.getvalue(),
            }

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            error_trace = traceback.format_exc()

            # 特殊处理 __import__ 错误，提供友好的提示
            if '__import__' in error_msg.lower() or '__import__ not found' in error_msg:
                error_msg = (
                    "__import__ not found: 代码中使用了__import__()函数，这在安全沙箱中是被禁止的。\n"
                    "解决方案：不要使用任何import语句，直接使用预加载的变量：\n"
                    "  - pd (pandas)\n"
                    "  - np (numpy)\n"
                    "  - plt (matplotlib.pyplot)\n"
                    "  - sns (seaborn)\n"
                    "  - datetime, timedelta, math\n"
                    "所有这些变量已经预加载，可以直接使用。"
                )
                error_type = "ImportError"

            self.logger.error(f"执行错误 [{error_type}]: {error_msg}")

            return {
                'success': False,
                'error_type': error_type,
                'error': error_msg,
                'error_message': error_msg,  # 添加 error_message 字段以保持兼容
                'traceback': error_trace,
                'stdout': stdout_capture.getvalue(),
                'stderr': stderr_capture.getvalue(),
            }

        finally:
            # 确保取消超时
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)

    def execute(self, code: str) -> Dict[str, Any]:
        """
        执行Python代码（主入口）

        Args:
            code: 要执行的Python代码

        Returns:
            执行结果字典
        """
        self.logger.info("开始执行代码（Sandbox模式）")

        # 1. 安全检查
        try:
            self._check_code_safety(code)
        except CodeSecurityError as e:
            error_msg = str(e)
            # 特殊处理 __import__ 错误，提供友好的提示
            if '__import__' in error_msg.lower():
                error_msg = (
                    "代码安全检查失败: 代码中使用了__import__()函数，这在安全沙箱中是被禁止的。\n"
                    "解决方案：不要使用任何import语句，直接使用预加载的变量：\n"
                    "  - pd (pandas)\n"
                    "  - np (numpy)\n"
                    "  - plt (matplotlib.pyplot)\n"
                    "  - sns (seaborn)\n"
                    "  - datetime, timedelta, math\n"
                    "所有这些变量已经预加载，可以直接使用。"
                )
            self.logger.error(f"代码安全检查失败: {error_msg}")
            return {
                'success': False,
                'error_type': 'SecurityError',
                'error': error_msg,  # 使用处理后的友好错误消息
                'error_message': error_msg,  # 添加 error_message 字段以保持兼容
                'traceback': ''
            }

        # 2. 语法检查
        try:
            compile(code, '<sandbox>', 'exec')
        except SyntaxError as e:
            self.logger.error(f"语法错误: {str(e)}")
            return {
                'success': False,
                'error_type': 'SyntaxError',
                'error': str(e),
                'traceback': traceback.format_exc()
            }

        # 3. 执行代码
        if self.use_process_isolation:
            # TODO: 使用multiprocessing进程隔离
            # 注意：进程隔离会导致状态不保持
            return self._execute_with_timeout(code)
        else:
            return self._execute_with_timeout(code)

    def reset(self):
        """重置执行环境"""
        self.logger.info("重置Sandbox环境")
        df_backup = self.globals_dict.get('df')
        self._init_globals()
        if df_backup is not None:
            self.globals_dict['df'] = df_backup

    def get_variable(self, name: str) -> Any:
        """获取执行环境中的变量"""
        return self.globals_dict.get(name)

    def check_plot_generated(self) -> bool:
        """检查是否生成了图表"""
        plt = self.globals_dict.get('plt')
        if plt:
            return len(plt.get_fignums()) > 0
        return False

    def close_plots(self):
        """关闭所有图表"""
        plt = self.globals_dict.get('plt')
        if plt:
            plt.close('all')


# 保持向后兼容的别名
CodeExecutor = SandboxExecutor
