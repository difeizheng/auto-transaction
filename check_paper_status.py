"""
模拟盘状态查看脚本
用于快速查看模拟盘运行状态和日志
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
LOG_FILE = PROJECT_ROOT / "logs" / "trader.log"
OUTPUT_FILE = Path.home() / ".claude" / "tasks" / "bbv3na2k4.output"


def check_process():
    """检查进程状态"""
    print("=" * 60)
    print("模拟盘进程状态")
    print("=" * 60)

    try:
        result = subprocess.run(
            ["tasklist"],
            capture_output=True,
            text=True,
            encoding='gbk'
        )

        python_processes = [
            line for line in result.stdout.split('\n')
            if 'python.exe' in line.lower()
        ]

        if python_processes:
            print(f"运行中的 Python 进程: {len(python_processes)}")
            for proc in python_processes:
                print(f"  {proc.strip()}")
        else:
            print("未找到运行中的 Python 进程")

    except Exception as e:
        print(f"检查进程失败：{e}")

    print()


def check_recent_logs():
    """查看最近日志"""
    print("=" * 60)
    print("最近日志 (最后 20 条)")
    print("=" * 60)

    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[-20:]:
                    print(line.strip())
        except Exception as e:
            print(f"读取日志失败：{e}")
    else:
        print("日志文件不存在")

    print()


def check_background_output():
    """查看后台输出"""
    print("=" * 60)
    print("后台运行输出 (最后 30 条)")
    print("=" * 60)

    # 查找最新的输出文件
    output_dir = Path.home() / ".claude" / "projects" / "D--project-room-workspace2024-mytest-auto-transaction" / "52c304b5-9120-4061-aae9-2f481f0c9c04" / "tasks"

    if output_dir.exists():
        output_files = list(output_dir.glob("*.output"))
        if output_files:
            # 找到最新的文件
            latest_file = max(output_files, key=lambda x: x.stat().st_mtime)
            print(f"输出文件：{latest_file}")
            print("-" * 60)

            try:
                with open(latest_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines[-30:]:
                        # 清理行号前缀
                        if '→' in line:
                            line = line.split('→', 1)[1]
                        print(line.strip())
            except Exception as e:
                print(f"读取输出文件失败：{e}")
    else:
        print("输出目录不存在")

    print()


def main():
    """主函数"""
    print()
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 20 + "模拟盘运行状态" + " " * 20 + "║")
    print("║" + " " * 15 + f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    check_process()
    check_background_output()
    check_recent_logs()

    print("=" * 60)
    print("提示:")
    print("  - 查看完整日志：cat logs/trader.log")
    print("  - 重启服务：python run_paper_trading.py")
    print("  - 停止服务：taskkill /F /PID <进程 ID>")
    print("=" * 60)


if __name__ == "__main__":
    main()
