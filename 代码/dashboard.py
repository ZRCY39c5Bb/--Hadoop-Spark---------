#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多因子量化选股系统 - HTML 仪表盘生成器
零额外依赖：仅需 Python 3 标准库
图表通过 CDN 加载 ECharts
"""
import csv
import json
import math
import os
from datetime import datetime
# ============================================================
#  配置
# ============================================================
NAV_CSV = "nav_curve.csv"
HOLDING_CSV = "latest_holding.csv"
OUTPUT_HTML = "dashboard.html"
# ============================================================
#  1. 读取净值数据（健壮版：跳过空值行）
# ============================================================
def load_nav(csv_path):
    """读取净值曲线 CSV，返回 dates, navs, rets"""
    if not os.path.exists(csv_path):
        print(f"[警告] 未找到 {csv_path}")
        return [], [], []
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        print(f"[调试] CSV 表头: {header}")
        for r in reader:
            if not r or len(r) < 2:
                continue
            rows.append(r)
    print(f"[调试] 原始行数: {len(rows)}")
    rows.sort(key=lambda x: x[0])
    dates = []
    navs = []
    rets = []
    for r in rows:
        date_str = r[0].strip()
        ret_str = r[1].strip() if len(r) >= 2 else ""
        nav_str = r[2].strip() if len(r) >= 3 else ""
        # 跳过净值空白行（第一天无收益导致）
        if not nav_str:
            continue
        try:
            nav_val = float(nav_str)
        except ValueError:
            continue
        ret_val = None
        if ret_str:
            try:
                ret_val = float(ret_str)
            except ValueError:
                ret_val = None
        dates.append(date_str)
        navs.append(nav_val)
        rets.append(ret_val)
    print(f"[调试] 有效行数: {len(dates)}")
    if navs:
        print(f"[调试] 净值范围: {navs[0]:.4f} ~ {navs[-1]:.4f}")
    return dates, navs, rets
# ============================================================
#  2. 读取持仓数据
# ============================================================
def load_holding(csv_path):
    if not os.path.exists(csv_path):
        return []
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for r in reader:
            if r and len(r) >= 3:
                rows.append(r)
    return rows
# ============================================================
#  3. 计算指标
# ============================================================
def calc_metrics(dates, navs, rets):
    if not navs or len(navs) < 2:
        return {}
    total_ret = navs[-1] / navs[0] - 1
    n = len(navs)
    ann_ret = (navs[-1] / navs[0]) ** (252.0 / n) - 1 if n > 0 else 0
    # 最大回撤
    peak = navs[0]
    mdd = 0
    for v in navs:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > mdd:
            mdd = dd
    # 年化波动率 & 夏普比率
    valid_rets = [r for r in rets if r is not None]
    if len(valid_rets) > 1:
        mean_ret = sum(valid_rets) / len(valid_rets)
        var = sum((r - mean_ret) ** 2 for r in valid_rets) / (len(valid_rets) - 1)
        ann_vol = math.sqrt(var) * math.sqrt(252)
        sharpe = (ann_ret - 0.025) / ann_vol if ann_vol > 0 else 0
    else:
        ann_vol = 0
        sharpe = 0
    return {
        "total_ret": total_ret,
        "ann_ret": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "mdd": mdd,
        "start_date": dates[0] if dates else "",
        "end_date": dates[-1] if dates else "",
    }
# ============================================================
#  4. 构建 HTML
# ============================================================
def build_html(dates, navs, rets, holdings, metrics):
    dates_json = json.dumps(dates, ensure_ascii=False)
    navs_json = json.dumps(navs)
    # 持仓表格行
    holding_rows = ""
    for i, r in enumerate(holdings[:30]):
        rank = r[3].strip() if len(r) > 3 else str(i+1)
        code = r[1].strip() if len(r) > 1 else (r[0].strip() if len(r) > 0 else "")
        score = r[2].strip() if len(r) > 2 else ""
        date_col = r[0].strip() if len(r) > 0 else ""
        holding_rows += f"""
            <tr>
                <td>{rank}</td>
                <td><b>{code}</b></td>
                <td>{score}</td>
                <td>{date_col}</td>
            </tr>"""
    # 日收益直方图数据
    valid_rets = [r for r in rets if r is not None]
    if valid_rets:
        min_r = min(valid_rets)
        max_r = max(valid_rets)
        bins = 30
        bin_w = (max_r - min_r) / bins if bins > 0 else 0.01
        counts = [0] * bins
        for r in valid_rets:
            idx = min(int((r - min_r) / bin_w), bins - 1)
            counts[idx] += 1
        categories = [f"{min_r + i*bin_w:.4f}" for i in range(bins)]
        categories_json = json.dumps(categories)
        hist_json = json.dumps(counts)
    else:
        categories_json = "[]"
        hist_json = "[]"
    # 找最大回撤区间
    peak = navs[0] if navs else 0
    peak_idx = 0
    max_dd_val = 0
    dd_start_idx = 0
    dd_end_idx = 0
    for i, v in enumerate(navs):
        if v > peak:
            peak = v
            peak_idx = i
        dd = (peak - v) / peak if peak > 0 else 0
        if dd > max_dd_val:
            max_dd_val = dd
            dd_start_idx = peak_idx
            dd_end_idx = i
    m = metrics
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>多因子量化选股系统</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f0f2f5; color: #333; }}
        .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: white; padding: 32px 40px; text-align: center; }}
        .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .header p {{ opacity: 0.75; font-size: 14px; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); text-align: center; }}
        .card .label {{ font-size: 13px; color: #888; margin-bottom: 8px; }}
        .card .value {{ font-size: 26px; font-weight: 700; }}
        .card .value.positive {{ color: #e74c3c; }}
        .card .value.negative {{ color: #27ae60; }}
        .chart-box {{ background: white; border-radius: 12px; padding: 20px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .chart-box h2 {{ font-size: 18px; margin-bottom: 16px; color: #1a1a2e; }}
        .chart {{ width: 100%; height: 420px; }}
        .half {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
        @media (max-width: 768px) {{ .half {{ grid-template-columns: 1fr; }} }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; font-size: 13px; color: #555; }}
        td {{ font-size: 14px; }}
        tr:hover {{ background: #f8f9ff; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
        .badge {{ display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; background: rgba(255,255,255,0.2); color: white; margin-left: 8px; }}
    </style>
</head>
<body>
<div class="header">
    <h1>📈 基于 Hadoop + Spark 的多因子量化选股系统</h1>
    <p>
        回测区间：{m.get('start_date','')}  —  {m.get('end_date','')}
        <span class="badge">日频调仓</span>
        <span class="badge">等权组合</span>
        <span class="badge">TOP 30</span>
        <span class="badge">6因子模型</span>
    </p>
</div>
<div class="container">
    <div class="cards">
        <div class="card">
            <div class="label">累计收益率</div>
            <div class="value {"positive" if m.get('total_ret',0)>=0 else "negative"}">{m.get('total_ret',0):+.2%}</div>
        </div>
        <div class="card">
            <div class="label">年化收益率</div>
            <div class="value {"positive" if m.get('ann_ret',0)>=0 else "negative"}">{m.get('ann_ret',0):+.2%}</div>
        </div>
        <div class="card">
            <div class="label">夏普比率</div>
            <div class="value" style="color:#0f3460">{m.get('sharpe',0):.4f}</div>
        </div>
        <div class="card">
            <div class="label">最大回撤</div>
            <div class="value negative">{m.get('mdd',0):.2%}</div>
        </div>
        <div class="card">
            <div class="label">年化波动率</div>
            <div class="value" style="color:#555">{m.get('ann_vol',0):.2%}</div>
        </div>
    </div>
    <div class="chart-box">
        <h2>📊 策略净值曲线（红色阴影 = 最大回撤区间）</h2>
        <div id="navChart" class="chart"></div>
    </div>
    <div class="half">
        <div class="chart-box">
            <h2>📉 日收益率分布</h2>
            <div id="histChart" class="chart"></div>
        </div>
        <div class="chart-box">
            <h2>📋 最新持仓 TOP 30</h2>
            <div style="max-height: 420px; overflow-y: auto;">
                <table>
                    <thead>
                        <tr><th>排名</th><th>股票代码</th><th>综合得分</th><th>调仓日期</th></tr>
                    </thead>
                    <tbody>{holding_rows}</tbody>
                </table>
            </div>
        </div>
    </div>
</div>
<div class="footer">
    数据来源：Tushare Pro &nbsp;|&nbsp; 计算引擎：Apache Spark 3.4 &nbsp;|&nbsp; 存储：HDFS Parquet &nbsp;|&nbsp; 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
</div>
<script>
var navData = {navs_json};
var peakVal = navData[0], peakI = 0;
var maxDD = 0, ddS = 0, ddE = 0;
for (var i = 1; i < navData.length; i++) {{
    if (navData[i] > peakVal) {{ peakVal = navData[i]; peakI = i; }}
    var dd = (peakVal - navData[i]) / peakVal;
    if (dd > maxDD) {{ maxDD = dd; ddS = peakI; ddE = i; }}
}}
var navChart = echarts.init(document.getElementById('navChart'));
navChart.setOption({{
    tooltip: {{
        trigger: 'axis',
        backgroundColor: 'rgba(255,255,255,0.96)',
        borderColor: '#ddd',
        textStyle: {{ color: '#333' }},
        formatter: function(p) {{ return p[0].axisValue + '<br/>净值：<b>' + p[0].value.toFixed(4) + '</b>'; }}
    }},
    grid: {{ left: 65, right: 35, top: 15, bottom: 45 }},
    xAxis: {{
        type: 'category',
        data: {dates_json},
        axisLabel: {{ rotate: 45, fontSize: 10, formatter: function(v){{ return v.substring(5); }} }},
        axisLine: {{ lineStyle: {{ color: '#ccc' }} }}
    }},
    yAxis: {{
        type: 'value',
        name: '净值',
        scale: true,
        splitLine: {{ lineStyle: {{ type: 'dashed', color: '#eee' }} }}
    }},
    dataZoom: [
        {{ type: 'slider', start: 0, end: 100, height: 26, bottom: 0 }},
        {{ type: 'inside' }}
    ],
    series: [{{
        name: '策略净值',
        type: 'line',
        data: {navs_json},
        smooth: true,
        lineStyle: {{ color: '#1890ff', width: 2.5 }},
        itemStyle: {{ color: '#1890ff' }},
        areaStyle: {{
            color: new echarts.graphic.LinearGradient(0,0,0,1,[
                {{ offset:0, color:'rgba(24,144,255,0.22)' }},
                {{ offset:1, color:'rgba(24,144,255,0.01)' }}
            ])
        }},
        markLine: {{
            silent: true, symbol: 'none',
            lineStyle: {{ color: '#999', type: 'dashed', width: 1 }},
            data: [{{ yAxis: navData[0], label: {{ formatter:'初始=\u007b'+navData[0].toFixed(3)+'\u007d', position:'start' }} }}]
        }},
        markArea: {{
            silent: true,
            data: [[
                {{ xAxis: {dates_json}[ddS], itemStyle: {{ color:'rgba(255,77,79,0.10)' }} }},
                {{ xAxis: {dates_json}[ddE] }}
            ]]
        }}
    }}]
}});
var histChart = echarts.init(document.getElementById('histChart'));
histChart.setOption({{
    tooltip: {{
        trigger: 'axis',
        axisPointer: {{ type: 'shadow' }},
        formatter: function(p) {{ return '区间：' + p[0].name + '<br/>频数：<b>' + p[0].value + '</b>'; }}
    }},
    grid: {{ left: 50, right: 20, top: 10, bottom: 45 }},
    xAxis: {{
        type: 'category',
        data: {categories_json},
        axisLabel: {{ rotate: 60, fontSize: 9, formatter: function(v){{ return parseFloat(v).toFixed(3); }} }}
    }},
    yAxis: {{
        type: 'value', name: '频数',
        splitLine: {{ lineStyle: {{ type:'dashed', color:'#eee' }} }}
    }},
    series: [{{
        type: 'bar',
        data: {hist_json},
        itemStyle: {{
            color: new echarts.graphic.LinearGradient(0,0,0,1,[
                {{ offset:0, color:'#1890ff' }}, {{ offset:1, color:'#91d5ff' }}
            ]),
            borderRadius: [4,4,0,0]
        }}
    }}]
}});
window.addEventListener('resize', function(){{ navChart.resize(); histChart.resize(); }});
</script>
</body>
</html>"""
    return html
