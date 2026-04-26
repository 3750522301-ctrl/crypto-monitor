import requests
import pandas as pd
from datetime import datetime
import json
import time
import os

STABLE_DAYS = 5
STABLE_VOL_THRESHOLD = 0.10
BREAKOUT_THRESHOLD = 0.10
VOL_MULTIPLIER = 2.0

FAPI_URLS = [
    "https://fapi.binance.com/fapi/v1",
    "https://fapi1.binance.com/fapi/v1",
    "https://fapi2.binance.com/fapi/v1",
    "https://fapi3.binance.com/fapi/v1",
]

def fapi_get(endpoint, params=None):
    if params is None:
        params = {}
    for base in FAPI_URLS:
        try:
            r = requests.get(f"{base}/{endpoint}", params=params, timeout=15)
            data = r.json()
            if isinstance(data, dict) and "code" in data:
                continue
            if isinstance(data, (dict, list)):
                return data
        except Exception:
            continue
    return None

def get_all_futures_symbols():
    data = fapi_get("exchangeInfo")
    if not data or "symbols" not in data:
        print("获取合约列表失败")
        return []
    symbols = []
    for s in data["symbols"]:
        if (
            s["symbol"].endswith("USDT")
            and s["status"] == "TRADING"
            and s["contractType"] == "PERPETUAL"
        ):
            symbols.append(s["symbol"])
    symbols.sort()
    print(f"共获取到 {len(symbols)} 个USDT永续合约")
    return symbols

def get_daily_klines(symbol, days=30):
    data = fapi_get("klines", {
        "symbol": symbol,
        "interval": "1d",
        "limit": days + 5
    })
    if not data or not isinstance(data, list):
        return None
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df = df.set_index("open_time").sort_index()
    df["daily_vol"] = (df["high"] - df["low"]) / df["open"] * 100
    return df

def get_recent_klines(symbol, interval, limit=5):
    data = fapi_get("klines", {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    })
    if not data or not isinstance(data, list):
        return None
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df = df.set_index("open_time").sort_index()
    return df

def get_ticker(symbol):
    data = fapi_get("ticker/price", {"symbol": symbol})
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
    for label, interval, limit in [("15m", "15m", 4), ("4h", "4h", 3), ("1d", "1d", 2)]:
        df = get_recent_klines(symbol, interval, limit)
        if df is None or len(df) < 2:
            continue
        last = df.iloc[-2]
        change_pct = (last["close"] - last["open"]) / last["open"] * 100
        candle_vol = (last["high"] - last["low"]) / last["open"] * 100
        if (
            abs(change_pct) >= BREAKOUT_THRESHOLD * 100
            and stable_avg_vol > 0
            and candle_vol >= stable_avg_vol * VOL_MULTIPLIER
        ):
            signals.append({
                "周期": label,
                "方向": "🚀 暴涨" if change_pct > 0 else "💥 暴跌",
                "涨跌幅": round(change_pct, 2),
                "K线波动": round(candle_vol, 2),
                "稳定期均波动": round(stable_avg_vol, 2),
                "波动倍数": round(candle_vol / stable_avg_vol, 1),
                "K线时间": str(df.index[-2]),
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
        "symbol": symbol,
        "current_price": get_ticker(symbol),
        "stable_days": stable_days,
        "avg_vol_pct": round(avg_vol, 2),
        "signals": signals,
        "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

def print_result(result):
    print("\n" + "="*50)
    print(f"  ⚡ 异动币种: {result['symbol']}")
    print(f"  💰 当前价格: {result['current_price']}")
    print(f"  📅 稳定天数: {result['stable_days']}天")
    print(f"  📊 稳定期均波动: {result['avg_vol_pct']}%")
    print(f"  🕐 检测时间: {result['detected_at']}")
    for s in result["signals"]:
        print(f"\n  [{s['周期']}] {s['方向']}")
        print(f"    涨跌幅:   {s['涨跌幅']}%")
        print(f"    K线波动:  {s['K线波动']}%")
        print(f"    波动放大: {s['波动倍数']}x")
        print(f"    K线时间:  {s['K线时间'][:16]}")
    print("="*50)

def main():
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 50)
    print("   ⚡ 币安合约异动监控 - 本地版")
    print("=" * 50)
    print(f"  稳定期:   连续 {STABLE_DAYS} 天日波动 < {int(STABLE_VOL_THRESHOLD*100)}%")
    print(f"  触发条件: 涨跌 > {int(BREAKOUT_THRESHOLD*100)}% 且波动放大 {VOL_MULTIPLIER}x")
    print(f"  合约类型: U本位永续合约")
    print("=" * 50)

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n🔍 开始新一轮扫描 [{now}]")

        symbols = get_all_futures_symbols()
        if not symbols:
            print("❌ 获取合约列表失败，60秒后重试...")
            time.sleep(60)
            continue

        total = len(symbols)
        found_this_round = []

        for i, symbol in enumerate(symbols):
            pct = int((i + 1) / total * 100)
            filled = pct // 5
            bar = "#" * filled + "-" * (20 - filled)
            print(f"\r  [{bar}] {pct:3d}% [{i+1}/{total}] {symbol:<20}", end="", flush=True)

            try:
                result = check_symbol(symbol)
                if result:
                    found_this_round.append(result)
                    print_result(result)
            except Exception as e:
                pass

            time.sleep(0.05)

        print(f"\n\n✅ 本轮完成！发现 {len(found_this_round)} 个异动")

        if found_this_round:
            try:
                with open("alerts.json", "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []

            history.extend(found_this_round)

            with open("alerts.json", "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

            print(f"📁 结果已保存到 alerts.json（累计 {len(history)} 条）")

        print("\n⏳ 15分钟后开始下一轮扫描...")
        print("   按 Ctrl+C 退出")

        time.sleep(900)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已退出监控")
