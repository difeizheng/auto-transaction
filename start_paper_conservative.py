"""
启动稳健版 (牛市 53%) 模拟交易

配置说明:
- 信号阈值：5.5
- 止损：4%
- 止盈：35%
- 基础仓位：33%
- 牛市最大：53%
- 熊市仓位：2%
- 移动止损触发：15%
- 时间止损：10 日

预期表现 (基于回测 20240324-20260323):
- 年化收益：15.22%
- 夏普比率：0.62
- 最大回撤：14.46%
- 胜率：51.4%
- 盈亏比：2.72
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from start_services import start_paper_trading

if __name__ == '__main__':
    print("=" * 70)
    print("启动稳健版 (牛市 53%) 模拟交易")
    print("=" * 70)
    print()

    # 启动模拟交易
    # mode='conservative' 使用稳健版配置 (牛市 53%)
    start_paper_trading(
        strategy='optimal',
        capital=100000,  # 初始资金 10 万
        mode='conservative'
    )
