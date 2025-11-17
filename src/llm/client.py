"""智谱AI GLM客户端"""

import json
import logging
from typing import Dict, List, Optional
from zhipuai import ZhipuAI

from .prompts import PromptManager
from .function_schemas import CodeGenerationSchemas
from ..core import get_global_context


class GLMClient:
    """智谱AI GLM-4.6 API客户端"""

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4-plus",
        temperature: float = 0.1,
        max_tokens: int = 2000,
        explanation_max_tokens: int = 4000,
        top_p: float = 0.7,
        use_function_calling: bool = True
    ):
        """
        初始化GLM客户端

        Args:
            api_key: 智谱AI API密钥
            model: 模型名称
            temperature: 温度参数，控制随机性
            max_tokens: 最大生成token数（代码生成）
            explanation_max_tokens: 分析解释的最大token数（默认4000，是代码生成的2倍）
            top_p: 核采样参数
            use_function_calling: 是否使用Function Calling（推荐）
        """
        self.client = ZhipuAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.explanation_max_tokens = explanation_max_tokens
        self.top_p = top_p
        self.use_function_calling = use_function_calling
        self.logger = logging.getLogger(__name__)
        self.prompt_manager = PromptManager()
        self.schemas = CodeGenerationSchemas()

    def _call_api(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None
    ) -> str:
        """
        调用智谱AI API

        Args:
            messages: 消息列表
            temperature: 临时温度参数

        Returns:
            模型响应内容

        Raises:
            Exception: API调用失败
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=self.max_tokens,
                top_p=self.top_p,
            )

            content = response.choices[0].message.content
            self.logger.debug(f"API响应: {content[:200]}...")
            return content

        except Exception as e:
            self.logger.error(f"API调用失败: {str(e)}")
            raise

    def generate_code(
        self,
        question: str,
        df_info: Dict,
        history: List[Dict] = None,
        error_feedback: Optional[Dict] = None,
        plot_path: Optional[str] = None
    ) -> str:
        """
        生成Python代码

        Args:
            question: 用户问题
            df_info: DataFrame信息
            history: 对话历史
            error_feedback: 错误反馈（用于重试）
            plot_path: 图表保存路径

        Returns:
            生成的Python代码
        """
        self.logger.info(f"生成代码: {question}")

        # 如果启用Function Calling，优先使用
        if self.use_function_calling and not error_feedback:
            try:
                code = self._generate_code_with_function_calling(
                    question, df_info, history, plot_path
                )
                self.logger.info("使用Function Calling生成代码成功")
                return code
            except Exception as e:
                self.logger.warning(f"Function Calling失败，回退到Prompt方式: {str(e)}")
                # 回退到传统方式

        # 错误重试时使用特殊的Function Calling schema
        if self.use_function_calling and error_feedback:
            try:
                code = self._generate_fixed_code_with_function_calling(
                    question, df_info, history, error_feedback, plot_path
                )
                self.logger.info("使用Function Calling修复代码成功")
                return code
            except Exception as e:
                self.logger.warning(f"Function Calling修复失败，回退到Prompt方式: {str(e)}")

        # 传统Prompt方式（备用）
        return self._generate_code_with_prompt(
            question, df_info, history, error_feedback, plot_path
        )

    def _generate_code_with_function_calling(
        self,
        question: str,
        df_info: Dict,
        history: List[Dict],
        plot_path: Optional[str]
    ) -> str:
        """
        使用Function Calling生成代码

        Returns:
            生成的Python代码
        """
        # 获取全局上下文
        global_ctx = get_global_context()
        context_parts = []

        # ===全局上下文（始终包含）===
        if global_ctx.is_ready():
            context_parts.append(global_ctx.get_global_context_prompt())
        else:
            # 回退方案：使用传入的df_info
            context_parts.append(f"DataFrame包含{df_info['shape'][0]}行，{df_info['shape'][1]}列")
            context_parts.append(f"列名: {', '.join(df_info['columns'])}")

        # 历史上下文（简化）
        if history:
            last_turn = history[-1]
            context_parts.append(f"\n【上一轮分析】: {last_turn['question']}")

        # 图表路径
        if plot_path:
            context_parts.append(f"\n如需保存图表，使用: plt.savefig('{plot_path}')")

        user_content = f"{chr(10).join(context_parts)}\n\n【用户问题】: {question}"

        # 构建包含sandbox环境配置的system prompt
        sandbox_config = """
【Sandbox执行环境配置】
✓ 已预加载的库（直接使用变量，无需import）：
  - pandas as pd
  - numpy as np
  - matplotlib.pyplot as plt
  - seaborn as sns
  - datetime, timedelta（时间处理）
  - math（数学函数）

