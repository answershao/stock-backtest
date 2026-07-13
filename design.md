# 股票缓存与收益率绘图说明

## 1. 项目范围

当前仓库只保留两个功能：

1. 读取本地配置中的股票池，把 Tushare 数据缓存到本地
2. 基于本地缓存，按股票池逐只绘制历史三年年化收益率走势图

仓库中原有的回测、调仓、持仓分析相关代码已移除。

## 2. 运行环境

默认使用 `conda` 环境 `stock`。

```bash
conda run -n stock python prefetch_cache.py --help
conda run -n stock python plot_expected_return.py --help
```

## 3. 缓存命令

```bash
cp config.local.example.json config.local.json
python3 prefetch_cache.py
```

说明：

- `config.local.json` 可同时放 `token` 和 `stock_pool`，并且不会参与 git 提交
- 只要参数已在 `config.local.json` 定义，运行时就可以不再从命令行传入
- 会缓存 `trade_cal`、`daily`、`daily_basic`、`report_rc`、`fina_indicator`、`dividend`
- `--refresh-datasets` 可按数据集名强制重拉，例如 `report_rc,daily_basic`
- 缓存默认更新到运行当天；`token` 默认优先读取本地配置，其次读取 `TUSHARE_TOKEN` 环境变量

## 4. 绘图命令

```bash
python3 plot_expected_return.py
```

默认输出：

```text
artifacts/expected_return/expected_return_<ts_code>.png
artifacts/expected_return/expected_return_summary.csv
```

补充说明：

- 如果 `config.local.json` 通过 `stock_pool_file` 指向的 CSV 同时带有 `name` 列，汇总 CSV 和 PNG 标题会优先带上中文名称

图中包含：

- 三年均值回归年化收益率
- 卖方三年 CAGR
- 期望三年年化收益率
- 股价副轴

## 5. 测试

```bash
conda run -n stock python -m unittest discover -s tests -p 'test_*.py'
```
