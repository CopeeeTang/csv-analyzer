"""代码执行器"""

import sys
import io
import traceback
import signal
import logging
from typing import Dict, Any, Set
from contextlib import redirect_stdout, redirect_stderr


class TimeoutError(Exception):
    """执行超时异常"""
    pass


class CodeExecutor:
    """安全的Python代码执行器"""

    # 允许的模块白名单
    ALLOWED_MODULES: Set[str] = {
        'pandas', 'pd',
        'numpy', 'np',
        'matplotlib', 'plt',
        'seaborn', 'sns',
        'datetime', 'date', 'time',
        'math', 'statistics',
        'collections', 'itertools',
        're', 'json'
    }

    # 危险的内置函数黑名单
    FORBIDDEN_BUILTINS: Set[str] = {
        'eval', 'exec', 'compile',
        '__import__', 'open',
        'input', 'raw_input'
    }

    def __init__(
        self,
        timeout: int = 30,
        allowed_modules: list = None
    ):
        """
        初始化代码执行器

        Args:
            timeout: 执行超时时间（秒）
            allowed_modules: 额外允许的模块列表
        """
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)

        # 扩展允许的模块
        if allowed_modules:
            self.ALLOWED_MODULES.update(allowed_modules)

        # 初始化全局变量环境
        self.globals_dict: Dict[str, Any] = {}
        self._init_globals()

    def _init_globals(self):
        """初始化全局变量环境"""
        import pandas as pd
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')  # 使用非交互式后端
        import matplotlib.pyplot as plt
        import seaborn as sns

        # 配置matplotlib
        plt.ioff()  # 关闭交互模式

        # 设置安全的内置函数
        safe_builtins = self._create_safe_builtins()

        self.globals_dict = {
            '__builtins__': safe_builtins,
            'pd': pd,
            'np': np,
            'plt': plt,
            'sns': sns,
        }

        self.logger.debug("全局环境初始化完成")

    def _create_safe_builtins(self) -> dict:
        """创建安全的内置函数环境"""
        import builtins

        # 复制内置函数
        safe_builtins = {}
        for name in dir(builtins):
            if not name.startswith('_') and name not in self.FORBIDDEN_BUILTINS:
                safe_builtins[name] = getattr(builtins, name)

        return safe_builtins

    def set_dataframe(self, df):
        """
        设置DataFrame到执行环境

        Args:
            df: pandas DataFrame对象
        """
        self.globals_dict['df'] = df
        self.logger.debug(f"DataFrame已加载: shape={df.shape}")

    def execute(self, code: str) -> Dict[str, Any]:
        """
        执行Python代码

        Args:
            code: 要执行的Python代码

        Returns:
            执行结果字典，包含:
            - success: bool, 是否成功
            - stdout: str, 标准输出
            - stderr: str, 标准错误
            - error_type: str, 错误类型（失败时）
            - error: str, 错误信息（失败时）
            - traceback: str, 错误堆栈（失败时）
        """
        self.logger.info("开始执行代码")

        # 1. 语法检查
        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            self.logger.error(f"语法错误: {str(e)}")
            return {
                'success': False,
                'error_type': 'SyntaxError',
                'error': str(e),
                'traceback': traceback.format_exc()
            }

        # 2. 执行代码
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        try:
            # 重定向输出
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # TODO: 添加超时控制（需要使用signal或multiprocessing）
                exec(code, self.globals_dict)

            stdout_content = stdout_capture.getvalue()
            stderr_content = stderr_capture.getvalue()

            self.logger.info("代码执行成功")
            self.logger.debug(f"输出: {stdout_content[:200]}")

            return {
                'success': True,
                'stdout': stdout_content,
                'stderr': stderr_content,
            }

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            error_trace = traceback.format_exc()

            self.logger.error(f"执行错误 [{error_type}]: {error_msg}")

            return {
                'success': False,
                'error_type': error_type,
                'error': error_msg,
                'traceback': error_trace,
                'stdout': stdout_capture.getvalue(),
                'stderr': stderr_capture.getvalue(),
            }

    def reset(self):
        """重置执行环境"""
        self.logger.info("重置执行环境")
        df_backup = self.globals_dict.get('df')
        self._init_globals()
        if df_backup is not None:
            self.globals_dict['df'] = df_backup

    def get_variable(self, name: str) -> Any:
        """
        获取执行环境中的变量

        Args:
            name: 变量名

        Returns:
            变量值
        """
        return self.globals_dict.get(name)

    def check_plot_generated(self) -> bool:
        """
        检查是否生成了图表

        Returns:
            是否有未保存的图表
        """
        plt = self.globals_dict.get('plt')
        if plt:
            # 检查是否有活动的图形
            return len(plt.get_fignums()) > 0
        return False

    def close_plots(self):
        """关闭所有图表"""
        plt = self.globals_dict.get('plt')
        if plt:
            plt.close('all')
