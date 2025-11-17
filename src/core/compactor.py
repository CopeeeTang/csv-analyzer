"""智能对话压缩器 - 参考Claude Code的Compact机制"""

import logging
from typing import List, Dict, Any, Optional


class ConversationCompactor:
    """
    智能对话压缩器

    功能：
    1. 自动检测是否需要压缩（基于token或长度阈值）
    2. 提取关键信息（决策、代码变更、错误等）
    3. 生成结构化摘要
    4. 保留最近N条完整消息
    """

    def __init__(
        self,
        llm_client,
        compression_threshold: float = 0.7,  # 达到70%阈值时触发
        target_ratio: float = 0.4,  # 压缩到40%
        keep_recent: int = 3  # 保留最近3条完整消息
    ):
        """
        初始化压缩器

        Args:
            llm_client: LLM客户端（用于智能摘要）
            compression_threshold: 触发压缩的阈值（0-1）
            target_ratio: 压缩目标比例（0-1）
            keep_recent: 保留最近N条完整消息
        """
        self.llm_client = llm_client
        self.compression_threshold = compression_threshold
        self.target_ratio = target_ratio
        self.keep_recent = keep_recent
        self.logger = logging.getLogger(__name__)

    def should_compact(
        self,
        history: List[Dict],
        max_length: int = 3000
    ) -> bool:
        """
        判断是否需要压缩

        Args:
            history: 对话历史
            max_length: 最大允许长度（字符数）

        Returns:
            是否需要压缩
        """
        if len(history) < self.keep_recent + 2:
            # 历史太短，不需要压缩
            return False

        # 估算当前长度
        current_length = self._estimate_history_length(history)

        # 判断是否超过阈值
        threshold_length = max_length * self.compression_threshold

        should_compact = current_length >= threshold_length

        if should_compact:
            self.logger.info(
                f"触发压缩: 当前长度{current_length} >= "
                f"阈值{threshold_length:.0f} ({self.compression_threshold*100}%)"
            )

        return should_compact

    def compact(
        self,
        history: List[Dict],
        custom_instruction: Optional[str] = None
    ) -> List[Dict]:
        """
        压缩对话历史

        Args:
            history: 完整的对话历史
            custom_instruction: 自定义压缩指令

        Returns:
            压缩后的历史（摘要 + 最近的完整消息）
        """
        if len(history) <= self.keep_recent:
            return history

        # 分离：要压缩的部分 vs 保留的部分
        to_compress = history[:-self.keep_recent]
        to_keep = history[-self.keep_recent:]

        self.logger.info(
            f"开始压缩: 共{len(history)}轮，"
            f"压缩{len(to_compress)}轮，保留{len(to_keep)}轮"
        )

        # 提取关键信息
        key_info = self._extract_key_information(to_compress)

        # 生成摘要（不使用LLM，使用规则提取以提高速度）
        summary = self._create_summary(key_info, custom_instruction)

        # 构建压缩后的历史
        compacted = [{
            'question': '【历史对话摘要】',
            'code': '',
            'result': {'success': True, 'stdout': ''},
            'explanation': summary
        }] + to_keep

        self.logger.info(f"压缩完成: {len(history)}轮 -> {len(compacted)}轮(含摘要)")

        return compacted

    def _estimate_history_length(self, history: List[Dict]) -> int:
        """
        估算历史记录的长度

        Args:
            history: 对话历史

        Returns:
            估算的字符数
        """
        total_length = 0

        for turn in history:
            total_length += len(turn.get('question', ''))
            total_length += len(turn.get('code', ''))
            total_length += len(str(turn.get('result', '')))
            total_length += len(turn.get('explanation', ''))

        return total_length

    def _extract_key_information(
        self,
        history: List[Dict]
    ) -> Dict[str, Any]:
        """
        提取关键信息（规则based，快速）

        Args:
            history: 要压缩的对话历史

        Returns:
            关键信息字典
        """
        key_info = {
            'important_decisions': [],
            'code_changes': [],
            'errors_encountered': [],
            'key_findings': [],
            'variables_defined': set()
        }

        for i, turn in enumerate(history):
            question = turn.get('question', '')
            code = turn.get('code', '')
            result = turn.get('result', {})
            explanation = turn.get('explanation', '')

            # 提取决策关键词
            decision_keywords = ['决定', '选择', '采用', 'decided', 'chose']
            if any(kw in question.lower() or kw in explanation.lower()
                   for kw in decision_keywords):
                key_info['important_decisions'].append({
                    'turn': i + 1,
                    'decision': question[:100]
                })

            # 提取代码变更（简化）
            if code and len(code) > 50:
                # 提取函数定义、变量赋值等
                key_lines = []
                for line in code.split('\n'):
                    line = line.strip()
                    if line.startswith('def ') or '=' in line[:30]:
                        key_lines.append(line[:60])
                        if len(key_lines) >= 3:
                            break

                if key_lines:
                    key_info['code_changes'].append({
                        'turn': i + 1,
                        'summary': '; '.join(key_lines)
                    })

            # 提取错误
            if not result.get('success'):
                error_type = result.get('error_type', 'Unknown')
                error_msg = result.get('error', '')[:100]
                key_info['errors_encountered'].append({
                    'turn': i + 1,
                    'error': f"{error_type}: {error_msg}"
                })

            # 提取关键发现（从explanation中）
            finding_keywords = ['发现', '结果显示', '数据表明', 'found', 'shows']
            if any(kw in explanation.lower() for kw in finding_keywords):
                key_info['key_findings'].append({
                    'turn': i + 1,
                    'finding': explanation[:150]
                })

        return key_info

    def _create_summary(
        self,
        key_info: Dict[str, Any],
        custom_instruction: Optional[str] = None
    ) -> str:
        """
        创建结构化摘要（不使用LLM）

        Args:
            key_info: 提取的关键信息
            custom_instruction: 自定义指令

        Returns:
            摘要文本
        """
        summary_parts = []

        if custom_instruction:
            summary_parts.append(f"**压缩说明**: {custom_instruction}\n")

        summary_parts.append("## 历史对话摘要\n")

        # 重要决策
        if key_info['important_decisions']:
            summary_parts.append("### 关键决策")
            for dec in key_info['important_decisions'][:5]:  # 最多5个
                summary_parts.append(f"- 第{dec['turn']}轮: {dec['decision']}")
            summary_parts.append("")

        # 代码变更
        if key_info['code_changes']:
            summary_parts.append("### 主要代码操作")
            for change in key_info['code_changes'][:5]:
                summary_parts.append(f"- 第{change['turn']}轮: {change['summary']}")
            summary_parts.append("")

        # 遇到的错误
        if key_info['errors_encountered']:
            summary_parts.append("### 遇到的错误")
            for err in key_info['errors_encountered'][:3]:
                summary_parts.append(f"- 第{err['turn']}轮: {err['error']}")
            summary_parts.append("")

        # 关键发现
        if key_info['key_findings']:
            summary_parts.append("### 关键发现")
            for finding in key_info['key_findings'][:5]:
                summary_parts.append(f"- 第{finding['turn']}轮: {finding['finding']}")
            summary_parts.append("")

        if len(summary_parts) == 1:  # 只有标题
            summary_parts.append("*（早期对话未发现关键信息）*")

        return "\n".join(summary_parts)

    def compact_with_llm(
        self,
        history: List[Dict],
        custom_instruction: Optional[str] = None
    ) -> List[Dict]:
        """
        使用LLM进行智能压缩（可选，更慢但更智能）

        Args:
            history: 完整的对话历史
            custom_instruction: 自定义压缩指令

        Returns:
            压缩后的历史
        """
        # TODO: 实现基于LLM的智能摘要
        # 这里可以调用llm_client生成更智能的摘要
        self.logger.warning("LLM压缩暂未实现，使用规则based压缩")
        return self.compact(history, custom_instruction)
