"""Rich终端界面"""

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich import box
from typing import Dict, Any


class RichInterface:
    """Rich美化的终端界面"""

    def __init__(self, theme: str = "monokai"):
        """
        初始化界面

        Args:
            theme: 代码高亮主题
        """
        self.console = Console()
        self.theme = theme

    def show_welcome(self):
        """显示欢迎信息"""
        welcome_text = """
[bold cyan]CSV数据分析系统[/bold cyan]
基于智谱GLM-4.6大模型

[dim]输入问题进行数据分析，输入 'exit' 或 'quit' 退出[/dim]
        """
        self.console.print(Panel.fit(
            welcome_text.strip(),
            border_style="cyan",
            box=box.DOUBLE
        ))
        self.console.print()

    def show_csv_info(self, csv_summary: str):
        """
        显示CSV数据信息

        Args:
            csv_summary: CSV摘要信息
        """
        self.console.print(Panel(
            csv_summary,
            title="[bold green]数据加载成功[/bold green]",
            border_style="green",
            box=box.ROUNDED
        ))
        self.console.print()

    def prompt_question(self) -> str:
        """
        提示用户输入问题

        Returns:
            用户输入的问题
        """
        return Prompt.ask("\n[bold yellow]❓ 请输入问题[/bold yellow]")

    def show_question(self, question: str, turn_number: int):
        """
        显示用户问题

        Args:
            question: 用户问题
            turn_number: 轮次编号
        """
        self.console.print(
            f"\n[bold cyan]━━━ 第 {turn_number} 轮分析 ━━━[/bold cyan]\n"
        )
        self.console.print(
            f"[bold green]问题:[/bold green] {question}"
        )

    def show_context_window(self, token_display: str, context_status: Dict[str, Any]):
        """
        显示上下文窗口状态

        Args:
            token_display: 格式化的token显示文本
            context_status: 上下文窗口状态字典
        """
        # 显示简洁的token信息
        self.console.print(f"[dim]{token_display}[/dim]")

        # 如果接近或超过阈值，显示警告
        if context_status.get('should_compact'):
            self.console.print(
                "[yellow]⚠️  上下文窗口接近限制，将自动压缩历史记录[/yellow]"
            )

    def show_generating(self, message: str = "正在生成代码..."):
        """
        显示生成中的状态

        Args:
            message: 提示信息
        """
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            progress.add_task(description=message, total=None)
            # 注意：实际使用时需要在外部控制进度

    def show_code(self, code: str, title: str = "生成的代码"):
        """
        显示生成的代码

        Args:
            code: Python代码
            title: 面板标题
        """
        syntax = Syntax(
            code,
            "python",
            theme=self.theme,
            line_numbers=True,
            word_wrap=False
        )

        self.console.print()
        self.console.print(Panel(
            syntax,
            title=f"[bold blue]{title}[/bold blue]",
            border_style="blue",
            box=box.ROUNDED
        ))

    def show_executing(self):
        """显示执行中状态"""
        self.console.print("[yellow]⚙️  执行代码中...[/yellow]")

    def show_result(self, result: Dict[str, Any]):
        """
        显示执行结果

        Args:
            result: 执行结果字典
        """
        if result['success']:
            stdout = result.get('stdout', '').strip()

            if stdout:
                self.console.print()
                self.console.print(Panel(
                    stdout,
                    title="[bold green]执行结果[/bold green]",
                    border_style="green",
                    box=box.ROUNDED
                ))

            # 检查是否有图表
            if result.get('plot_saved'):
                self.console.print(
                    f"[green]📊 图表已保存: {result['plot_path']}[/green]"
                )
        else:
            # 显示错误
            self.show_error(
                result.get('error', 'Unknown error'),
                result.get('error_type', 'Error')
            )

    def show_explanation(self, explanation: str, max_display_chars: int = None):
        """
        显示LLM解释（优化版，支持长文本）

        Args:
            explanation: 解释文本
            max_display_chars: 最大显示字符数（None表示不限制）
        """
        md = Markdown(explanation)

        # 计算字符数
        char_count = len(explanation)

        # 构建标题（包含字符数）
        title = f"[bold cyan]分析解释[/bold cyan] [dim]({char_count} 字符)[/dim]"

        # 如果内容很长，添加提示
        if max_display_chars and char_count > max_display_chars:
            # 显示截断提示（但实际显示完整内容）
            title += " [yellow]⚠️ 内容较长，建议查看完整输出[/yellow]"

        self.console.print()
        self.console.print(Panel(
            md,
            title=title,
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2)  # 增加内边距，使内容更易读
        ))

        # 如果内容超长，显示滚动提示
        if char_count > 1000:
            self.console.print(
                "[dim]💡 提示: 内容较长，可以向上滚动查看完整分析[/dim]",
                style="dim cyan"
            )

    def show_error(self, error: str, error_type: str = "Error"):
        """
        显示错误信息

        Args:
            error: 错误信息
            error_type: 错误类型
        """
        self.console.print()
        self.console.print(Panel(
            f"[red][bold]{error_type}:[/bold] {error}[/red]",
            title="[bold red]执行失败[/bold red]",
            border_style="red",
            box=box.ROUNDED
        ))

    def show_retry(self, attempt: int, max_retries: int):
        """
        显示重试信息

        Args:
            attempt: 当前尝试次数
            max_retries: 最大重试次数
        """
        self.console.print(
            f"\n[yellow]🔄 重试中 ({attempt}/{max_retries})...[/yellow]"
        )

    def show_info(self, message: str):
        """
        显示信息

        Args:
            message: 信息内容
        """
        self.console.print(f"[cyan]ℹ️  {message}[/cyan]")

    def show_warning(self, message: str):
        """
        显示警告

        Args:
            message: 警告内容
        """
        self.console.print(f"[yellow]⚠️  {message}[/yellow]")

    def show_success(self, message: str):
        """
        显示成功信息

        Args:
            message: 成功信息
        """
        self.console.print(f"[green]✓ {message}[/green]")

    def show_statistics(self, stats: Dict[str, Any]):
        """
        显示会话统计信息

        Args:
            stats: 统计信息字典
        """
        table = Table(title="会话统计", box=box.ROUNDED)
        table.add_column("项目", style="cyan", justify="left")
        table.add_column("数值", style="green", justify="right")

        for key, value in stats.items():
            table.add_row(key, str(value))

        self.console.print()
        self.console.print(table)

    def show_goodbye(self):
        """显示退出信息"""
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]感谢使用CSV数据分析系统！[/bold cyan]",
            border_style="cyan"
        ))

    def clear(self):
        """清空终端"""
        self.console.clear()

    def print(self, *args, **kwargs):
        """直接打印（代理到console）"""
        self.console.print(*args, **kwargs)
