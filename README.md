# stock-backtest

当前仓库只保留两个功能：

1. 读取股票池配置并把所需 Tushare 数据缓存到本地
2. 基于本地缓存，按股票池逐只绘制历史三年年化收益率走势图

常用命令：

```bash
cp config.local.example.json config.local.json
python3 prefetch_cache.py
python3 plot_expected_return.py
```

会在输出目录中同时生成每只股票的 PNG，以及一个汇总结果文件 `expected_return_summary.csv`。

更多说明见 [design.md](design.md)。
