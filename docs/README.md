# 文档索引

本目录存放当前项目中与交易策略整理相关的正式文档。

## 文件说明

- [trading_strategy.md](/root/shaopf/stock-backtest/docs/trading_strategy.md)
  说明：
  手册版。用于理解策略整体框架、作者的投资思想、持有与调仓逻辑、行业偏好与资产配置思路。

- [trading_strategy_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_backtest.md)
  说明：
  回测版。用于提取原文中明确写出的参数、阈值、买卖规则、边界条件和分支体系，作为程序化实现前的约束文档。

- [trading_strategy_docs_note.md](/root/shaopf/stock-backtest/docs/trading_strategy_docs_note.md)
  说明：
  差异说明。用于解释手册版和回测版各自负责什么、哪些内容只适合出现在其中一份文档里。

## 使用建议

1. 想先理解这套策略，先读 [trading_strategy.md](/root/shaopf/stock-backtest/docs/trading_strategy.md)
2. 想做程序化实现或回测，先读 [trading_strategy_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_backtest.md)
3. 想确认两份文档为何分开维护，读 [trading_strategy_docs_note.md](/root/shaopf/stock-backtest/docs/trading_strategy_docs_note.md)

## 兼容说明

仓库根目录保留了同名跳转文件：

- [../trading_strategy.md](/root/shaopf/stock-backtest/trading_strategy.md)
- [../trading_strategy_backtest.md](/root/shaopf/stock-backtest/trading_strategy_backtest.md)
- [../trading_strategy_docs_note.md](/root/shaopf/stock-backtest/trading_strategy_docs_note.md)

它们的作用是兼容旧路径与现有编辑器标签页，正式内容以 `docs/` 下的文件为准。

