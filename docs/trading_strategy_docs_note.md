# `trading_strategy.md`、`trading_strategy_backtest.md` 与 `trading_strategy_research_backtest.md` 的差异说明

## 一、目的

仓库中目前有三份关于交易策略的文档：

- [trading_strategy.md](/root/shaopf/stock-backtest/docs/trading_strategy.md)
- [trading_strategy_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_backtest.md)
- [trading_strategy_research_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_research_backtest.md)

它们不是重复文件，而是承担不同职责。

## 二、三份文档各自负责什么

### 1. `trading_strategy.md`

这是一份：

- 手册版
- 思想版
- 执行框架版

它负责回答的问题是：

- 这套策略整体在做什么
- 作者的投资世界观是什么
- 如何理解选股、持有、调仓、回撤、资产配置
- 哪些原则是长期反复强调的

它更适合：

- 人阅读
- 建立整体理解
- 做投资方法论梳理
- 作为研究笔记或策略手册使用

### 2. `trading_strategy_backtest.md`

这是一份：

- 回测版
- 原文校对版
- 规则摘录版

它负责回答的问题是：

- 作者原文里到底明确写出了哪些规则
- 哪些阈值、公式、参数可以直接量化
- 哪些内容只是边界、例外、分支、变体
- 哪些东西不能混进主体系

它更适合：

- 程序化实现前的规则确认
- 回测参数设计
- 原文出处核对
- 避免把作者没说过的话误写成规则

### 3. `trading_strategy_research_backtest.md`

这是一份：

- 研究版
- 可执行版
- 量化近似版

它负责回答的问题是：

- 如果原文条件无法完整拿到，怎样重写成一套能回测的规则
- 哪些原文条件需要用代理变量替代
- 如何把模糊理念落成工程上闭合的系统

它更适合：

- 真正落地代码
- 迭代参数
- 跑研究回测
- 区分“原文规则”和“研究假设”

## 三、哪些内容只该出现在回测版

以下内容更适合放在 `trading_strategy_backtest.md` 中：

- 明确的数值阈值
- 明确的买入/卖出/换股条件
- 明确的参数来源
- 原文出处说明
- “该规则来自哪篇文章”的校对信息
- 互相可能冲突的原文补丁
- 哪些规则属于另一套体系，不能混用

例如：

- `PEG < 1.2`
- `g > 10%`
- `目标预估收益率 > 35%`
- `卖出预估收益率 <= 0%`
- `组合 20 只`
- `行业 10 个`
- `三年不盈利离场`
- `预备队 10% ~ 20%`
- `20% 止盈 + 8% 止损` 属于另一套早期系统

这些内容如果大量塞进手册版，会让手册版变得像审计记录，不利于阅读。

## 四、哪些内容只该出现在研究版

以下内容更适合放在 `trading_strategy_research_backtest.md` 中：

- 可运行的替代规则
- 难以获取数据时的代理变量定义
- 估值分位卖出线
- 排序打分公式
- 回测工程口径
- 参数分层与默认值

例如：

- `PE > 历史80%分位` 作为减仓线
- `PE > 历史95%分位` 作为极端高估清仓线
- 用历史利润增速代理 `g`
- 用排序得分差代理换股收益差

这些内容不应误写为作者原话，因此更适合放在研究版。

## 五、哪些内容只该出现在手册版

以下内容更适合放在 `trading_strategy.md` 中：

- 策略的整体目标
- 作者的投资哲学
- 对优质股、回撤、长期持有、空仓、调仓的理解
- 对行业偏好与公司质地的高层描述
- 对资产配置分支的理解性总结
- 对“为什么这么做”的解释

例如：

- 为什么净资产增厚很重要
- 为什么优质股不宜轻易空仓
- 为什么组合中的调整股反而是金疙瘩
- 为什么不能混用趋势止损和价值持有
- 为什么要顺应人性、顺应长期需求

这些内容如果全部硬塞进回测版，会让回测版失去“可校对、可摘规则”的作用。

## 六、三份文档的关系

最简单的理解方式是：

- `trading_strategy.md` 负责讲“道”
- `trading_strategy_backtest.md` 负责讲“原文规则”
- `trading_strategy_research_backtest.md` 负责讲“可执行近似”

或者说：

- 手册版负责讲“为什么”
- 回测版负责讲“原文到底写了什么”

三者关系不是并列重复，而是：

- 手册版在上层
- 原文回测版负责校对
- 研究回测版负责落地

## 七、使用建议

### 1. 如果你想理解这套策略

先读：

- [trading_strategy.md](/root/shaopf/stock-backtest/docs/trading_strategy.md)

### 2. 如果你想把它做成程序或回测

先读：

- [trading_strategy_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_backtest.md)

再回头结合：

- [trading_strategy.md](/root/shaopf/stock-backtest/docs/trading_strategy.md)

### 3. 如果你想真正开始写代码和跑回测

优先读：

- [trading_strategy_research_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_research_backtest.md)

必要时再对照：

- [trading_strategy_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_backtest.md)

### 4. 如果几份文档看起来有差异

优先按以下原则理解：

1. 回测版优先负责“原文精确性”
2. 研究版优先负责“系统可执行性”
3. 手册版优先负责“整体可读性”
4. 手册版若比回测版更概括，不一定代表冲突
5. 若必须确定“作者是否明确说过某条规则”，以原文回测版为准

## 八、后续维护原则

以后若继续补充原文材料，建议遵守以下规则：

1. 新发现的明确原文数值规则，先补到 `trading_strategy_backtest.md`
2. 新增的量化替代方案，补到 `trading_strategy_research_backtest.md`
3. 新发现的高层逻辑或长期偏好，再整理进 `trading_strategy.md`
4. 若只是情绪性时评、没有新增规则，不必强行写入
5. 若属于另一套策略分支，要单独标注，避免混入主体系

## 九、结论

这三份文档分别服务于不同目标：

- [trading_strategy.md](/root/shaopf/stock-backtest/docs/trading_strategy.md) 用来理解策略
- [trading_strategy_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_backtest.md) 用来校对原文
- [trading_strategy_research_backtest.md](/root/shaopf/stock-backtest/docs/trading_strategy_research_backtest.md) 用来落地回测

最稳妥的使用方式是：

> 先用手册版建立整体认知，再用原文回测版校对边界，最后用研究回测版落地代码，避免把作者未明确写出的内容误当成硬规则，也避免因为拘泥原文而无法回测。
