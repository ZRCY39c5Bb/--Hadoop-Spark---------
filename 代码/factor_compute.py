# factor_compute.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lag, stddev, when, sum as F_sum, lit
from pyspark.sql.window import Window

spark = SparkSession.builder \
    .appName("FactorCompute") \
    .master("spark://master:7077") \
    .config("spark.executor.memory", "512m") \
    .config("spark.driver.memory", "512m") \
    .config("spark.executor.memoryOverhead", "64m") \
    .config("spark.driver.memoryOverhead", "64m") \
    .config("spark.sql.shuffle.partitions", "200") \
    .getOrCreate()

# 读取清洗后数据
df = spark.read.parquet("hdfs://master:9000/user/quant/clean/stock_clean.parquet")

# ==================== 窗口定义 ====================
# 按股票分组，按日期排序的窗口（用于lag操作）
win_order = Window.partitionBy("ts_code").orderBy("trade_date")
# 前20个交易日窗口（不含当天）
win_20 = Window.partitionBy("ts_code").orderBy("trade_date").rowsBetween(-20, -1)
# 前60个交易日窗口（不含当天）
win_60 = Window.partitionBy("ts_code").orderBy("trade_date").rowsBetween(-60, -1)
# 前14个交易日窗口（不含当天，用于RSI）
win_14 = Window.partitionBy("ts_code").orderBy("trade_date").rowsBetween(-14, -1)

# ==================== 1. RET_1M: 20日动量 ====================
df = df.withColumn("close_20d_ago", lag("close", 20).over(win_order))
df = df.withColumn("RET_1M", (col("close") - col("close_20d_ago")) / col("close_20d_ago"))

# ==================== 2. VOL_20: 20日波动率 ====================
df = df.withColumn("VOL_20", stddev("close").over(win_20))

# ==================== 3. RET_3M: 60日动量 ====================
df = df.withColumn("close_60d_ago", lag("close", 60).over(win_order))
df = df.withColumn("RET_3M", (col("close") - col("close_60d_ago")) / col("close_60d_ago"))

# ==================== 4. RSI: 14日相对强弱指标 ====================
df = df.withColumn("delta", col("close") - lag("close", 1).over(win_order))
df = df.withColumn("gain", when(col("delta") > 0, col("delta")).otherwise(0))
df = df.withColumn("loss", when(col("delta") < 0, -col("delta")).otherwise(0))

avg_gain = F_sum("gain").over(win_14) / 14
avg_loss = F_sum("loss").over(win_14) / 14
df = df.withColumn("RSI", 100 - 100 / (1 + avg_gain / avg_loss))

# ==================== 5. ROE_TTM: 模拟财务因子（实际需join财报）====================
df = df.withColumn("ROE_TTM", lit(0.12))

# ==================== 6. EP: E/P 估值因子（模拟EPS=0.5元）====================
df = df.withColumn("EP", lit(0.5) / col("close"))

# ==================== 筛选因子列 ====================
factor_cols = ["ts_code", "trade_date", "RET_1M", "VOL_20", "RET_3M", "RSI", "ROE_TTM", "EP"]
df_factors = df.select(*factor_cols)

# 保存为 Parquet
df_factors.write.mode("overwrite").parquet("hdfs://master:9000/user/quant/factors/")

print(f"因子记录数: {df_factors.count()}")
print("因子计算完成！")
spark.stop()
