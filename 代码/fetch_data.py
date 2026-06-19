import tushare as ts
import pandas as pd

ts.set_token('877294b694c947b1be4e3e67afc7d71993dd80b10a2c0f82f8295313')   # 替换为你自己的 token
pro = ts.pro_api()

# 手动指定 30 只沪深 300 成分股代码（示例）
stock_list = [
    '000001.SZ', '000002.SZ', '000063.SZ', '000069.SZ', '000100.SZ',
    '000157.SZ', '000166.SZ', '000333.SZ', '000338.SZ', '000425.SZ',
    '000538.SZ', '000568.SZ', '000625.SZ', '000651.SZ', '000656.SZ',
    '000725.SZ', '000768.SZ', '000776.SZ', '000858.SZ', '000895.SZ',
    '001979.SZ', '002007.SZ', '002027.SZ', '002049.SZ', '002050.SZ',
    '002129.SZ', '002142.SZ', '002179.SZ', '002230.SZ', '002236.SZ'
]

all_data = []
for code in stock_list:
    df = pro.daily(ts_code=code, start_date='20200101', end_date='20231231',
                   fields='ts_code,trade_date,open,high,low,close,vol,amount')
    if df is not None and not df.empty:
        all_data.append(df)
        print(f'Fetched {code}')
    else:
        print(f'No data for {code}')

if all_data:
    full_df = pd.concat(all_data, ignore_index=True)
    full_df.to_csv('stock_daily.csv', index=False)
    print(f'共采集 {len(full_df)} 条记录')
else:
    print('未获取到任何数据')