✓ 可用的内置类型和函数：
  - 基本类型: int, float, str, bool, list, dict, tuple, set
  - 数学函数: abs, max, min, sum, round, pow, math.sqrt, math.log等
  - 迭代工具: len, range, enumerate, zip, sorted
  - 类型判断: isinstance, type
  - 输出函数: print

✗ 禁止的操作：
  - 任何import语句（包括import、from...import）
  - 文件操作（open、read、write）
  - 系统调用（os、sys、subprocess）
  - 动态执行（eval、exec、compile）
"""

        messages = [
            {
                "role": "system",
                "content": f"你是数据分析专家。使用generate_python_code函数生成代码。\n{sandbox_config}\n重要规则：\n1. 【重要】不要使用任何import语句！直接使用pd、np、plt、sns\n2. 代码必须在上述sandbox环境中可执行\n3. 【数据清洗】在数值计算前必须转换数据类型：\n   - Sales列包含'$'和','，使用: df['Sales'].str.replace('$','').str.replace(',','').str.strip().astype(float)\n   - Rating列包含'%'，使用: df['Rating'].str.replace('%','').str.strip().astype(float)\n4. 确保所有使用的类型（如float、int）都在可用列表中"
            },
            {"role": "user", "content": user_content}
        ]

        # 定义工具
        tools = [self.schemas.get_python_code_schema()]

        # 调用API with Function Calling
        # 根据文档，tool_choice 默认且仅支持 "auto"
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",  # 使用 auto 而不是强制指定函数
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            # 提取函数调用
            message = response.choices[0].message
            if not message.tool_calls:
                raise ValueError("模型未返回函数调用")

            tool_call = message.tool_calls[0]
            func_args = json.loads(tool_call.function.arguments)

            # 提取代码
            code = func_args.get('code', '')

            # 如果有额外的imports，添加到代码开头
            if func_args.get('imports'):
                imports_code = '\n'.join(func_args['imports'])
                code = f"{imports_code}\n\n{code}"

            self.logger.debug(f"Function Calling分析方法: {func_args.get('analysis_approach')}")
            self.logger.debug(f"生成的代码:\n{code}")

            return code

        except Exception as e:
            self.logger.error(f"Function Calling错误: {str(e)}")
            raise

    def _generate_fixed_code_with_function_calling(
        self,
        question: str,
        df_info: Dict,
        history: List[Dict],
        error_feedback: Dict,
        plot_path: Optional[str]
    ) -> str:
        """
        使用Function Calling修复错误代码（带思考链）

        Returns:
            修复后的Python代码
        """
        # 获取全局上下文
        global_ctx = get_global_context()
        context = []

        # ===全局上下文（始终包含）===
        if global_ctx.is_ready():
            context.append(global_ctx.get_global_context_prompt())
        else:
            # 回退方案
            context.append(f"DataFrame包含{df_info['shape'][0]}行，{df_info['shape'][1]}列")
            context.append(f"列名: {', '.join(df_info['columns'])}")

        # 错误分析信息
        context.append(f"\n原始问题: {question}")
        context.append(f"\n失败的代码:\n{error_feedback['code']}")
        context.append(f"\n错误类型: {error_feedback['error_type']}")
        context.append(f"错误信息: {error_feedback['error_message']}")

        if error_feedback.get('traceback'):
            # 只取最后几行traceback，避免太长
            traceback_lines = error_feedback['traceback'].split('\n')
            context.append(f"\n关键错误位置: {chr(10).join(traceback_lines[-5:])}")

        user_content = "\n".join(context)

        # Sandbox环境配置（错误修复时同样需要）
        sandbox_config = """
