"""会话管理"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from .compactor import ConversationCompactor
    COMPACTOR_AVAILABLE = True
except ImportError:
    COMPACTOR_AVAILABLE = False

from .token_counter import TokenCounter


@dataclass
class ConversationTurn:
    """单轮对话"""
    timestamp: str
    question: str
    code: str
    execution_result: Dict[str, Any]
    explanation: str
    retry_count: int = 0
    plot_path: Optional[str] = None


class SessionManager:
    """会话管理器"""

    def __init__(
        self,
        session_id: str = None,
        save_dir: str = "output/sessions",
        enable_smart_compression: bool = True,
        compression_threshold: float = 0.7,
        model_max_tokens: int = None
    ):
        """
        初始化会话管理器

        Args:
            session_id: 会话ID，如果为None则自动生成
            save_dir: 会话保存目录
            enable_smart_compression: 是否启用智能压缩
            compression_threshold: 压缩触发阈值（已废弃，改用token计数）
            model_max_tokens: 模型最大token数（默认128K for GLM-4-plus）
        """
        self.session_id = session_id or self._generate_session_id()
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self.turns: List[ConversationTurn] = []
        self.csv_path: Optional[str] = None
        self.created_at = datetime.now().isoformat()

        # Token计数器（用于上下文窗口管理）
        self.token_counter = TokenCounter(
            model_max_tokens=model_max_tokens,
            compression_threshold=compression_threshold
        )

        # 智能压缩设置
        self.enable_smart_compression = enable_smart_compression and COMPACTOR_AVAILABLE
        self.compression_threshold = compression_threshold  # 保留以兼容旧代码
        self.compactor: Optional['ConversationCompactor'] = None

        self.logger = logging.getLogger(__name__)
        self.logger.info(f"会话创建: {self.session_id}")

        if self.enable_smart_compression:
            self.logger.info("智能压缩已启用（基于token计数）")
        elif enable_smart_compression and not COMPACTOR_AVAILABLE:
            self.logger.warning("Compactor不可用，禁用智能压缩")

    @staticmethod
    def _generate_session_id() -> str:
        """生成会话ID"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def add_turn(self, turn: ConversationTurn):
        """
        添加一轮对话

        Args:
            turn: ConversationTurn对象
        """
        self.turns.append(turn)
        self.logger.info(f"添加对话轮次 #{len(self.turns)}")

    def set_compactor(self, compactor: 'ConversationCompactor'):
        """
        设置压缩器（用于LLM摘要）

        Args:
            compactor: ConversationCompactor实例
        """
        if self.enable_smart_compression:
            self.compactor = compactor
            self.logger.info("Compactor已设置")

    def get_recent_history(
        self,
        n: int = 3,
        auto_compact: bool = True,
        current_question: str = ""
    ) -> List[Dict]:
        """
        获取最近N轮对话历史（带自动压缩）

        Args:
            n: 获取的轮次数
            auto_compact: 是否自动触发压缩
            current_question: 当前问题（用于token计算）

        Returns:
            历史对话列表（可能包含压缩摘要）
        """
        # 将turns转换为字典（只包含成功部分）
        history_dicts = self._turns_to_dicts(self.turns, only_successful=True)

        # 检查是否需要压缩（基于token计数）
        if auto_compact and self.enable_smart_compression and self.compactor:
            # 计算当前上下文的token数
            token_info = self.token_counter.calculate_context_tokens(
                question=current_question,
                history=history_dicts
            )

            # 判断是否需要压缩
            if self.token_counter.should_compact(token_info['total']):
                self.logger.info(
                    f"自动触发智能压缩 (tokens: {token_info['total']}/{self.token_counter.safe_max_tokens})"
                )
                return self.compact_history(n)

        # 不压缩，直接返回最近N轮（只包含成功的部分）
        recent_history = history_dicts[-n:] if len(history_dicts) > n else history_dicts

        return recent_history

    def calculate_current_tokens(self, current_question: str = "") -> Dict[str, int]:
        """
        计算当前上下文的token使用量

        Args:
            current_question: 当前问题

        Returns:
            token使用详情
        """
        history_dicts = self._turns_to_dicts(self.turns, only_successful=True)

        return self.token_counter.calculate_context_tokens(
            question=current_question,
            history=history_dicts
        )

    def get_context_window_status(self, current_question: str = "") -> Dict[str, Any]:
        """
        获取上下文窗口状态

        Args:
            current_question: 当前问题

        Returns:
            上下文窗口状态
        """
        token_info = self.calculate_current_tokens(current_question)

        return self.token_counter.get_context_window_status(token_info['total'])

    def compact_history(
        self,
        keep_recent: int = 3,
        custom_instruction: Optional[str] = None
    ) -> List[Dict]:
        """
        手动触发智能压缩

        Args:
            keep_recent: 保留最近N轮完整对话
            custom_instruction: 自定义压缩指令

        Returns:
            压缩后的历史
        """
        if not self.compactor:
            self.logger.warning("Compactor未设置，返回原始历史")
            return self.get_recent_history(keep_recent, auto_compact=False)

        # 转换为dict格式（只包含成功的部分）
        history_dicts = self._turns_to_dicts(self.turns, only_successful=True)

        # 执行压缩
        compacted = self.compactor.compact(
            history_dicts,
            custom_instruction=custom_instruction
        )

        return compacted

    def _turns_to_dicts(
        self,
        turns: List[ConversationTurn],
        only_successful: bool = True
    ) -> List[Dict]:
        """
        将ConversationTurn列表转换为字典列表

        Args:
            turns: ConversationTurn列表
            only_successful: 是否只包含成功的执行（不包含错误信息）

        Returns:
            字典列表
        """
        result = []

        for turn in turns:
            turn_dict = {
                'question': turn.question,
                'code': turn.code,
                'explanation': turn.explanation
            }

            # 根据only_successful参数决定是否包含执行结果
            if only_successful:
                # 只包含成功的执行结果（不包含错误）
                if turn.execution_result.get('success'):
                    turn_dict['result'] = {
                        'success': True,
                        'stdout': turn.execution_result.get('stdout', '')
                    }
                    # 如果有图表路径，也包含进去
                    if turn.execution_result.get('plot_saved'):
                        turn_dict['result']['plot_saved'] = True
                        turn_dict['result']['plot_path'] = turn.execution_result.get('plot_path')
                else:
                    # 失败的情况，result字段只标记为失败，不包含错误详情
                    turn_dict['result'] = {'success': False}
            else:
                # 包含所有执行结果（包括错误）
                turn_dict['result'] = turn.execution_result

            result.append(turn_dict)

        return result

    def save(self, filepath: str = None):
        """
        保存会话到JSON文件

        Args:
            filepath: 保存路径，如果为None则使用默认路径
        """
        if filepath is None:
            filepath = self.save_dir / f"{self.session_id}.json"
        else:
            filepath = Path(filepath)

        data = {
            'session_id': self.session_id,
            'created_at': self.created_at,
            'csv_path': self.csv_path,
            'total_turns': len(self.turns),
            'turns': [asdict(turn) for turn in self.turns]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"会话已保存: {filepath}")

    @classmethod
    def load(cls, filepath: str) -> 'SessionManager':
        """
        从JSON文件加载会话

        Args:
            filepath: 会话文件路径

        Returns:
            SessionManager对象
        """
        filepath = Path(filepath)

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        session = cls(session_id=data['session_id'])
        session.created_at = data['created_at']
        session.csv_path = data.get('csv_path')

        # 恢复对话轮次
        for turn_data in data['turns']:
            turn = ConversationTurn(**turn_data)
            session.turns.append(turn)

        return session

    def export_report(self, output_path: str = None) -> str:
        """
        导出Markdown格式的分析报告

        Args:
            output_path: 输出路径，如果为None则使用默认路径

        Returns:
            报告文件路径
        """
        if output_path is None:
            output_path = self.save_dir.parent / "reports" / f"{self.session_id}.md"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 生成报告内容
        lines = [
            f"# CSV数据分析报告",
            f"\n**会话ID**: {self.session_id}",
            f"**创建时间**: {self.created_at}",
            f"**数据文件**: {self.csv_path or 'N/A'}",
            f"**分析轮次**: {len(self.turns)}",
            "\n---\n"
        ]

        # 添加每轮对话
        for i, turn in enumerate(self.turns, 1):
            lines.append(f"## 第{i}轮分析\n")
            lines.append(f"**问题**: {turn.question}\n")

            lines.append(f"**生成的代码**:")
            lines.append(f"```python\n{turn.code}\n```\n")

            if turn.execution_result.get('success'):
                stdout = turn.execution_result.get('stdout', '').strip()
                if stdout:
                    lines.append(f"**执行结果**:")
                    lines.append(f"```\n{stdout}\n```\n")

                if turn.plot_path:
                    lines.append(f"**生成的图表**: `{turn.plot_path}`\n")
            else:
                lines.append(f"**执行错误**: {turn.execution_result.get('error')}\n")

            lines.append(f"**分析解释**:\n{turn.explanation}\n")

            if turn.retry_count > 0:
                lines.append(f"*（重试次数: {turn.retry_count}）*\n")

            lines.append("\n---\n")

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        self.logger.info(f"报告已导出: {output_path}")
        return str(output_path)

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取会话统计信息

        Returns:
            统计信息字典
        """
        total_turns = len(self.turns)
        success_count = sum(1 for t in self.turns if t.execution_result.get('success'))
        total_retries = sum(t.retry_count for t in self.turns)
        plots_count = sum(1 for t in self.turns if t.plot_path)

        return {
            'total_turns': total_turns,
            'success_count': success_count,
            'failed_count': total_turns - success_count,
            'total_retries': total_retries,
            'plots_generated': plots_count
        }
