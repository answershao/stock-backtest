# stock-backtest

当前仓库只保留两个功能：

1. 读取 [stock_pool_27.csv](stock_pool_27.csv) 并把所需 Tushare 数据缓存到本地
2. 基于本地缓存，绘制单只股票的历史三年年化收益率走势图

常用命令：

```bash
conda run -n stock python prefetch_cache.py --stock-pool-file stock_pool_27.csv
conda run -n stock python plot_expected_return.py --ts-code 600519.SH
```

更多说明见 [design.md](design.md)。