【Sandbox执行环境】
可用：pd, np, plt, sns, datetime, timedelta, math, float, int, str, bool, list, dict, tuple, set, print, len, range, sum, max, min, abs, round, sorted, enumerate, zip, isinstance, type
禁止：import语句、文件操作、系统调用
"""

        messages = [
            {
                "role": "system",
                "content": f"你是代码调试专家。分析错误原因，生成修正后的代码。使用analyze_and_fix_code_error函数输出分析和修复。\n{sandbox_config}\n重要规则：\n1. 【重要】不要使用任何import语句！直接使用pd、np、plt、sns\n2. 仔细分析错误原因（特别关注NameError说明变量或类型未定义）\n3. 确保使用的所有类型（float、int等）都在可用列表中\n4. 【数据类型错误】如果遇到类型错误，需要清洗数据：\n   - Sales: df['Sales'].str.replace('$','').str.replace(',','').str.strip().astype(float)\n   - Rating: df['Rating'].str.replace('%','').str.strip().astype(float)\n5. 如果错误是'xxx not defined'，检查是否使用了不存在的变量或函数"
            },
            {"role": "user", "content": user_content}
        ]

        # 使用错误分析schema
        tools = [self.schemas.get_error_analysis_schema()]

        # 提高温度以获得不同结果
        temperature = min(self.temperature + 0.2, 0.5)

        # 注意：thinking参数和tools参数不能同时使用
        # Function Calling模式下不使用thinking参数
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=self.max_tokens
            )

            message = response.choices[0].message
            if not message.tool_calls:
                raise ValueError("模型未返回函数调用")

            tool_call = message.tool_calls[0]
            func_args = json.loads(tool_call.function.arguments)

            # 记录分析过程
            error_analysis = func_args.get('error_analysis', {})
            self.logger.info(f"错误分析 - 根本原因: {error_analysis.get('root_cause')}")
            self.logger.info(f"解决方案: {error_analysis.get('solution_approach')}")
            self.logger.debug(f"修改内容: {func_args.get('changes_made')}")

            # 提取修复后的代码
            fixed_code = func_args.get('fixed_code', '')
            return fixed_code

        except Exception as e:
            self.logger.error(f"Function Calling修复错误: {str(e)}")
            raise

    def _generate_code_with_prompt(
        self,
        question: str,
        df_info: Dict,
        history: List[Dict],
        error_feedback: Optional[Dict],
        plot_path: Optional[str]
    ) -> str:
        """
        使用传统Prompt方式生成代码（备用方案）

        Returns:
            生成的Python代码
        """
        self.logger.info("使用传统Prompt方式生成代码")

        # 获取全局上下文
        global_ctx = get_global_context()

        # 构建包含全局上下文的prompt
        # 注意：这里直接传递df_info作为兼容，但实际会在prompt中优先使用全局上下文
        user_prompt = self.prompt_manager.build_code_generation_prompt(
            question=question,
            df_info=df_info,
            history=history or [],
            error_feedback=error_feedback,
            plot_path=plot_path,
            global_context=global_ctx if global_ctx.is_ready() else None
        )

        messages = [
            {"role": "system", "content": self.prompt_manager.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        # 如果是错误重试，增加温度以获得不同结果
        temperature = self.temperature
        if error_feedback:
            temperature = min(self.temperature + 0.2, 0.5)
            self.logger.info(f"错误重试，提高温度至: {temperature}")

        response = self._call_api(messages, temperature)

        # 清理响应（移除可能的markdown格式）
        code = self._clean_code_response(response)

        self.logger.debug(f"生成的代码:\n{code}")
        return code

    def explain_result(
        self,
        question: str,
        code: str,
        result: Dict
    ) -> str:
        """
        解释执行结果

        Args:
            question: 用户问题
            code: 执行的代码
            result: 执行结果

        Returns:
            自然语言解释
        """
        self.logger.info("生成结果解释")

        user_prompt = self.prompt_manager.build_explanation_prompt(
            question=question,
            code=code,
            result=result
        )

        messages = [
            {
                "role": "system",
                "content": "你是一个数据分析专家，擅长用详细、清晰的语言解释分析结果。提供深入的数据洞察和具体的数值支撑。"
            },
            {"role": "user", "content": user_prompt}
        ]

        # 使用explanation_max_tokens以获得更详细的解释
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.explanation_max_tokens,  # 使用更大的token限制
                top_p=self.top_p,
            )
            explanation = response.choices[0].message.content
            self.logger.debug(f"API响应: {explanation[:200]}...")
            return explanation
        except Exception as e:
            self.logger.error(f"API调用失败: {str(e)}")
            raise

    @staticmethod
    def _clean_code_response(response: str) -> str:
        """
        清理代码响应，移除markdown格式

        Args:
            response: 原始响应

        Returns:
            清理后的代码
        """
        # 移除markdown代码块标记
        lines = response.strip().split('\n')

        # 如果第一行是```python或```，则移除
        if lines and lines[0].strip().startswith('```'):
            lines = lines[1:]

        # 如果最后一行是```，则移除
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]

        code = '\n'.join(lines).strip()

        return code

    def test_connection(self) -> bool:
        """
        测试API连接

        Returns:
            连接是否成功
        """
        try:
            messages = [
                {"role": "user", "content": "Hello"}
            ]
            self._call_api(messages)
            return True
        except Exception as e:
            self.logger.error(f"连接测试失败: {str(e)}")
            return False
