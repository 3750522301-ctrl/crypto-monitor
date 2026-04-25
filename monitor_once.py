import requests
import pandas as pd
import numpy as np
from datetime import datetime
import json
import time

STABLE_DAYS          = 5
STABLE_VOL_THRESHOLD = 0.10
BREAKOUT_THRESHOLD   = 0.10
VOL_MULTIPLIER       = 3.0

SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    "DOGEUSDT","ADAUSDT","AVAXUSDT","MATICUSDT","DOTUSDT",
    "LINKUSDT","UNIUSDT","ATOMUSDT","LTCUSDT","NEARUSDT",
    "APTUSDT","ARBUSDT","OPUSDT","INJUSDT","SUIUSDT",
]

BINANCE_URLS = [
    "https://api.binance.com/api/v3",
    "https://api1.binance.com/api/v3",
    "https://api2.binance.com/api/v3",
]

def binance_get(endpoint, params):
    for base in BINANCE_URLS:
        try:
            r = requests.get(f"{base}/{endpoint}", params=params, timeout=10)
            data = r.json()
            if isinstance(data, (list, dict)):
                return data
        except Exception:
            continue
    return None

def get_daily_klines(symbol, days=30):
    data = binance_get("klines", {"symbol": symbol, "interval": "1d", "limit": days + 5})
    if not data:
        return None
    df = pd.DataFrame(data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_volume","trades",
        "taker_buy_base","taker_buy_quote","ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    df = df.set_index("open_time").sort_index()
    df["daily_vol"] = (df["high"] - df["low"]) / df["open"] * 100
    return df

def get_recent_klines(symbol, interval, limit=5):
    data = binance_get("klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not data:
        return None
    df = pd.DataFrame(data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_volume","trades",
        "taker_buy_base","taker_buy_quote","ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    df = df.set_index("open_time").sort_index()
    return df

def get_ticker(symbol):
    data = binance_get("ticker/price", {"symbol": symbol})
    if data and "price" in data:
        return float(data["price"])
    return None

def check_stable_period(df_daily):
    past = df_daily.iloc[:-1].copy()
    if len(past) < STABLE_DAYS:
        return False, 0, 0
    stable_count = 0
    for i in range(len(past) - 1, -1, -1):
        if past.iloc[i]["daily_vol"] < STABLE_VOL_THRESHOLD * 100:
            stable_count += 1
        else:
            break
    if stable_count < STABLE_DAYS:
        return False, stable_count, 0
    avg_vol = past.iloc[-stable_count:]["daily_vol"].mean()
    return True, stable_count, avg_vol

def check_breakout(symbol, stable_avg_vol):
    signals = []
    for label, interval, limit in [("15m","15m",4),("4h","4h",3),("1d","1d",2)]:
        df = get_recent_klines(symbol, interval, limit)
        if df is None or len(df) < 2:
            continue
        last       = df.iloc[-2]
        change_pct = (last["close"] - last["open"]) / last["open"] * 100
        candle_vol = (last["high"]  - last["low"])  / last["open"] * 100
        if (abs(change_pct) >= BREAKOUT_THRESHOLD * 100 and
                stable_avg_vol > 0 and
                candle_vol >= stable_avg_vol * VOL_MULTIPLIER):
            signals.append({
                "周期"        : label,
                "方向"        : "🚀 暴涨" if change_pct > 0 else "💥 暴跌",
                "涨跌幅"      : round(change_pct, 2),
                "K线波动"     : round(candle_vol, 2),
                "稳定期均波动": round(stable_avg_vol, 2),
                "波动倍数"    : round(candle_vol / stable_avg_vol, 1),
                "K线时间"     : str(df.index[-2]),
            })
    return signals

def check_symbol(symbol):
    df_daily = get_daily_klines(symbol)
    if df_daily is None:
        return None
    is_stable, stable_days, avg_vol = check_stable_period(df_daily)
    if not is_stable:
        return None
    signals = check_breakout(symbol, avg_vol)
    if not signals:
        return None
    return {
        "symbol"       : symbol,
        "current_price": get_ticker(symbol),
        "stable_days"  : stable_days,
        "avg_vol_pct"  : round(avg_vol, 2),
        "signals"      : signals,
        "detected_at"  : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

def generate_html(history):
    html = """<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="60">
  <title>币安异动监控</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #0d1117; color: #e6edf3; font-family: 'Segoe UI', sans-serif; padding: 20px; }
    h1 { text-align: center; color: #58a6ff; margin-bottom: 8px; font-size: 24px; }
    .subtitle { text-align: center; color: #8b949e; font-size: 13px; margin-bottom: 24px; }
    .stats { display: flex; gap: 16px; justify-content: center; margin-bottom: 24px; flex-wrap: wrap; }
    .stat-box { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 24px; text-align: center; }
    .stat-box .num { font-size: 28px; font-weight: bold; color: #58a6ff; }
    .stat-box .label { font-size: 12px; color: #8b949e; margin-top: 4px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px; }
    .card.up   { border-left: 4px solid #3fb950; }
    .card.down { border-left: 4px solid #f85149; }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .symbol { font-size: 18px; font-weight: bold; color: #58a6ff; }
    .time { font-size: 11px; color: #8b949e; }
    .price { font-size: 13px; color: #8b949e; margin-bottom: 10px; }
    .stable-info { font-size: 12px; color: #8b949e; margin-bottom: 10px; padding: 6px 10px; background: #0d1117; border-radius: 6px; }
    .signal { background: #0d1117; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; }
    .signal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .period { font-size: 12px; font-weight: bold; background: #21262d; padding: 2px 8px; border-radius: 10px; }
    .up-text   { color: #3fb950; font-weight: bold; }
    .down-text { color: #f85149; font-weight: bold; }
    .signal-row { display: flex; justify-content: space-between; font-size: 12px; color: #8b949e; margin-top: 3px; }
    .signal-row span:last-child { color: #e6edf3; }
    .multiplier { color: #e3b341; font-weight: bold; }
    .no-data { text-align: center; color: #8b949e; padding: 60px; font-size: 16px; }
    .update-time { text-align: center; color: #8b949e; font-size: 12px; margin-top: 24px; }
  </style>
</head>
<body>
<h1>⚡ 币安异动监控</h1>
<p class="subtitle">稳定≥5天(日波动&lt;10%) → 突破涨跌&gt;10% 且波动率暴增</p>
<div class="stats">
  <div class="stat-box"><div class="num">""" + str(len(history)) + """</div><div class="label">累计异动</div></div>
  <div class="stat-box"><div class="num" style="color:#3fb950">""" + str(sum(1 for d in history if any("暴涨" in s["方向"] for s in d["signals"]))) + """</div><div class="label">暴涨信号</div></div>
  <div class="stat-box"><div class="num" style="color:#f85149">""" + str(sum(1 for d in history if any("暴跌" in s["方向"] for s in d["signals"]))) + """</div><div class="label">暴跌信号</div></div>
</div>
<div class="grid">
"""
    if not history:
        html += '<div class="no-data">暂无异动数据</div>'
    else:
        for item in reversed(history):
            is_up    = any("暴涨" in s["方向"] for s in item["signals"])
            card_cls = "up" if is_up else "down"
            signals_html = ""
            for s in item["signals"]:
                is_up_sig  = "暴涨" in s["方向"]
                dir_cls    = "up-text" if is_up_sig else "down-text"
                change_str = f"+{s['涨跌幅']}%" if s['涨跌幅'] > 0 else f"{s['涨跌幅']}%"
                signals_html += f"""
                <div class="signal">
                  <div class="signal-header">
                    <span class="period">{s['周期']}</span>
                    <span class="{dir_cls}">{s['方向']}</span>
                  </div>
                  <div class="signal-row"><span>涨跌幅</span><span class="{dir_cls}">{change_str}</span></div>
                  <div class="signal-row"><span>K线波动</span><span>{s['K线波动']}%</span></div>
                  <div class="signal-row"><span>波动放大</span><span class="multiplier">{s['波动倍数']}x</span></div>
                  <div class="signal-row"><span>K线时间</span><span>{str(s['K线时间'])[:16]}</span></div>
                </div>"""

            html += f"""
            <div class="card {card_cls}">
              <div class="card-header">
                <span class="symbol">{item['symbol']}</span>
                <span class="time">{item['detected_at']}</span>
              </div>
              <div class="price">💰 当前价: {item['current_price']}</div>
              <div class="stable-info">📅 稳定 {item['stable_days']} 天 &nbsp;|&nbsp; 均波动 {item['avg_vol_pct']}%</div>
              {signals_html}
            </div>"""

    html += f"""
</div>
<div class="update-time">最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</body>
</html>"""
    return html

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始扫描 {len(SYMBOLS)} 个币种...")

    try:
        with open("alerts.json", "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = []

    for symbol in SYMBOLS:
        try:
            result = check_symbol(symbol)
            if result:
                print(f"  ⚡ {symbol} 异动！{result['signals'][0]['方向']} {result['signals'][0]['涨跌幅']}%")
                history.append(result)
            else:
                print(f"  ✅ {symbol} 正常")
        except Exception as e:
            print(f"  ❌ {symbol} 出错: {e}")
        time.sleep(0.2)

    with open("alerts.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(generate_html(history))

    print(f"完成！共 {len(history)} 条记录")

if __name__ == "__main__":
    main()
