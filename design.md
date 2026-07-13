# 股票缓存与收益率绘图说明

## 1. 项目范围

当前仓库只保留两个功能：

1. 读取 [stock_pool_27.csv](stock_pool_27.csv) 中的 `ts_code`，把 Tushare 数据缓存到本地
2. 基于本地缓存，绘制单只股票的历史三年年化收益率走势图

仓库中原有的回测、调仓、持仓分析相关代码已移除。

## 2. 运行环境

默认使用 `conda` 环境 `stock`。

```bash
conda run -n stock python prefetch_cache.py --help
conda run -n stock python plot_expected_return.py --help
```

## 3. 缓存命令

```bash
conda run -n stock python prefetch_cache.py \
  --stock-pool-file stock_pool_27.csv \
  --cache-dir artifacts/tushare_cache
```

说明：

- 会缓存 `trade_cal`、`daily`、`daily_basic`、`report_rc`、`fina_indicator`、`dividend`
- `--refresh-datasets` 可按数据集名强制重拉，例如 `report_rc,daily_basic`
- 默认从 `TUSHARE_TOKEN` 环境变量读取 token

## 4. 绘图命令

```bash
conda run -n stock python plot_expected_return.py \
  --ts-code 600519.SH \
  --start-date 20150630 \
  --cache-dir artifacts/tushare_cache
```

默认输出：

```text
artifacts/expected_return_<ts_code>.png
```

图中包含：

- 三年均值回归年化收益率
- 卖方三年 CAGR
- 期望三年年化收益率
- 股价副轴

## 5. 测试

```bash
conda run -n stock python -m unittest discover -s tests -p 'test_*.py'
```
