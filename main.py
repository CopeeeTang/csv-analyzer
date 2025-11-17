#!/usr/bin/env python3
"""
CSV数据分析系统 - 主入口

基于智谱GLM-4.6大模型的CSV数据分析工具
"""

import sys
import argparse
import logging
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.utils import load_config, setup_logger, get_api_key
from src.llm import GLMClient
from src.core import CodeExecutor, SessionManager, CSVHandler, get_global_context
from src.core.workflow import AnalysisWorkflow
from src.core.compactor import ConversationCompactor
from src.cli import RichInterface


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="CSV数据分析系统 - 基于智谱GLM-4.6大模型"
    )

    parser.add_argument(
        'csv_file',
        type=str,
        help='CSV文件路径'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config/config.yaml',
        help='配置文件路径 (默认: config/config.yaml)'
    )

    parser.add_argument(
        '--session-id',
        type=str,
        default=None,
        help='会话ID (默认: 自动生成)'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        default=None,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别'
    )

    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()

    # 加载配置
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"错误: 配置文件不存在: {args.config}")
        sys.exit(1)
    except Exception as e:
        print(f"错误: 加载配置失败: {str(e)}")
        sys.exit(1)

    # 设置日志
    log_level = args.log_level or config.get('logging.level', 'INFO')
    log_file = config.get('logging.file', 'logs/app.log')
    logger = setup_logger(
        name='csv_analyzer',
        level=log_level,
        log_file=log_file
    )

    logger.info("=" * 60)
    logger.info("CSV数据分析系统启动")
    logger.info("=" * 60)

    # 初始化界面
    ui = RichInterface(theme=config.get('ui.theme', 'monokai'))

    try:
        # 获取API密钥
        try:
            api_key = get_api_key()
        except ValueError as e:
            ui.show_error(str(e), "ConfigError")
            sys.exit(1)

        # 初始化LLM客户端
        logger.info("初始化LLM客户端...")
        llm_client = GLMClient(
            api_key=api_key,
            model=config.get('llm.model', 'glm-4-plus'),
            temperature=config.get('llm.temperature', 0.1),
            max_tokens=config.get('llm.max_tokens', 2000),
            explanation_max_tokens=config.get('llm.explanation_max_tokens', 4000),
            top_p=config.get('llm.top_p', 0.7)
        )

        # 测试连接
        ui.show_info("测试API连接...")
        if not llm_client.test_connection():
            ui.show_error("API连接失败，请检查API密钥和网络", "ConnectionError")
            sys.exit(1)
        ui.show_success("API连接成功")

        # 加载CSV文件
        logger.info(f"加载CSV文件: {args.csv_file}")
        csv_handler = CSVHandler()

        try:
            csv_handler.load(args.csv_file)
        except FileNotFoundError:
            ui.show_error(f"文件不存在: {args.csv_file}", "FileNotFoundError")
            sys.exit(1)
        except Exception as e:
            ui.show_error(f"加载CSV失败: {str(e)}", "LoadError")
            sys.exit(1)

        if not csv_handler.validate():
            ui.show_error("CSV数据无效或为空", "ValidationError")
            sys.exit(1)

        # 初始化全局上下文（DataFrame元数据）
        global_ctx = get_global_context()
        df_info = csv_handler.get_info()
        global_ctx.set_dataframe_metadata(df_info, args.csv_file)

        # 设置Sandbox配置说明
        sandbox_config = """
【Sandbox执行环境】
✓ 已预加载：pd, np, plt, sns, datetime, timedelta, math
✓ 可用类型：float, int, str, bool, list, dict, tuple, set
✓ 可用函数：print, len, range, sum, max, min, abs, round, sorted, enumerate, zip, isinstance, type等
✗ 禁止：任何import语句、文件操作、系统调用
"""
        global_ctx.set_sandbox_config(sandbox_config)

        logger.info("全局上下文已初始化")

        # 初始化代码执行器
        logger.info("初始化代码执行器...")
        executor = CodeExecutor(
            timeout=config.get('executor.timeout', 30),
            allowed_modules=config.get('executor.allowed_modules', [])
        )
        executor.set_dataframe(csv_handler.df)

        # 初始化会话管理器（带智能压缩）
        enable_compression = config.get('session.enable_smart_compression', True)
        session_manager = SessionManager(
            session_id=args.session_id,
            save_dir=config.get('session.save_dir', 'output/sessions'),
            enable_smart_compression=enable_compression,
            compression_threshold=config.get('session.compression_threshold', 0.7)
        )
        session_manager.csv_path = args.csv_file

        # 设置智能压缩器（可选）
        if enable_compression:
            compactor = ConversationCompactor(
                llm_client=llm_client,
                compression_threshold=config.get('session.compression_threshold', 0.7),
                keep_recent=config.get('session.context_window', 3)
            )
            session_manager.set_compactor(compactor)
            logger.info("智能压缩器已配置")

        # 创建工作流
        workflow = AnalysisWorkflow(
            llm_client=llm_client,
            csv_handler=csv_handler,
            executor=executor,
            session_manager=session_manager,
            interface=ui,
            max_retries=config.get('executor.max_retries', 3),
            plot_dir='output/plots'
        )

        # 运行交互式会话
        workflow.run_interactive()

        logger.info("会话结束")

    except KeyboardInterrupt:
        ui.print("\n[yellow]程序被用户中断[/yellow]")
        logger.info("程序被用户中断")
        sys.exit(0)

    except Exception as e:
        logger.error(f"程序异常: {str(e)}", exc_info=True)
        ui.show_error(f"程序异常: {str(e)}", "FatalError")
        sys.exit(1)


if __name__ == '__main__':
    main()
