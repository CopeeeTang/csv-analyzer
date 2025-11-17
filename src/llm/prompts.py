"""Prompt模板管理"""

from typing import Dict, List, Optional


class PromptManager:
    """Prompt模板管理器"""

    SYSTEM_PROMPT = """你是一个专业的数据分析助手，擅长使用Python和pandas分析CSV数据。

你的任务是根据用户的问题生成Python代码或解释分析结果。

重要规则：
1. 生成代码时，只返回纯Python代码，不要使用markdown代码块格式（不要```python```）
2. 变量'df'已经预加载了CSV数据，直接使用即可
3. 代码要简洁、高效、安全
4. 需要打印的结果必须使用print()明确输出
5. 如果需要可视化，使用matplotlib，并用plt.savefig()保存图片到指定路径
6. 不要使用危险函数如eval、exec、os.system等
7. 【重要】不要使用任何import语句！所有需要的库已经预加载：pandas(pd)、numpy(np)、matplotlib.pyplot(plt)、seaborn(sns)，直接使用这些变量即可
8. 如果遇到错误信息，仔细分析原因并修正代码
9. 确保代码中没有import、from...import等导入语句
10. 【数据清洗】在进行数值计算前，务必检查并转换数据类型：
    - 如果列包含货币符号($)、逗号、百分号(%)等，先清洗数据
    - 使用 str.replace() 移除特殊字符，然后用 astype(float) 或 pd.to_numeric() 转换类型
    - 示例：df['Sales'] = df['Sales'].str.replace('$', '').str.replace(',', '').str.strip().astype(float)"""

    @staticmethod
    def format_df_info(df_info: Dict) -> str:
        """格式化DataFrame信息"""
        info_parts = [
            "【DataFrame信息】",
            f"列名: {', '.join(df_info['columns'])}",
            f"形状: {df_info['shape'][0]}行 × {df_info['shape'][1]}列",
            "\n数据类型:",
        ]

        for col, dtype in df_info['dtypes'].items():
            info_parts.append(f"  - {col}: {dtype}")

        info_parts.append("\n前5行数据预览:")
        # 简化显示
        info_parts.append(str(df_info.get('head_str', '')))

        return "\n".join(info_parts)

    @staticmethod
    def format_history(
        history: List[Dict],
        max_length_per_turn: int = 500,
        max_total_length: int = 2000
    ) -> str:
        """
        格式化对话历史（带长度控制）

        Args:
            history: 对话历史列表
            max_length_per_turn: 每轮最大字符数
            max_total_length: 总最大字符数

        Returns:
            格式化的历史字符串
        """
        if not history:
            return ""

        history_parts = ["【对话历史】"]
        current_length = len(history_parts[0])

        for i, turn in enumerate(history, 1):
            turn_parts = []
            turn_parts.append(f"\n第{i}轮:")
            turn_parts.append(f"问题: {turn['question']}")

            # 代码可能很长，截断处理
            code = turn['code']
            if len(code) > 300:
                code = code[:300] + "\n... (代码已截断)"
            turn_parts.append(f"代码:\n{code}")

            result = turn.get('result', {})
            if result.get('success'):
                stdout = result.get('stdout', '').strip()
                if stdout:
                    # 结果也可能很长，智能截断
                    if len(stdout) > 200:
                        stdout = stdout[:200] + "... (输出已截断)"
                    turn_parts.append(f"结果: {stdout}")
            else:
                error_msg = result.get('error', 'Unknown error')
                if len(error_msg) > 100:
                    error_msg = error_msg[:100] + "..."
                turn_parts.append(f"错误: {error_msg}")

            # 检查单轮长度
            turn_str = "\n".join(turn_parts)
            if len(turn_str) > max_length_per_turn:
                turn_str = turn_str[:max_length_per_turn] + "\n... (本轮已截断)"

            # 检查总长度
            if current_length + len(turn_str) > max_total_length:
                history_parts.append("\n... (更早的历史已省略)")
                break

            history_parts.append(turn_str)
            current_length += len(turn_str)

        return "\n".join(history_parts)

    @staticmethod
    def estimate_token_count(text: str) -> int:
        """
        估算文本的Token数量（粗略估计）

        中文：1字符 ≈ 1.5 token
        英文：1词 ≈ 1 token，1字符 ≈ 0.25 token

        Args:
            text: 文本内容

        Returns:
            估算的token数
        """
        # 简单估算：中文字符较多时按1.5倍计算
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        total_chars = len(text)
        english_chars = total_chars - chinese_chars

        # 粗略估算
        estimated_tokens = int(chinese_chars * 1.5 + english_chars * 0.25)
        return estimated_tokens

    @staticmethod
    def format_error_feedback(error_info: Dict) -> str:
        """
        格式化错误反馈（引导思考链）

        Args:
            error_info: 错误信息字典

        Returns:
            带思考引导的错误反馈
        """
        parts = [
            "【上次代码执行失败】",
            "\n失败的代码:",
            error_info['code'],
            f"\n错误类型: {error_info['error_type']}",
            f"错误信息: {error_info['error_message']}",
        ]

        if error_info.get('traceback'):
            # 只取最后几行，避免过长
            traceback_lines = error_info['traceback'].split('\n')
            key_traceback = '\n'.join(traceback_lines[-8:])
            parts.append(f"\n关键错误堆栈:\n{key_traceback}")

        # 引导思考的prompt
        parts.append("\n【请按以下步骤分析和修复】")
        parts.append("1. 分析错误原因：")
        parts.append("   - 为什么会出现这个错误？")
        parts.append("   - 是数据问题、语法问题还是逻辑问题？")
        parts.append("\n2. 思考解决方案：")
        parts.append("   - 有哪些可能的修复方法？")
        parts.append("   - 最佳的解决方案是什么？")
        parts.append("\n3. 生成修正后的代码：")
        parts.append("   - 确保代码可以直接执行")
        parts.append("   - 验证逻辑的正确性")

        parts.append("\n注意：直接生成修正后的完整代码，不要输出分析过程的文字。")

        return "\n".join(parts)

    @classmethod
    def build_code_generation_prompt(
        cls,
        question: str,
        df_info: Dict,
        history: List[Dict] = None,
        error_feedback: Optional[Dict] = None,
        plot_path: Optional[str] = None,
        global_context = None
    ) -> str:
        """
        构建代码生成的prompt

        Args:
            question: 用户问题
            df_info: DataFrame信息（备用）
            history: 对话历史
            error_feedback: 错误反馈信息
            plot_path: 图表保存路径
            global_context: 全局上下文对象（优先使用）

        Returns:
            完整的prompt
        """
        parts = []

        # 优先使用全局上下文，否则回退到df_info
        if global_context and hasattr(global_context, 'get_global_context_prompt'):
            parts.append(global_context.get_global_context_prompt())
        else:
            parts.append(cls.format_df_info(df_info))

        # 添加历史
        if history:
            parts.append("\n" + cls.format_history(history))

        # 添加错误反馈
        if error_feedback:
            parts.append("\n" + cls.format_error_feedback(error_feedback))

        # 添加当前问题
        parts.append(f"\n【当前问题】\n{question}")

        # 添加要求
        requirements = [
            "\n【生成要求】",
            "1. 只返回可执行的Python代码，不要markdown格式",
            "2. 变量df已加载，直接使用",
            "3. 使用print()输出关键结果",
        ]

        if plot_path:
            requirements.append(f"4. 如需画图，使用plt.savefig('{plot_path}')保存")

        parts.append("\n".join(requirements))

        return "\n".join(parts)

    @staticmethod
    def build_explanation_prompt(
        question: str,
        code: str,
        result: Dict
    ) -> str:
        """
        构建结果解释的prompt

        Args:
            question: 用户问题
            code: 执行的代码
            result: 执行结果

        Returns:
            解释prompt
        """
        parts = [
            f"用户问题: {question}",
            f"\n执行的代码:\n{code}",
        ]

        if result.get('success'):
            stdout = result.get('stdout', '').strip()
            parts.append(f"\n执行结果:\n{stdout}")

            if result.get('plot_saved'):
                parts.append(f"\n生成的图表: {result['plot_path']}")

        parts.append(
            "\n请基于分析结果回答用户的问题，提供详细、深入的分析说明："
            "\n\n## 分析要求："
            "\n1. **直接回答问题**：清晰、明确地回答用户提出的问题"
            "\n2. **数据洞察**：深入分析数据之间的关联、趋势和模式"
            "\n3. **具体数值支撑**：提供详细的数据发现（具体数值、变化率、百分比、相关性等）"
            "\n4. **多维度分析**："
            "\n   - 整体趋势描述"
            "\n   - 关键时间点/类别的特征"
            "\n   - 异常值或特殊模式识别"
            "\n   - 可能的原因分析"
            "\n5. **结论与建议**：基于数据给出清晰的结论和可行的建议"
            "\n\n## 展示要求："
            "\n- 使用Markdown格式，结构清晰（标题、列表、加粗重点）"
            "\n- 重点关注数据本身的含义和关联，而非图表的技术细节"
            "\n- 用具体的数值和百分比来支撑每个观点"
            "\n- 语言专业但易懂，避免冗余但要详尽"
            "\n- 如果数据量大，可以分段说明（如：总体趋势、细分分析、关键发现）"
        )

        return "\n".join(parts)
