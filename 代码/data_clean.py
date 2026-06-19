from pyspark.sql import SparkSession
from pyspark.sql.functions import col, last, when, to_date, row_number
from pyspark.sql.window import Window

spark = SparkSession.builder \
    .appName("DataClean") \
    .master("spark://master:7077") \
    .config("spark.executor.memory", "512m") \
    .config("spark.driver.memory", "512m") \
    .config("spark.executor.memoryOverhead", "64m") \
    .config("spark.driver.memoryOverhead", "64m") \
    .config("spark.sql.shuffle.partitions", "200") \
    .getOrCreate()

# 读取 CSV，关闭 schema 推断以避免类型问题（或手动指定 schema）
df = spark.read.option("header", True) \
    .option("inferSchema", False) \
    .csv("hdfs://master:9000/user/quant/data/stock_daily.csv") \
    .select("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount")

# 将 trade_date 字符串转为日期（格式 yyyyMMdd）
df = df.withColumn("trade_date", to_date(col("trade_date"), "yyyyMMdd"))

# 按股票分组，按日期排序
window_spec = Window.partitionBy("ts_code").orderBy("trade_date")

# 前向填充 close
df = df.withColumn("close_filled",
                   when(col("close").isNull(),
                        last("close", ignorenulls=True).over(window_spec))
                   .otherwise(col("close")))

# 过滤掉 close 仍为 null 的记录
df_clean = df.filter(col("close_filled").isNotNull()) \
             .drop("close") \
             .withColumnRenamed("close_filled", "close")

# 添加行序号（可选）
df_clean = df_clean.withColumn("row_num", row_number().over(window_spec))

# 保存为 Parquet
df_clean.write.mode("overwrite").parquet("hdfs://master:9000/user/quant/clean/stock_clean.parquet")

print(f"清洗后记录数: {df_clean.count()}")
spark.stop()
