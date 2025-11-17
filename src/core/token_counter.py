"""Token计数和上下文窗口管理

管理模型的上下文窗口，跟踪token使用量，并在接近限制时触发压缩
"""

import logging
from typing import Dict, List, Any, Optional
from .global_context import get_global_context


class TokenCounter:
    """
    Token计数器和上下文窗口管理器

    用于跟踪当前上下文的token使用量，并在达到阈值时触发压缩
    """

    # GLM-4-plus模型的上下文长度限制
    MODEL_MAX_TOKENS = 128000  # 128K tokens

    # 默认安全阈值
    DEFAULT_THRESHOLD = 0.7

    def __init__(
        self,
        model_max_tokens: int = None,
        compression_threshold: float = None
    ):
        """
        初始化Token计数器

        Args:
            model_max_tokens: 模型最大token数（默认128K for GLM-4-plus）
            compression_threshold: 压缩触发阈值（0-1之间，默认0.7即70%）
        """
        self.model_max_tokens = model_max_tokens or self.MODEL_MAX_TOKENS
        self.compression_threshold = compression_threshold or self.DEFAULT_THRESHOLD
        self.safe_max_tokens = int(self.model_max_tokens * self.compression_threshold)
        self.logger = logging.getLogger(__name__)

        self.logger.info(
            f"Token计数器初始化: 最大={self.model_max_tokens}, "
            f"安全阈值={self.safe_max_tokens} ({self.compression_threshold*100:.0f}%)"
        )

    def estimate_tokens(self, text: str) -> int:
        """
        估算文本的Token数量

        使用简化的估算方法：
        - 中文：1字符 ≈ 1.5 token
        - 英文：1词 ≈ 1 token，1字符 ≈ 0.25 token
        - 代码：1字符 ≈ 0.4 token

        Args:
            text: 文本内容

        Returns:
            估算的token数
        """
        if not text:
            return 0

        # 统计中文字符
        chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')

        # 统计代码特征（如果包含大量代码语法）
        code_indicators = ['def ', 'import ', 'print(', 'if ', 'for ', 'while ']
        code_density = sum(text.count(indicator) for indicator in code_indicators)
        is_code_heavy = code_density > 5

        total_chars = len(text)
        english_chars = total_chars - chinese_count

        if is_code_heavy:
            # 代码密集型文本
            estimated = int(chinese_count * 1.5 + english_chars * 0.4)
        else:
            # 普通文本
            estimated = int(chinese_count * 1.5 + english_chars * 0.25)

        return estimated

    def calculate_context_tokens(
        self,
        question: str,
        history: List[Dict],
        global_context_tokens: Optional[int] = None
    ) -> Dict[str, int]:
        """
        计算当前上下文的总token数

        Args:
            question: 当前问题
            history: 历史对话（已过滤，只包含成功部分）
            global_context_tokens: 全局上下文token数（可选，会自动计算）

        Returns:
            token使用详情字典
        """
        tokens = {
            'question': self.estimate_tokens(question),
            'global_context': 0,
            'history': 0,
            'total': 0
        }

        # 计算全局上下文（DataFrame元数据 + Sandbox配置）
        if global_context_tokens is not None:
            tokens['global_context'] = global_context_tokens
        else:
            global_ctx = get_global_context()
            if global_ctx.is_ready():
                ctx_prompt = global_ctx.get_global_context_prompt()
                tokens['global_context'] = self.estimate_tokens(ctx_prompt)

        # 计算历史对话token
        for turn in history:
            # 问题
            tokens['history'] += self.estimate_tokens(turn.get('question', ''))

            # 代码
            tokens['history'] += self.estimate_tokens(turn.get('code', ''))

            # 成功的执行结果（stdout）
            result = turn.get('result', {})
            if result.get('success'):
                stdout = result.get('stdout', '')
                tokens['history'] += self.estimate_tokens(stdout)

            # 解释（可能较长）
            explanation = turn.get('explanation', '')
            tokens['history'] += self.estimate_tokens(explanation)

        # 总计
        tokens['total'] = tokens['question'] + tokens['global_context'] + tokens['history']

        return tokens

    def should_compact(self, total_tokens: int) -> bool:
        """
        判断是否应该触发压缩

        Args:
            total_tokens: 当前总token数

        Returns:
            是否应该压缩
        """
        should = total_tokens >= self.safe_max_tokens

        if should:
            usage_pct = (total_tokens / self.model_max_tokens) * 100
            self.logger.warning(
                f"上下文窗口达到阈值！当前: {total_tokens}/{self.safe_max_tokens} "
                f"({usage_pct:.1f}%)"
            )

        return should

    def get_context_window_status(self, total_tokens: int) -> Dict[str, Any]:
        """
        获取上下文窗口状态

        Args:
            total_tokens: 当前总token数

        Returns:
            状态字典，包含使用量、剩余量、百分比等
        """
        remaining = self.safe_max_tokens - total_tokens
        usage_pct = (total_tokens / self.safe_max_tokens) * 100

        # 状态分级
        if usage_pct >= 100:
            status = 'critical'  # 超出阈值
        elif usage_pct >= 80:
            status = 'warning'   # 接近阈值
        elif usage_pct >= 50:
            status = 'normal'    # 正常
        else:
            status = 'healthy'   # 健康

        return {
            'total_tokens': total_tokens,
            'max_tokens': self.safe_max_tokens,
            'remaining_tokens': remaining,
            'usage_percentage': usage_pct,
            'status': status,
            'should_compact': self.should_compact(total_tokens)
        }

    def format_token_display(self, total_tokens: int) -> str:
        """
        格式化token显示文本（用于UI）

        Args:
            total_tokens: 当前总token数

        Returns:
            格式化的显示文本
        """
        status = self.get_context_window_status(total_tokens)

        # 格式化数字（添加千位分隔符）
        total_str = f"{total_tokens:,}"
        max_str = f"{self.safe_max_tokens:,}"
        remaining_str = f"{status['remaining_tokens']:,}"

        # 根据状态选择颜色
        if status['status'] == 'critical':
            color = 'red'
        elif status['status'] == 'warning':
            color = 'yellow'
        elif status['status'] == 'normal':
            color = 'cyan'
        else:
            color = 'green'

        return (
            f"[{color}]Context: {total_str}/{max_str} tokens "
            f"({status['usage_percentage']:.1f}%) | "
            f"Remaining: {remaining_str}[/{color}]"
        )
