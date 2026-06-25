"""
投資シミュレーター バックエンド
起動: uv run python server.py
URL:  http://localhost:5000
"""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import anthropic
import pandas as pd
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# ============================================================
# 定数
# ============================================================
DB_PATH = Path(__file__).parent / "investment.db"
INITIAL_BALANCE = 1_000_000.0
CLAUDE_MODEL = "claude-sonnet-4-6"
CACHE_TTL = 300  # 株価キャッシュ5分

DEFAULT_STOCKS = [
    ("7203.T", "トヨタ自動車"),
    ("9984.T", "ソフトバンクグループ"),
    ("6758.T", "ソニーグループ"),
    ("8306.T", "三菱UFJフィナンシャル・グループ"),
    ("6861.T", "キーエンス"),
]

# ============================================================
# Flask アプリ
# ============================================================
app = Flask(__name__)
CORS(app)

# ============================================================
# グローバル状態
# ============================================================
_price_cache: dict[str, tuple[dict, float]] = {}
_anthropic_api_key: str = ""
_auto_trade_lock = threading.Lock()
_auto_trade_settings: dict = {
    "enabled": False,
    "interval_minutes": 60,
    "max_spend_per_cycle": 200_000,
}
_scheduler = BackgroundScheduler(daemon=True)

# ============================================================
# DB 初期化
# ============================================================
def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY DEFAULT 1,
                cash_balance REAL NOT NULL,
                initial_balance REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS portfolio (
                stock_code TEXT PRIMARY KEY,
                company_name TEXT,
                shares INTEGER NOT NULL DEFAULT 0,
                avg_buy_price REAL NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT NOT NULL,
                company_name TEXT,
                action TEXT NOT NULL,
                shares INTEGER NOT NULL,
                price REAL NOT NULL,
                total_amount REAL NOT NULL,
                cash_before REAL,
                cash_after REAL,
                profit_loss REAL DEFAULT 0,
                claude_reasoning TEXT,
                triggered_by TEXT DEFAULT 'manual',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS watchlist (
                stock_code TEXT PRIMARY KEY,
                company_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute(
            "INSERT OR IGNORE INTO account (id, cash_balance, initial_balance) VALUES (1, ?, ?)",
            (INITIAL_BALANCE, INITIAL_BALANCE),
        )
        for code, name in DEFAULT_STOCKS:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist (stock_code, company_name) VALUES (?, ?)",
                (code, name),
            )

# ============================================================
# yfinance ヘルパー
# ============================================================
def _normalize_code(code: str) -> str:
    code = code.strip().upper()
    if not code.endswith(".T"):
        code += ".T"
    return code

def _calc_rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("inf"))
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(float(val), 2) if not pd.isna(val) else None

def get_stock_data(code: str) -> dict:
    now = time.time()
    if code in _price_cache:
        data, ts = _price_cache[code]
        if now - ts < CACHE_TTL:
            return data

    try:
        ticker = yf.Ticker(code)
        fi = ticker.fast_info
        current_price = float(fi.last_price) if fi.last_price else None

        hist = ticker.history(period="60d", interval="1d")
        if hist.empty or current_price is None:
            return {"error": f"データ取得失敗: {code}"}

        closes = hist["Close"].dropna()

        ma5 = float(closes.tail(5).mean()) if len(closes) >= 5 else None
        ma25 = float(closes.tail(25).mean()) if len(closes) >= 25 else None
        rsi = _calc_rsi(closes, 14)

        prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else current_price
        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0

        week52_high = None
        week52_low = None
        try:
            week52_high = float(fi.fifty_two_week_high) if fi.fifty_two_week_high else None
            week52_low = float(fi.fifty_two_week_low) if fi.fifty_two_week_low else None
        except Exception:
            pass

        volume = 0
        try:
            volume = int(hist["Volume"].iloc[-1]) if not hist.empty else 0
        except Exception:
            pass

        chart = []
        for d, v in closes.tail(30).items():
            if not pd.isna(v):
                chart.append({"date": str(d.date()), "close": float(v)})

        data = {
            "code": code,
            "price": current_price,
            "ma5": round(ma5, 2) if ma5 else None,
            "ma25": round(ma25, 2) if ma25 else None,
            "rsi": rsi,
            "change_pct": round(change_pct, 2),
            "week52_high": week52_high,
            "week52_low": week52_low,
            "volume": volume,
            "chart": chart,
        }
        _price_cache[code] = (data, now)
        return data
    except Exception as e:
        return {"error": f"取得エラー: {str(e)}"}

