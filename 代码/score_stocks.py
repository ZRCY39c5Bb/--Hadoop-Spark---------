# score_stocks.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, mean, stddev, row_number
from pyspark.sql.window import Window

spark = SparkSession.builder \
    .appName("StockSelection") \
    .master("spark://master:7077") \
    .config("spark.executor.memory", "512m") \
    .config("spark.driver.memory", "512m") \
    .config("spark.executor.memoryOverhead", "64m") \
    .config("spark.driver.memoryOverhead", "64m") \
    .config("spark.sql.shuffle.partitions", "200") \
    .getOrCreate()

df = spark.read.parquet("hdfs://master:9000/user/quant/factors/")

# ==================== Z-Score 标准化（按截面） ====================
def zscore(df, col_name):
    """在每个交易日截面上做 Z-Score 标准化"""
    win = Window.partitionBy("trade_date")
    mean_val = mean(col(col_name)).over(win)
    std_val = stddev(col(col_name)).over(win)
    return df.withColumn(f"{col_name}_z", (col(col_name) - mean_val) / std_val)

for f in ["RET_1M", "VOL_20", "RET_3M", "RSI", "ROE_TTM", "EP"]:
    df = zscore(df, f)

# ==================== 方向处理与打分 ====================
# RET_1M（动量↑好）、RET_3M（动量↑好）、ROE_TTM（盈利↑好）、EP（估值↑好）→ 正向
# VOL_20（波动↓好）、RSI（过高→反转↓好）→ 负向

df = df.withColumn("score_RET_1M",  col("RET_1M_z")) \
       .withColumn("score_RET_3M",  col("RET_3M_z")) \
       .withColumn("score_ROE_TTM", col("ROE_TTM_z")) \
       .withColumn("score_EP",      col("EP_z")) \
       .withColumn("score_VOL_20", -col("VOL_20_z")) \
       .withColumn("score_RSI",    -col("RSI_z"))

# 等权合成
score_cols = ["score_RET_1M", "score_RET_3M", "score_ROE_TTM",
              "score_EP", "score_VOL_20", "score_RSI"]
df = df.withColumn("total_score",
                   (col(score_cols[0]) + col(score_cols[1]) + col(score_cols[2]) +
                    col(score_cols[3]) + col(score_cols[4]) + col(score_cols[5])) / 6)

# ==================== 每期选前30名 ====================
win_rank = Window.partitionBy("trade_date").orderBy(col("total_score").desc())
df_selected = df.withColumn("rank", row_number().over(win_rank)) \
                .filter(col("rank") <= 30) \
                .select("trade_date", "ts_code", "total_score", "rank")

df_selected.write.mode("overwrite").parquet(
    "hdfs://master:9000/user/quant/selected_stocks/"
)
print(f"选股结果行数: {df_selected.count()}")
print("选股完成！")
spark.stop()
