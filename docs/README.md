# 文档索引

本目录存放当前项目中与交易策略整理相关的正式文档。

## 文件说明

- [trading_strategy.md](/root/shaopf/stock-backtest/docs/trading_strategy.md)
  说明：
  手册版。用于理解策略整体框架、作者的投资思想、持有与调仓逻辑、行业偏好与资产配置思路。

- [trading_strategy_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_backtest.md)
  说明：
  回测版。用于提取原文中明确写出的参数、阈值、买卖规则、边界条件和分支体系，作为程序化实现前的约束文档。

- [trading_strategy_research_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_research_backtest.md)
  说明：
  研究回测设计文档。用于在无法完整复现原文条件时，使用可量化代理变量定义一套能实际回测的系统设计。

- [trading_strategy_docs_note.md](/root/shaopf/stock-backtest/docs/trading_strategy_docs_note.md)
  说明：
  差异说明。用于解释手册版、原文回测版、研究回测版各自负责什么，以及哪些内容只适合出现在对应文档里。

## 使用建议

1. 想先理解这套策略，先读 [trading_strategy.md](/root/shaopf/stock-backtest/docs/trading_strategy.md)
2. 想做程序化实现或回测，先读 [trading_strategy_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_backtest.md)
3. 想直接落地一个研究版回测系统，读 [trading_strategy_research_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_research_backtest.md)
4. 想确认几份文档为何分开维护，读 [trading_strategy_docs_note.md](/root/shaopf/stock-backtest/docs/trading_strategy_docs_note.md)

## 兼容说明

仓库根目录保留了同名跳转文件：

- [../trading_strategy.md](/root/shaopf/stock-backtest/trading_strategy.md)
- [../trading_strategy_backtest.md](/root/shaopf/stock-backtest/trading_strategy_backtest.md)
- [../trading_strategy_docs_note.md](/root/shaopf/stock-backtest/trading_strategy_docs_note.md)

它们的作用是兼容旧路径与现有编辑器标签页，正式内容以 `docs/` 下的文件为准。
