"""Thinking内容解析器

解析和处理GLM-4.6的深度思考（thinking）模式返回的内容
"""

import logging
from typing import Dict, Optional
from rich.markdown import Markdown
from rich.panel import Panel
from rich import box


class ThinkingParser:
    """解析和格式化模型的思考过程"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_thinking_response(self, response) -> Dict[str, str]:
        """
        解析thinking模式的API响应

        Args:
            response: API响应对象

        Returns:
            包含thinking_content和final_answer的字典
        """
        try:
            message = response.choices[0].message

            # 提取thinking内容（如果存在）
            thinking_content = getattr(message, 'reasoning_content', None)

            # 提取最终答案
            final_answer = message.content

            result = {
                'thinking_content': thinking_content or '',
                'final_answer': final_answer or '',
                'has_thinking': bool(thinking_content)
            }

            if thinking_content:
                self.logger.info(f"成功解析thinking内容，长度: {len(thinking_content)}")
            else:
                self.logger.debug("响应中无thinking内容")

            return result

        except Exception as e:
            self.logger.error(f"解析thinking响应失败: {str(e)}")
            return {
                'thinking_content': '',
                'final_answer': '',
                'has_thinking': False,
                'error': str(e)
            }

    def extract_code_from_thinking(self, final_answer: str) -> Optional[str]:
        """
        从thinking的最终答案中提取代码（严格过滤中文解释）

        Args:
            final_answer: 最终答案文本

        Returns:
            提取的Python代码，如果没有则返回None
        """
        # 移除markdown代码块标记
        lines = final_answer.strip().split('\n')

        # 查找代码块
        in_code_block = False
        code_lines = []

        for line in lines:
            # 检测代码块开始
            if line.strip().startswith('```python') or (line.strip().startswith('```') and not in_code_block):
                in_code_block = True
                continue
            # 检测代码块结束
            elif line.strip() == '```' and in_code_block:
                break  # 找到第一个代码块后立即停止
            # 提取代码块内容
            elif in_code_block:
                code_lines.append(line)

        if code_lines:
            # 过滤掉明显的解释性文字（但保留所有注释）
            filtered_code = []
            for line in code_lines:
                stripped = line.strip()

                # 保留注释（无论是否包含中文）
                if stripped.startswith('#'):
                    filtered_code.append(line)
                    continue

                # 保留空行
                if not stripped:
                    filtered_code.append(line)
                    continue

                # 检查是否为纯解释性文字（不是有效Python语法）
                if self._is_explanation_line(line):
                    self.logger.warning(f"过滤掉解释性文字行: {line[:50]}")
                    continue

                # 保留其他所有行（包括含中文的代码）
                filtered_code.append(line)

            return '\n'.join(filtered_code)

        # 如果没有代码块标记，尝试逐行提取纯代码
        # 严格过滤：只保留明显是Python代码的行
        code_lines = []
        for line in lines:
            stripped = line.strip()
            # 跳过空行
            if not stripped:
                continue
            # 跳过包含大量中文的行（解释性文字）
            if self._is_explanation_line(line):
                continue
            # 保留看起来像代码的行
            if self._looks_like_code(line):
                code_lines.append(line)

        if code_lines:
            return '\n'.join(code_lines)

        return None

    def _contains_chinese(self, text: str) -> bool:
        """检查文本是否包含中文字符"""
        return any('\u4e00' <= char <= '\u9fff' for char in text)

    def _is_explanation_line(self, line: str) -> bool:
        """判断是否为解释性文字行（非代码）"""
        stripped = line.strip()

        # 如果是注释，不算解释行
        if stripped.startswith('#'):
            return False

        # 如果包含明显的代码语法，不算解释行
        if self._looks_like_code(line):
            return False

        # 常见解释性开头（这些通常不会出现在有效Python代码中）
        explanation_patterns = [
            '这个修复版本', '这样可以确保', '注意：', '说明：',
            '步骤', '原因分析', '解决方案', '修改点：',
            '以上代码', '上述代码', '该代码', '此代码'
        ]

        return any(pattern in stripped for pattern in explanation_patterns)

    def _looks_like_code(self, line: str) -> bool:
        """判断是否看起来像Python代码"""
        stripped = line.strip()

        # 空行
        if not stripped:
            return True

        # 注释
        if stripped.startswith('#'):
            return True

        # 常见Python语法
        code_indicators = [
            '=', 'df[', 'print(', 'plt.', 'pd.', 'np.',
            'if ', 'for ', 'while ', 'def ', 'class ',
            'import ', 'from ', 'return ', 'yield ',
            '.groupby(', '.sum(', '.mean(', '.apply(',
            'else:', 'elif ', 'try:', 'except '
        ]

        return any(indicator in stripped for indicator in code_indicators)

    def format_thinking_for_display(self, thinking_content: str, max_length: int = 500) -> str:
        """
        格式化thinking内容以供UI显示

        Args:
            thinking_content: 原始thinking内容
            max_length: 最大显示长度（字符数）

        Returns:
            格式化后的字符串
        """
        if not thinking_content:
            return ""

        # 简化thinking内容为关键步骤
        lines = thinking_content.split('\n')
        formatted_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 提取关键信息（简化处理）
            if any(keyword in stripped for keyword in ['分析', '思考', '考虑', '因为', '所以', '步骤']):
                formatted_lines.append(f"• {stripped[:100]}")

        formatted = '\n'.join(formatted_lines[:10])  # 最多10条关键信息

        # 如果超过最大长度，截断
        if len(formatted) > max_length:
            formatted = formatted[:max_length] + "..."

        return formatted

    def create_thinking_panel(self, thinking_content: str, title: str = "模型思考过程") -> Panel:
        """
        创建Rich Panel显示thinking内容

        Args:
            thinking_content: thinking内容
            title: Panel标题

        Returns:
            Rich Panel对象
        """
        formatted = self.format_thinking_for_display(thinking_content)

        if not formatted:
            formatted = "（无思考过程记录）"

        md = Markdown(formatted)
        return Panel(
            md,
            title=f"[dim cyan]{title}[/dim cyan]",
            border_style="dim cyan",
            box=box.ROUNDED,
            padding=(1, 2)
        )

    def extract_error_analysis(self, thinking_content: str) -> Dict[str, str]:
        """
        从thinking内容中提取错误分析要点

        Args:
            thinking_content: thinking内容

        Returns:
            包含root_cause、solution等的字典
        """
        analysis = {
            'root_cause': '',
            'solution_approach': '',
            'key_insights': []
        }

        if not thinking_content:
            return analysis

        # 简单的关键词匹配（可以根据实际情况优化）
        lines = thinking_content.split('\n')

        for line in lines:
            lower_line = line.lower()
            if '错误' in lower_line or 'error' in lower_line or '原因' in lower_line:
                analysis['root_cause'] += line.strip() + ' '
            elif '解决' in lower_line or 'solution' in lower_line or '修复' in lower_line:
                analysis['solution_approach'] += line.strip() + ' '
            elif '关键' in lower_line or '重要' in lower_line:
                analysis['key_insights'].append(line.strip())

        return analysis