# ============================================================
# Claude 分析
# ============================================================
def analyze_with_claude(stock_data: dict, company_name: str, port_row: dict, cash: float) -> dict:
    if not _anthropic_api_key:
        return {"error": "APIキーが未設定です。設定画面で入力してください。"}

    shares = port_row.get("shares", 0)
    avg_price = port_row.get("avg_buy_price", 0)
    holding_value = shares * stock_data["price"]

    def fmt(v, suffix=""):
        if v is None:
            return "N/A"
        return f"{v:,.0f}{suffix}"

    prompt = f"""あなたは日本株の投資アドバイザーです。以下のデータを分析して売買判断をしてください。

銘柄: {company_name} ({stock_data['code']})
現在株価: ¥{fmt(stock_data['price'])}
5日移動平均: ¥{fmt(stock_data['ma5'])}
25日移動平均: ¥{fmt(stock_data['ma25'])}
RSI(14): {stock_data['rsi'] if stock_data['rsi'] else 'N/A'}
本日の変化率: {stock_data['change_pct']}%
52週高値: ¥{fmt(stock_data['week52_high'])}
52週安値: ¥{fmt(stock_data['week52_low'])}
出来高: {fmt(stock_data['volume'])}

現在のポートフォリオ:
- 現金残高: ¥{fmt(cash)}
- 保有株数: {shares}株（平均取得単価: ¥{fmt(avg_price)}）
- 保有株評価額: ¥{fmt(holding_value)}

判断をJSON形式のみで回答してください（前後の説明文は不要）:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "shares": 数量（HOLDの場合は0）,
  "reasoning": "判断理由（日本語200文字以内）",
  "confidence": 0.0から1.0
}}

注意: BUYの場合は現金残高内に収まる株数を指定してください。SELLの場合は保有株数以内を指定してください。"""

    try:
        client = anthropic.Anthropic(api_key=_anthropic_api_key)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # マークダウンコードフェンスを除去
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        # 安全バリデーション
        if result.get("action") not in ("BUY", "SELL", "HOLD"):
            result["action"] = "HOLD"
            result["shares"] = 0
        return result
    except json.JSONDecodeError:
        return {"error": "Claude応答のJSON解析に失敗しました", "action": "HOLD", "shares": 0}
    except anthropic.APIError as e:
        return {"error": f"Claude APIエラー: {str(e)}", "action": "HOLD", "shares": 0}
    except Exception as e:
        return {"error": f"分析エラー: {str(e)}", "action": "HOLD", "shares": 0}

