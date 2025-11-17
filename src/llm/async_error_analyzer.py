"""异步错误分析器

使用thinking模式进行深度错误分析和代码修复
"""

import logging
import threading
from typing import Dict, Optional, List, Callable
from zhipuai import ZhipuAI

from .thinking_parser import ThinkingParser
from .prompts import PromptManager
from ..core import get_global_context


class AsyncErrorAnalyzer:
    """
    异步错误分析器

    使用GLM-4.6的thinking模式进行深度错误分析
    不使用Function Calling，以避免参数冲突
    """

    def __init__(
        self,
        client: ZhipuAI,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ):
        """
        初始化异步错误分析器

        Args:
            client: ZhipuAI客户端实例
            model: 模型名称（需要支持thinking模式）
            temperature: 温度参数（错误分析时适当提高）
            max_tokens: 最大token数
        """
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.logger = logging.getLogger(__name__)
        self.thinking_parser = ThinkingParser()
        self.prompt_manager = PromptManager()

    def analyze_error_async(
        self,
        question: str,
        df_info: Dict,
        history: List[Dict],
        error_feedback: Dict,
        plot_path: Optional[str],
        callback: Callable[[Dict], None]
    ) -> threading.Thread:
        """
        异步启动错误分析

        Args:
            question: 用户问题
            df_info: DataFrame信息
            history: 对话历史
            error_feedback: 错误反馈信息
            plot_path: 图表保存路径
            callback: 分析完成后的回调函数

        Returns:
            分析线程对象
        """
        thread = threading.Thread(
            target=self._analyze_error_thread,
            args=(question, df_info, history, error_feedback, plot_path, callback),
            daemon=True
        )
        thread.start()
        self.logger.info("异步错误分析已启动")
        return thread

    def _analyze_error_thread(
        self,
        question: str,
        df_info: Dict,
        history: List[Dict],
        error_feedback: Dict,
        plot_path: Optional[str],
        callback: Callable[[Dict], None]
    ):
        """
        错误分析线程函数（内部使用）
        """
        try:
            result = self.analyze_error_with_thinking(
                question=question,
                df_info=df_info,
                history=history,
                error_feedback=error_feedback,
                plot_path=plot_path
            )
            callback(result)
        except Exception as e:
            self.logger.error(f"异步错误分析失败: {str(e)}", exc_info=True)
            callback({
                'success': False,
                'error': str(e),
                'code': None
            })

    def analyze_error_with_thinking(
        self,
        question: str,
        df_info: Dict,
        history: List[Dict],
        error_feedback: Dict,
        plot_path: Optional[str]
    ) -> Dict:
        """
        使用thinking模式分析错误并生成修复代码

        Args:
            question: 用户问题
            df_info: DataFrame信息
            history: 对话历史
            error_feedback: 错误反馈
            plot_path: 图表路径

        Returns:
            包含thinking_content、fixed_code、analysis的字典
        """
        self.logger.info("使用thinking模式进行深度错误分析")

        # 构建详细的错误分析prompt（包含对话历史和上下文）
        prompt = self._build_error_analysis_prompt(
            question=question,
            df_info=df_info,
            history=history,
            error_feedback=error_feedback,
            plot_path=plot_path
        )

        # Sandbox环境配置
        sandbox_config = """
【Sandbox执行环境限制】
✓ 已预加载：pd, np, plt, sns, datetime, timedelta, math（直接使用，无需import）
✓ 可用的内置类型：float, int, str, bool, list, dict, tuple, set
✓ 可用的函数：print, len, range, sum, max, min, abs, round, sorted, enumerate, zip, isinstance, type
✗ 禁止：任何import语句、文件操作、os/sys模块
"""

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个专业的代码调试专家，擅长分析Python代码错误。\n"
                    f"{sandbox_config}\n\n"
                    "【错误诊断流程】\n"
                    "第一步：判断错误类型\n"
                    "- **Sandbox环境问题**：使用了禁止的操作（import、未定义的类型/函数、文件操作等）\n"
                    "- **代码逻辑问题**：数据处理错误（KeyError、TypeError、列名错误、数据类型转换等）\n\n"
                    "第二步：分析根本原因\n"
                    "- NameError: 检查是否使用了sandbox中不存在的类型或函数\n"
                    "- KeyError: 检查列名是否正确（注意大小写、空格）\n"
                    "- TypeError: 检查数据类型（如Sales列包含$和,符号需要清洗）\n\n"
                    "第三步：生成修复代码\n"
                    "- 只在```python```代码块中输出纯Python代码\n"
                    "- 代码块外可以写分析说明，但代码块内不要混入任何解释性文字\n"
                    "- 确保代码完整可执行，不使用import语句\n\n"
                    "【输出格式要求】\n"
                    "```python\n"
                    "# 修复后的完整代码（只包含Python代码和注释，不要中文解释）\n"
                    "```\n\n"
                    "代码块外可以写修复说明，但代码块内严格只放代码。"
                )
            },
            {"role": "user", "content": prompt}
        ]

        try:
            # 使用thinking模式（不使用tools参数）
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                thinking={"type": "enabled"},  # 启用深度思考
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            # 解析thinking响应
            parsed = self.thinking_parser.parse_thinking_response(response)

            # 提取修复代码
            fixed_code = self.thinking_parser.extract_code_from_thinking(
                parsed['final_answer']
            )

            # 提取错误分析要点
            error_analysis = self.thinking_parser.extract_error_analysis(
                parsed['thinking_content']
            )

            if not fixed_code:
                self.logger.warning("thinking模式未生成有效代码")
                return {
                    'success': False,
                    'error': 'thinking模式未生成代码',
                    'thinking_content': parsed['thinking_content'],
                    'code': None
                }

            self.logger.info(f"thinking分析成功，代码长度: {len(fixed_code)}")

            return {
                'success': True,
                'code': fixed_code,
                'thinking_content': parsed['thinking_content'],
                'error_analysis': error_analysis,
                'has_thinking': parsed['has_thinking'],
                'source': 'thinking_mode'
            }

        except Exception as e:
            self.logger.error(f"thinking模式调用失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'code': None
            }

    def _build_error_analysis_prompt(
        self,
        question: str,
        df_info: Dict,
        history: List[Dict],
        error_feedback: Dict,
        plot_path: Optional[str]
    ) -> str:
        """
        构建错误分析的详细prompt（包含对话历史和上下文）

        Args:
            question: 用户问题
            df_info: DataFrame信息（备用）
            history: 对话历史
            error_feedback: 错误反馈
            plot_path: 图表路径

        Returns:
            完整的prompt字符串
        """
        parts = []

        # 1. 使用全局上下文（优先）
        global_ctx = get_global_context()
        if global_ctx.is_ready():
            parts.append("# 全局上下文")
            parts.append(global_ctx.get_global_context_prompt())
        else:
            # 回退方案：使用df_info
            parts.append("# DataFrame信息")
            parts.append(f"列名: {', '.join(df_info['columns'])}")
            parts.append(f"形状: {df_info['shape'][0]}行 × {df_info['shape'][1]}列")
            parts.append("\n数据类型:")
            for col, dtype in df_info['dtypes'].items():
                parts.append(f"  - {col}: {dtype}")

        # 2. 对话历史（简化版）
        if history:
            parts.append("\n# 对话历史")
            for i, turn in enumerate(history[-2:], 1):  # 只显示最近2轮
                parts.append(f"\n第{i}轮:")
                parts.append(f"问题: {turn['question']}")
                if turn.get('result', {}).get('success'):
                    parts.append("状态: 成功")
                else:
                    parts.append("状态: 失败")

        # 3. 当前问题
        parts.append(f"\n# 当前问题\n{question}")

        # 4. 失败的代码和错误信息
        parts.append("\n# 执行失败的代码")
        parts.append("```python")
        parts.append(error_feedback['code'])
        parts.append("```")

        parts.append(f"\n# 错误信息")
        parts.append(f"错误类型: {error_feedback['error_type']}")
        parts.append(f"错误描述: {error_feedback['error_message']}")

        if error_feedback.get('traceback'):
            traceback_lines = error_feedback['traceback'].split('\n')
            parts.append("\n关键错误堆栈:")
            parts.append('\n'.join(traceback_lines[-6:]))

        # 5. 任务要求
        parts.append("\n# 任务")
        parts.append("请按照以下步骤分析并修复错误：")
        parts.append("\n**步骤1：错误分类**")
        parts.append("判断这是Sandbox环境问题还是代码逻辑问题？")
        parts.append("- Sandbox环境问题：使用了禁止的import、未定义的类型/函数等")
        parts.append("- 代码逻辑问题：数据处理错误、列名错误、类型转换等")
        parts.append("\n**步骤2：根因分析**")
        parts.append("深入分析错误的根本原因（不只是表面现象）")
        parts.append("\n**步骤3：生成修复代码**")
        parts.append("在```python```代码块中生成修正后的完整代码")
        parts.append("\n要求:")
        parts.append("1. 代码块内严格只放Python代码，不要混入解释性文字")
        parts.append("2. 不使用import语句（pd、np、plt、sns、datetime、timedelta、math已预加载）")
        parts.append("3. 确保所有类型（float、int、str等）都是Python内置的")
        parts.append("4. 如果需要数值计算，先清洗数据类型（如去除$、,、%符号）")

        if plot_path:
            parts.append(f"5. 如需保存图表，使用: plt.savefig('{plot_path}')")

        parts.append("\n代码块外可以写分析说明，但代码块内只放代码。")

        return "\n".join(parts)