# ============================================================
#  主入口
# ============================================================
def main():
    print("=" * 60)
    print("  多因子量化选股系统 - 仪表盘生成器")
    print("=" * 60)
    dates, navs, rets = load_nav(NAV_CSV)
    holdings = load_holding(HOLDING_CSV)
    if not dates:
        print("\n[错误] 净值数据为空！请确保 nav_curve.csv 存在。")
        print("  运行: hdfs dfs -getmerge /user/quant/output/nav_curve/ nav_curve.csv")
        return
    print(f"\n✅ 净值数据: {len(dates)} 个交易日 ({dates[0]} ~ {dates[-1]})")
    print(f"✅ 持仓记录: {len(holdings)} 只股票")
    metrics = calc_metrics(dates, navs, rets)
    print(f"\n📊 回测指标:")
    print(f"   累计收益率 : {metrics['total_ret']:+.2%}")
    print(f"   年化收益率 : {metrics['ann_ret']:+.2%}")
    print(f"   年化波动率 : {metrics['ann_vol']:.2%}")
    print(f"   夏普比率   : {metrics['sharpe']:.4f}")
    print(f"   最大回撤   : {metrics['mdd']:.2%}")
    html = build_html(dates, navs, rets, holdings, metrics)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ 仪表盘已生成: {os.path.abspath(OUTPUT_HTML)}")
    print(f"   浏览器访问: file://{os.path.abspath(OUTPUT_HTML)}")
    print(f"\n   或启动 HTTP 服务供远程访问:")
    print(f"   cd {os.path.dirname(os.path.abspath(OUTPUT_HTML)) or '.'}")
    print(f"   python3 -m http.server 8501 --bind 0.0.0.0")
    print(f"   然后访问: http://<服务器IP>:8501/dashboard.html")
if __name__ == "__main__":
    main()
