# stock-backtest

一个面向 A 股组合回测的轻量项目，当前支持：

- 自定义股票池与回测区间
- 定期调仓
- 现金分红 / 分红再投资
- 基准指数对比
- 图表与结果导出

## 目录结构

```text
stock-backtest/
├── main.py
├── src/
│   ├── app.py
│   ├── backtest.py
│   ├── config.py
│   ├── data.py
│   ├── metrics.py
│   ├── plot.py
│   └── reporting.py
├── tests/
│   ├── helpers.py
│   └── test_backtest.py
└── requirements.txt
```

## 模块分工

- `main.py`: 根目录兼容入口，方便直接运行
- `src/app.py`: 应用主入口，负责配置、数据加载、执行、结果导出
- `src/backtest.py`: 回测主流程、交易规则和核心数据结构
- `src/data.py`: Tushare 数据获取与缓存
- `src/metrics.py`: 绩效指标计算
- `src/plot.py`: 图表输出
- `src/reporting.py`: CSV 和文本报告导出
- `tests/`: 单元测试与测试夹具

## 运行方式

安装依赖：

```bash
pip install -r requirements.txt
```

直接运行项目：

```bash
python3 main.py
```

如果你想直接按模块方式运行：

```bash
python3 -m src.app
```

## 参数入口

常用可修改参数集中在：

- `src/stock_backtest/app.py`
- `src/app.py`

重点包括：

- 回测开始/结束日期
- 股票池
- 单只股票目标权重会按股票池数量自动计算，默认等权，合计为 1
- 初始资金
- 调仓计划
- 分红模式
- 手续费与税费
- 基准指数

## 测试

运行全部测试：

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```

如果按 `src` 包方式执行测试：

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```

## 输出结果

回测完成后会在 `output/` 下生成时间戳目录，包含：

- `daily_records.csv`
- `holdings.csv`
- `rebalance_weights.csv`
- `rebalance_summary.csv`
- `metrics.txt`
- `nav_curve.png`
- `drawdown_curve.png`
- `annual_returns.png`
- `holdings_heatmap.png`
