"""工作流编排 - 整合所有模块"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from . import CodeExecutor
from .session import SessionManager, ConversationTurn
from .csv_handler import CSVHandler
from ..llm import GLMClient
from ..llm.async_error_analyzer import AsyncErrorAnalyzer
from ..cli import RichInterface


class AnalysisWorkflow:
    """数据分析工作流"""

    def __init__(
        self,
        llm_client: GLMClient,
        csv_handler: CSVHandler,
        executor: CodeExecutor,
        session_manager: SessionManager,
        interface: RichInterface,
        max_retries: int = 3,
        plot_dir: str = "output/plots"
    ):
        """
        初始化工作流

        Args:
            llm_client: LLM客户端
            csv_handler: CSV处理器
            executor: 代码执行器
            session_manager: 会话管理器
            interface: 用户界面
            max_retries: 最大重试次数
            plot_dir: 图表保存目录
        """
        self.llm = llm_client
        self.csv = csv_handler
        self.executor = executor
        self.session = session_manager
        self.ui = interface
        self.max_retries = max_retries
        self.plot_dir = Path(plot_dir)
        self.plot_dir.mkdir(parents=True, exist_ok=True)

        # 初始化异步错误分析器
        self.async_error_analyzer = AsyncErrorAnalyzer(
            client=llm_client.client,
            model=llm_client.model,
            temperature=0.3,  # 错误分析时使用稍高的温度
            max_tokens=llm_client.max_tokens
        )

        self.logger = logging.getLogger(__name__)

    def analyze_question(self, question: str, turn_number: int) -> bool:
        """
        分析单个问题（完整流程）

        Args:
            question: 用户问题
            turn_number: 轮次编号

        Returns:
            是否成功
        """
        self.ui.show_question(question, turn_number)

        # 显示上下文窗口状态
        context_status = self.session.get_context_window_status(current_question=question)
        token_display = self.session.token_counter.format_token_display(
            context_status['total_tokens']
        )
        self.ui.show_context_window(token_display, context_status)

        # 获取历史上下文（会自动检查是否需要压缩）
        history = self.session.get_recent_history(current_question=question)

        # 生成图表路径
        plot_path = self.plot_dir / f"plot_{self.session.session_id}_{turn_number}.png"

        # 带重试的代码生成和执行
        code, result, retry_count = self._generate_and_execute_with_retry(
            question=question,
            history=history,
            plot_path=str(plot_path)
        )

        if result is None:
            # 所有重试都失败了
            self.ui.show_error(
                "多次重试后仍然失败，请检查问题或数据。",
                "MaxRetriesExceeded"
            )
            return False

        # 检查是否有图表生成
        if plot_path.exists():
            result['plot_saved'] = True
            result['plot_path'] = str(plot_path)
        else:
            result['plot_saved'] = False

        # 显示执行结果
        self.ui.show_result(result)

        # 生成解释
        self.ui.show_info("正在生成分析解释...")
        try:
            explanation = self.llm.explain_result(
                question=question,
                code=code,
                result=result
            )
            self.ui.show_explanation(explanation)
        except Exception as e:
            self.logger.error(f"生成解释失败: {str(e)}")
            explanation = "（解释生成失败）"
            self.ui.show_warning("未能生成解释")

        # 保存到会话
        turn = ConversationTurn(
            timestamp=datetime.now().isoformat(),
            question=question,
            code=code,
            execution_result=result,
            explanation=explanation,
            retry_count=retry_count,
            plot_path=str(plot_path) if plot_path.exists() else None
        )
        self.session.add_turn(turn)

        # 自动保存会话
        try:
            self.session.save()
        except Exception as e:
            self.logger.warning(f"会话保存失败: {str(e)}")

        return result.get('success', False)

    def _generate_and_execute_with_retry(
        self,
        question: str,
        history: list,
        plot_path: str
    ) -> tuple:
        """
        带重试机制的代码生成和执行（支持异步thinking分析）

        Args:
            question: 用户问题
            history: 对话历史
            plot_path: 图表保存路径

        Returns:
            (code, result, retry_count) 元组
        """
        error_feedback = None
        last_code = None
        last_result = None

        df_info = self.csv.get_info()

        for attempt in range(self.max_retries):
            try:
                # 生成代码
                if attempt == 0:
                    self.ui.show_info("正在生成代码...")
                else:
                    self.ui.show_retry(attempt + 1, self.max_retries)

                code = self.llm.generate_code(
                    question=question,
                    df_info=df_info,
                    history=history,
                    error_feedback=error_feedback,
                    plot_path=plot_path
                )

                last_code = code

                # 显示代码
                self.ui.show_code(code)

                # 执行代码
                self.ui.show_executing()
                result = self.executor.execute(code)

                last_result = result

                if result['success']:
                    self.logger.info(f"执行成功 (尝试 {attempt + 1})")
                    return code, result, attempt

                # 执行失败，准备错误反馈
                self.logger.warning(
                    f"执行失败 (尝试 {attempt + 1}): "
                    f"{result.get('error_type')}"
                )

                error_feedback = {
                    'code': code,
                    'error_type': result.get('error_type', 'Unknown'),
                    'error_message': result.get('error', 'Unknown error'),
                    'traceback': result.get('traceback', '')
                }

                # 显示错误
                self.ui.show_error(
                    result.get('error', 'Unknown error'),
                    result.get('error_type', 'Error')
                )

                # 【阻塞式thinking错误分析】代码执行失败后立即分析
                if attempt == 0:  # 第一次失败时使用thinking深度分析
                    self.ui.show_info("🧠 启动深度错误分析（thinking模式）...")

                    # 阻塞式调用thinking分析
                    thinking_result = self.async_error_analyzer.analyze_error_with_thinking(
                        question=question,
                        df_info=df_info,
                        history=history,
                        error_feedback=error_feedback,
                        plot_path=plot_path
                    )

                    # 如果thinking成功生成代码，立即执行
                    if thinking_result.get('success') and thinking_result.get('code'):
                        self.logger.info("✨ thinking分析完成，执行修复代码")
                        self.ui.show_info("✨ 使用thinking深度分析结果")
                        self.ui.show_code(thinking_result['code'])

                        # 执行thinking生成的代码
                        self.ui.show_executing()
                        thinking_exec_result = self.executor.execute(thinking_result['code'])

                        if thinking_exec_result['success']:
                            self.logger.info("thinking修复成功！")
                            return thinking_result['code'], thinking_exec_result, attempt

                        # thinking修复失败，记录但继续原有重试流程
                        self.logger.warning("thinking修复的代码执行失败，继续Function Calling重试")
                        self.ui.show_error(
                            thinking_exec_result.get('error', 'thinking修复失败'),
                            thinking_exec_result.get('error_type', 'Error')
                        )
                    else:
                        self.logger.warning("thinking分析未生成有效代码，继续Function Calling重试")

            except Exception as e:
                self.logger.error(f"生成或执行过程出错: {str(e)}")
                if attempt < self.max_retries - 1:
                    self.ui.show_error(str(e), "Exception")
                    continue
                else:
                    # 最后一次也失败了
                    return last_code, last_result, attempt

        # 所有重试都失败
        return last_code, last_result, self.max_retries

    def run_interactive(self):
        """运行交互式会话"""
        self.ui.show_welcome()

        # 显示CSV信息
        csv_summary = self.csv.get_summary()
        self.ui.show_csv_info(csv_summary)

        turn_number = 1

        while True:
            try:
                # 获取用户问题
                question = self.ui.prompt_question()

                # 检查退出命令
                if question.lower() in ['exit', 'quit', 'q']:
                    break

                if not question.strip():
                    self.ui.show_warning("请输入有效的问题")
                    continue

                # 分析问题
                self.analyze_question(question, turn_number)

                turn_number += 1

            except KeyboardInterrupt:
                self.ui.print("\n[yellow]用户中断[/yellow]")
                break
            except Exception as e:
                self.logger.error(f"处理问题时出错: {str(e)}", exc_info=True)
                self.ui.show_error(str(e), "Exception")
                continue

        # 显示统计信息
        stats = self.session.get_statistics()
        self.ui.show_statistics(stats)

        # 导出报告
        try:
            report_path = self.session.export_report()
            self.ui.show_success(f"分析报告已导出: {report_path}")
        except Exception as e:
            self.logger.warning(f"报告导出失败: {str(e)}")

        self.ui.show_goodbye()
