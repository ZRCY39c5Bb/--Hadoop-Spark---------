from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lag, avg, stddev as stddev_agg, exp, log, min as spark_min, max as spark_max
from pyspark.sql.window import Window

spark = SparkSession.builder \
    .appName("Backtest") \
    .master("spark://master:7077") \
    .config("spark.executor.memory", "512m") \
    .config("spark.driver.memory", "512m") \
    .config("spark.executor.memoryOverhead", "64m") \
    .config("spark.driver.memoryOverhead", "64m") \
    .config("spark.sql.shuffle.partitions", "200") \
    .getOrCreate()

# ==================== 1. 读取数据 ====================
df_stock = spark.read.parquet("hdfs://master:9000/user/quant/clean/stock_clean.parquet")
df_selected = spark.read.parquet("hdfs://master:9000/user/quant/selected_stocks/")

# ==================== 2. 计算个股日收益率 ====================
win_stock = Window.partitionBy("ts_code").orderBy("trade_date")
df_stock = df_stock.withColumn(
    "ret", (col("close") - lag("close", 1).over(win_stock)) / lag("close", 1).over(win_stock)
)

# ==================== 3. 关联持仓 → 组合日收益 ====================
df_port = df_selected.join(df_stock, on=["ts_code", "trade_date"], how="inner")

# 等权组合：每天持仓股票的平均收益率
df_daily = df_port.groupBy("trade_date").agg(avg("ret").alias("port_ret"))

# ==================== 4. 计算累计净值 ====================
win_time = Window.orderBy("trade_date")
df_nav = df_daily.withColumn(
    "cum_ret", exp(avg(log(1 + col("port_ret"))).over(win_time.rowsBetween(Window.unboundedPreceding, 0)))
).withColumn("port_nav", col("cum_ret"))  # 简化：初始净值=1

# ==================== 5. 计算评价指标 ====================
df_nav.createOrReplaceTempView("nav_table")

metrics = spark.sql("""
    SELECT
        AVG(port_ret) * 252                          AS annual_return,
        STDDEV(port_ret) * SQRT(252)                 AS annual_vol,
        (AVG(port_ret) * 252 - 0.025) /
        (STDDEV(port_ret) * SQRT(252))               AS sharpe,
        MAX(port_nav)                                AS max_nav,
        MIN(port_nav)                                AS min_nav
    FROM nav_table
""")

print("=" * 60)
print("                    回测评价指标")
print("=" * 60)
metrics.show()

# 最大回撤计算（简化版）
from pyspark.sql.functions import row_number as rn
w2 = Window.orderBy("trade_date")
nav_with_idx = df_nav.withColumn("idx", rn().over(w2))

max_row = metrics.collect()[0]
max_nav_val = max_row["max_nav"]
min_nav_val = max_row["min_nav"]
if max_nav_val and min_nav_val:
    mdd = (max_nav_val - min_nav_val) / max_nav_val
    print(f"\n最大回撤: {mdd:.4f} ({mdd*100:.2f}%)")

# ==================== 6. 保存净值曲线 ====================
df_nav.select("trade_date", "port_ret", "port_nav") \
    .coalesce(1).write.mode("overwrite").option("header", "true") \
    .csv("hdfs://master:9000/user/quant/output/nav_curve/")

# ==================== 7. 导出最新一期持仓 ====================
from pyspark.sql.functions import max as spark_max_date
max_date_row = df_selected.agg(spark_max_date("trade_date")).collect()[0][0]
print(f"\n最新调仓日期: {max_date_row}")

latest = df_selected.filter(col("trade_date") == max_date_row) \
    .orderBy("rank") \
    .select("trade_date", "ts_code", "total_score", "rank")
print("\n最新持仓前10:")
latest.show(10, truncate=False)

latest.coalesce(1).write.mode("overwrite").option("header", "true") \
    .csv("hdfs://master:9000/user/quant/output/latest_holding/")

print("\n回测完成！")
spark.stop()