# ============================================================
# 売買実行（内部共通関数）
# ============================================================
def _execute_trade_internal(
    code: str,
    action: str,
    shares_req: int,
    company_name: str = "",
    reasoning: str = "",
    triggered_by: str = "manual",
) -> dict:
    stock = get_stock_data(code)
    if "error" in stock:
        return {"error": stock["error"]}

    price = stock["price"]
    total = price * shares_req

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cash_row = conn.execute("SELECT cash_balance FROM account WHERE id=1").fetchone()
        cash = cash_row["cash_balance"]

        if action == "BUY":
            if total > cash:
                return {"error": f"残高不足（必要: ¥{total:,.0f} / 残高: ¥{cash:,.0f}）"}
            new_cash = cash - total
            existing = conn.execute(
                "SELECT * FROM portfolio WHERE stock_code=?", (code,)
            ).fetchone()
            if existing:
                new_shares = existing["shares"] + shares_req
                new_avg = (
                    existing["avg_buy_price"] * existing["shares"] + price * shares_req
                ) / new_shares
                conn.execute(
                    "UPDATE portfolio SET shares=?, avg_buy_price=?, updated_at=CURRENT_TIMESTAMP WHERE stock_code=?",
                    (new_shares, new_avg, code),
                )
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO portfolio (stock_code, company_name, shares, avg_buy_price) VALUES (?,?,?,?)",
                    (code, company_name, shares_req, price),
                )
            profit_loss = 0.0

        else:  # SELL
            existing = conn.execute(
                "SELECT * FROM portfolio WHERE stock_code=?", (code,)
            ).fetchone()
            if not existing or existing["shares"] < shares_req:
                return {"error": f"保有株数不足（保有: {existing['shares'] if existing else 0}株）"}
            new_cash = cash + total
            profit_loss = (price - existing["avg_buy_price"]) * shares_req
            new_shares = existing["shares"] - shares_req
            if new_shares == 0:
                conn.execute("DELETE FROM portfolio WHERE stock_code=?", (code,))
            else:
                conn.execute(
                    "UPDATE portfolio SET shares=?, updated_at=CURRENT_TIMESTAMP WHERE stock_code=?",
                    (new_shares, code),
                )

        conn.execute("UPDATE account SET cash_balance=? WHERE id=1", (new_cash,))
        conn.execute(
            """INSERT INTO trades
               (stock_code, company_name, action, shares, price, total_amount,
                cash_before, cash_after, profit_loss, claude_reasoning, triggered_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (code, company_name, action, shares_req, price, total,
             cash, new_cash, profit_loss, reasoning, triggered_by),
        )

    return {"ok": True, "new_cash": new_cash, "profit_loss": profit_loss, "price": price}

# ============================================================
# 自動売買スケジューラー
# ============================================================
def auto_trade_job() -> None:
    if not _auto_trade_lock.acquire(blocking=False):
        app.logger.info("Auto-trade: 前のサイクルが実行中のためスキップ")
        return
    try:
        _run_auto_trade()
    except Exception as e:
        app.logger.error(f"Auto-trade エラー: {e}", exc_info=True)
    finally:
        _auto_trade_lock.release()

def _run_auto_trade() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        watchlist = conn.execute(
            "SELECT stock_code, company_name FROM watchlist"
        ).fetchall()

    spent = 0.0
    max_spend = _auto_trade_settings["max_spend_per_cycle"]

    for code, name in watchlist:
        try:
            stock = get_stock_data(code)
            if "error" in stock:
                continue

            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cash = conn.execute(
                    "SELECT cash_balance FROM account WHERE id=1"
                ).fetchone()["cash_balance"]
                port = conn.execute(
                    "SELECT * FROM portfolio WHERE stock_code=?", (code,)
                ).fetchone()

            port_dict = dict(port) if port else {"shares": 0, "avg_buy_price": 0}
            decision = analyze_with_claude(stock, name, port_dict, cash)

            if "error" in decision or decision.get("action") == "HOLD":
                continue

            action = decision["action"]
            shares = int(decision.get("shares", 0))
            if shares <= 0:
                continue

            if action == "BUY":
                cost = stock["price"] * shares
                if spent + cost > max_spend:
                    app.logger.info(f"Auto-trade: {code} BUY スキップ（支出上限）")
                    continue
                spent += cost

            result = _execute_trade_internal(
                code=code,
                action=action,
                shares_req=shares,
                company_name=name,
                reasoning=decision.get("reasoning", ""),
                triggered_by="auto",
            )
            app.logger.info(f"Auto-trade: {code} {action} {shares}株 → {result}")
            time.sleep(0.5)

        except Exception as e:
            app.logger.error(f"Auto-trade {code} エラー: {e}")

def reschedule_auto_trade() -> None:
    if _scheduler.get_job("auto_trade"):
        _scheduler.remove_job("auto_trade")
    if _auto_trade_settings["enabled"]:
        _scheduler.add_job(
            auto_trade_job,
            "interval",
            minutes=_auto_trade_settings["interval_minutes"],
            id="auto_trade",
            replace_existing=True,
        )

# ============================================================
# REST エンドポイント
# ============================================================

@app.route("/")
def index():
    return send_from_directory(Path(__file__).parent, "index.html")

@app.route("/api/account")
def get_account():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        acc = conn.execute("SELECT * FROM account WHERE id=1").fetchone()
        portfolio = conn.execute("SELECT * FROM portfolio").fetchall()

    cash = acc["cash_balance"]
    initial = acc["initial_balance"]
    created_at = acc["created_at"]

    # 現在の保有株評価額を計算
    holding_value = 0.0
    unrealized_pl = 0.0
    for row in portfolio:
        stock = get_stock_data(row["stock_code"])
        if "error" not in stock and stock["price"]:
            val = stock["price"] * row["shares"]
            holding_value += val
            unrealized_pl += (stock["price"] - row["avg_buy_price"]) * row["shares"]

    total_value = cash + holding_value
    total_pl = total_value - initial
    return_pct = (total_pl / initial * 100) if initial else 0

    return jsonify({
        "cash": cash,
        "holding_value": holding_value,
        "total_value": total_value,
        "initial_balance": initial,
        "total_pl": total_pl,
        "unrealized_pl": unrealized_pl,
        "return_pct": round(return_pct, 2),
        "created_at": created_at,
    })

@app.route("/api/portfolio")
def get_portfolio():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()

    result = []
    for row in rows:
        stock = get_stock_data(row["stock_code"])
        price = stock.get("price") if "error" not in stock else None
        pl = ((price - row["avg_buy_price"]) * row["shares"]) if price else None
        pl_pct = ((price - row["avg_buy_price"]) / row["avg_buy_price"] * 100) if price and row["avg_buy_price"] else None
        result.append({
            "stock_code": row["stock_code"],
            "company_name": row["company_name"],
            "shares": row["shares"],
            "avg_buy_price": row["avg_buy_price"],
            "current_price": price,
            "value": price * row["shares"] if price else None,
            "profit_loss": round(pl, 2) if pl is not None else None,
            "profit_loss_pct": round(pl_pct, 2) if pl_pct is not None else None,
            "change_pct": stock.get("change_pct"),
        })
    return jsonify(result)

@app.route("/api/stocks/<path:code>")
def get_stock(code: str):
    code = _normalize_code(code)
    # ウォッチリスト・ポートフォリオから会社名を取得
    company_name = ""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT company_name FROM watchlist WHERE stock_code=?", (code,)
        ).fetchone()
        if row:
            company_name = row[0]
    data = get_stock_data(code)
    if "error" in data:
        return jsonify(data), 404
    data["company_name"] = company_name
    return jsonify(data)

@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM watchlist ORDER BY added_at DESC"
        ).fetchall()

    result = []
    for row in rows:
        stock = get_stock_data(row["stock_code"])
        result.append({
            "stock_code": row["stock_code"],
            "company_name": row["company_name"],
            "price": stock.get("price") if "error" not in stock else None,
            "change_pct": stock.get("change_pct") if "error" not in stock else None,
            "added_at": row["added_at"],
        })
    return jsonify(result)

@app.route("/api/watchlist", methods=["POST"])
def add_watchlist():
    body = request.json
    code = _normalize_code(body.get("stock_code", ""))
    name = body.get("company_name", "")

    # 会社名が未指定の場合はyfinanceから取得を試みる
    if not name:
        try:
            ticker = yf.Ticker(code)
            info = ticker.info
            name = info.get("longName") or info.get("shortName") or code
        except Exception:
            name = code

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist (stock_code, company_name) VALUES (?, ?)",
            (code, name),
        )
    return jsonify({"ok": True, "stock_code": code, "company_name": name})

@app.route("/api/watchlist/<path:code>", methods=["DELETE"])
def delete_watchlist(code: str):
    code = _normalize_code(code)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM watchlist WHERE stock_code=?", (code,))
    return jsonify({"ok": True})

@app.route("/api/trades")
def get_trades():
    stock_filter = request.args.get("stock")
    action_filter = request.args.get("action")

    query = "SELECT * FROM trades"
    params = []
    conditions = []
    if stock_filter:
        conditions.append("stock_code=?")
        params.append(_normalize_code(stock_filter))
    if action_filter and action_filter in ("BUY", "SELL"):
        conditions.append("action=?")
        params.append(action_filter)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp DESC LIMIT 200"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    return jsonify([dict(r) for r in rows])

@app.route("/api/analyze", methods=["POST"])
def analyze():
    body = request.json
    code = _normalize_code(body.get("stock_code", ""))
    company_name = body.get("company_name", "")

    stock = get_stock_data(code)
    if "error" in stock:
        return jsonify(stock), 404

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cash_row = conn.execute("SELECT cash_balance FROM account WHERE id=1").fetchone()
        port = conn.execute("SELECT * FROM portfolio WHERE stock_code=?", (code,)).fetchone()

    port_dict = dict(port) if port else {"shares": 0, "avg_buy_price": 0}
    cash = cash_row["cash_balance"]

    decision = analyze_with_claude(stock, company_name, port_dict, cash)
    decision["stock_code"] = code
    decision["current_price"] = stock["price"]
    return jsonify(decision)

@app.route("/api/trade", methods=["POST"])
def execute_trade():
    body = request.json
    code = _normalize_code(body.get("stock_code", ""))
    action = body.get("action", "").upper()
    shares_req = int(body.get("shares", 0))
    company_name = body.get("company_name", "")
    reasoning = body.get("claude_reasoning", "")
    triggered_by = body.get("triggered_by", "manual")

    if action not in ("BUY", "SELL") or shares_req <= 0:
        return jsonify({"error": "無効なリクエスト"}), 400

    result = _execute_trade_internal(
        code=code,
        action=action,
        shares_req=shares_req,
        company_name=company_name,
        reasoning=reasoning,
        triggered_by=triggered_by,
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route("/api/auto-trade", methods=["POST"])
def trigger_auto_trade():
    threading.Thread(target=auto_trade_job, daemon=True).start()
    return jsonify({"ok": True, "message": "自動売買を開始しました"})

@app.route("/api/stats")
def get_stats():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        acc = conn.execute("SELECT * FROM account WHERE id=1").fetchone()
        trades = conn.execute("SELECT * FROM trades ORDER BY timestamp DESC").fetchall()
        portfolio = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()

    initial = acc["initial_balance"]
    cash = acc["cash_balance"]

    holding_value = 0.0
    for row in portfolio:
        stock = get_stock_data(row["stock_code"])
        if "error" not in stock and stock["price"]:
            holding_value += stock["price"] * row["shares"]

    total_value = cash + holding_value
    total_pl = total_value - initial
    return_pct = (total_pl / initial * 100) if initial else 0

    # 銘柄別損益
    stock_pl: dict[str, float] = {}
    for t in trades:
        code = t["stock_code"]
        stock_pl[code] = stock_pl.get(code, 0) + (t["profit_loss"] or 0)

    best = max(stock_pl.items(), key=lambda x: x[1]) if stock_pl else None
    worst = min(stock_pl.items(), key=lambda x: x[1]) if stock_pl else None

    return jsonify({
        "total_value": total_value,
        "total_pl": total_pl,
        "return_pct": round(return_pct, 2),
        "trade_count": len(trades),
        "buy_count": sum(1 for t in trades if t["action"] == "BUY"),
        "sell_count": sum(1 for t in trades if t["action"] == "SELL"),
        "best_stock": {"code": best[0], "pl": best[1]} if best else None,
        "worst_stock": {"code": worst[0], "pl": worst[1]} if worst else None,
    })

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({
        "api_key_set": bool(_anthropic_api_key),
        "auto_trade": _auto_trade_settings,
    })

@app.route("/api/settings", methods=["POST"])
def post_settings():
    global _anthropic_api_key
    body = request.json
    if "api_key" in body:
        _anthropic_api_key = body["api_key"]
    if "auto_trade" in body:
        _auto_trade_settings.update(body["auto_trade"])
        reschedule_auto_trade()
    return jsonify({"ok": True})

@app.route("/api/reset", methods=["POST"])
def reset_portfolio():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE account SET cash_balance=initial_balance WHERE id=1")
        conn.execute("DELETE FROM portfolio")
        conn.execute("DELETE FROM trades")
    _price_cache.clear()
    return jsonify({"ok": True})

# ============================================================
# エントリーポイント
# ============================================================
if __name__ == "__main__":
    init_db()
    _scheduler.start()
    print("=" * 50)
    print("  投資シミュレーター起動")
    print(f"  URL: http://localhost:5000")
    print(f"  DB:  {DB_PATH}")
    print(f"  初期残高: ¥{INITIAL_BALANCE:,.0f}")
    print("  停止: Ctrl+C")
    print("=" * 50)
    app.run(host="127.0.0.1", port=5000, debug=False)
