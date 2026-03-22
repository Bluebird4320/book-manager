"""
読書AIエージェント MCP Server
===============================
Google Sheets (Sessions) から移行した読書データを
Claude Desktop から自然言語で操作するためのMCPサーバー。

前提:
  - Python 3.11+
  - uv がインストール済み (brew install uv)

セットアップ:
  cd /Volumes/SSD001/Dev/AIエージェント/読書用エージェント/mcp
  uv init --bare
  uv add "mcp[cli]" httpx

起動確認:
  uv run fastmcp dev server.py

Claude Desktop への登録:
  claude mcp add-json book-manager --scope user '{
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "--with", "httpx",
             "fastmcp", "run",
             "/Volumes/SSD001/Dev/AIエージェント/読書用エージェント/mcp/server.py"]
  }'
"""

import json
import uuid
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ============================================================
# 設定
# ============================================================

MCP_NAME = "book-manager"

# データファイルパス（同ディレクトリの books.json）
DATA_PATH = Path(__file__).parent / "books.json"

# Gemini API（オプション）
GEMINI_API_KEY: str = ""  # 環境変数 GEMINI_API_KEY から読み込む
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

mcp = FastMCP(MCP_NAME)

# ============================================================
# データ読み書きユーティリティ
# ============================================================

def _load() -> list[dict]:
    """books.json を読み込む。ファイルがなければ空リストを返す。"""
    if not DATA_PATH.exists():
        return []
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(sessions: list[dict]) -> None:
    """sessions リストを books.json に書き込む。"""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ============================================================
# ツール定義
# ============================================================

@mcp.tool()
def add_book(
    title: str,
    purpose: str = "",
    memo: str = "",
    answer: str = "",
    mode: str = "初回",
    date: Optional[str] = None,
    book_id: Optional[str] = None,
) -> str:
    """
    本・セッションを追加する。
    Google Sheets の runAgent() 実行後の Session保存に相当。

    Args:
        title:   本のタイトル（必須）
        purpose: 読書の目的・問い
        memo:    読書メモ（OCR結果や手入力）
        answer:  回答・気づき
        mode:    モード（初回 / 通常 / 解答後）
        date:    日付 (YYYY-MM-DD)。省略すると今日
        book_id: 同一本の別セッションをまとめる ID。省略すると自動生成
    """
    sessions = _load()

    # 同タイトルの既存 book_id を引き継ぐ（省略時）
    if not book_id:
        for s in sessions:
            if s.get("タイトル") == title:
                book_id = s.get("book_id", "")
                break
    if not book_id:
        book_id = str(uuid.uuid4())[:8]

    session_id = str(uuid.uuid4())
    entry = {
        "session_id": session_id,
        "日付": date or _today(),
        "book_id": book_id,
        "タイトル": title,
        "目的": purpose,
        "メモ": memo,
        "回答": answer,
        "モード": mode,
    }
    sessions.append(entry)
    _save(sessions)
    return f"✅ 登録しました（session_id: {session_id} / book_id: {book_id}）"


@mcp.tool()
def search_books(
    query: str = "",
    date: Optional[str] = None,
    mode: Optional[str] = None,
) -> str:
    """
    読書セッションをキーワード・日付・モードで検索する。

    Args:
        query: タイトル・目的・メモ・回答を横断検索するキーワード（省略可）
        date:  日付で絞り込む (YYYY-MM-DD)（省略可）
        mode:  モード（初回 / 通常 / 解答後）で絞り込む（省略可）
    """
    sessions = _load()
    results = []

    for s in sessions:
        if date and s.get("日付", "") != date:
            continue
        if mode and s.get("モード", "") != mode:
            continue
        if query:
            haystack = " ".join([
                s.get("タイトル", ""),
                s.get("目的", ""),
                s.get("メモ", ""),
                s.get("回答", ""),
            ]).lower()
            if query.lower() not in haystack:
                continue
        results.append(s)

    if not results:
        return "該当するセッションが見つかりませんでした。"

    lines = [f"🔍 {len(results)}件ヒット\n"]
    for s in results[-20:]:  # 最新20件
        lines.append(
            f"📖 {s['日付']} | {s['タイトル']} | {s['モード']}\n"
            f"   目的: {s.get('目的','（なし）')}\n"
            f"   session_id: {s['session_id']}\n"
        )
    return "\n".join(lines)


@mcp.tool()
def get_sessions(
    title: Optional[str] = None,
    date: Optional[str] = None,
    limit: int = 10,
) -> str:
    """
    セッション一覧を取得する。Google Sheets の Sessions シート参照に相当。

    Args:
        title: タイトルで絞り込む（省略可）
        date:  日付で絞り込む（省略可）
        limit: 最大表示件数（デフォルト10）
    """
    sessions = _load()

    filtered = [
        s for s in sessions
        if (not title or s.get("タイトル") == title)
        and (not date or s.get("日付") == date)
    ]

    if not filtered:
        return "セッションが見つかりませんでした。"

    recent = filtered[-limit:][::-1]
    lines = [f"📚 {len(filtered)}件中 最新{len(recent)}件\n"]
    for s in recent:
        lines.append(
            f"[{s['日付']}] {s['タイトル']} ({s['モード']})\n"
            f"  目的: {s.get('目的','')}\n"
            f"  session_id: {s['session_id']}\n"
        )
    return "\n".join(lines)


@mcp.tool()
def add_memo(
    session_id: str,
    memo: str,
    append: bool = True,
) -> str:
    """
    既存セッションにメモを追加・上書きする。
    Google Sheets の D2（メモ欄）書き込みに相当。

    Args:
        session_id: 対象セッションID（search_books や get_sessions で確認）
        memo:       追加または上書きするメモ内容
        append:     True=追記、False=上書き（デフォルト: 追記）
    """
    sessions = _load()
    for s in sessions:
        if s.get("session_id") == session_id:
            if append and s.get("メモ"):
                s["メモ"] = s["メモ"] + "\n\n" + memo
            else:
                s["メモ"] = memo
            _save(sessions)
            return f"✅ メモを{'追記' if append else '上書き'}しました（{s['タイトル']}）"
    return f"⚠️ session_id '{session_id}' が見つかりませんでした。"


@mcp.tool()
async def get_flashcards(session_id: str) -> str:
    """
    セッションのメモからフラッシュカードを生成する（Gemini API使用）。
    Gemini APIキーが未設定の場合はメモをそのまま返す。

    Args:
        session_id: 対象セッションID
    """
    import os
    sessions = _load()
    session = next((s for s in sessions if s.get("session_id") == session_id), None)

    if not session:
        return f"⚠️ session_id '{session_id}' が見つかりませんでした。"

    memo = session.get("メモ", "")
    if not memo:
        return "⚠️ このセッションにはメモがありません。"

    api_key = os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
    if not api_key:
        return f"（Gemini APIキー未設定のため、メモをそのまま返します）\n\n{memo}"

    prompt = f"""以下の読書メモから、重要な概念・知識のフラッシュカードを5〜10枚作成してください。

出力形式（各カードを以下の形式で）:
Q: 質問
A: 答え

読書メモ:
{memo}"""

    return await _call_gemini(api_key, prompt)


@mcp.tool()
async def get_challenge(session_id: str) -> str:
    """
    セッションのメモから7日間アクションチャレンジを生成する（Gemini API使用）。

    Args:
        session_id: 対象セッションID
    """
    import os
    sessions = _load()
    session = next((s for s in sessions if s.get("session_id") == session_id), None)

    if not session:
        return f"⚠️ session_id '{session_id}' が見つかりませんでした。"

    memo = session.get("メモ", "")
    purpose = session.get("目的", "")
    if not memo:
        return "⚠️ このセッションにはメモがありません。"

    api_key = os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
    if not api_key:
        return "⚠️ Gemini APIキーが設定されていません。環境変数 GEMINI_API_KEY を設定してください。"

    prompt = f"""以下の読書メモと目的をもとに、7日間の具体的なアクションチャレンジを作成してください。

読書の目的: {purpose}
読書メモ:
{memo}

出力形式:
Day 1: （具体的なアクション）
Day 2: ...
...
Day 7: ...

最後に「継続のポイント」を1〜2文で追加してください。"""

    return await _call_gemini(api_key, prompt)


@mcp.tool()
def get_stats() -> str:
    """
    読書統計を表示する。総冊数・セッション数・モード別件数・最近の読書など。
    """
    sessions = _load()
    if not sessions:
        return "まだセッションが登録されていません。"

    total_sessions = len(sessions)
    titles = list({s.get("タイトル", "") for s in sessions if s.get("タイトル")})
    total_books = len(titles)

    mode_counts: dict[str, int] = {}
    for s in sessions:
        m = s.get("モード", "不明")
        mode_counts[m] = mode_counts.get(m, 0) + 1

    recent = sorted(sessions, key=lambda s: s.get("日付", ""), reverse=True)[:5]
    recent_lines = [f"  {s['日付']} {s['タイトル']} ({s['モード']})" for s in recent]

    mode_text = " / ".join(f"{k}: {v}件" for k, v in mode_counts.items())

    return (
        f"📊 読書統計\n"
        f"  登録冊数: {total_books}冊\n"
        f"  総セッション数: {total_sessions}件\n"
        f"  モード内訳: {mode_text}\n\n"
        f"📖 最近の読書（最新5件）\n" + "\n".join(recent_lines)
    )


@mcp.tool()
def migrate_from_sheets(csv_text: str) -> str:
    """
    Google Sheets からエクスポートしたCSVを books.json に移行する。

    使い方:
        1. Google Sheets の Sessions シートを「ファイル → ダウンロード → CSV」でエクスポート
        2. CSVの内容をそのままこのツールに渡す

    想定CSVヘッダー:
        session_id, 日付, book_id, タイトル, 目的, メモ, 回答, モード

    Args:
        csv_text: CSVファイルの内容（テキスト全体）
    """
    existing = _load()
    existing_ids = {s.get("session_id") for s in existing}

    reader = csv.DictReader(io.StringIO(csv_text))
    new_entries = []
    skipped = 0

    for row in reader:
        sid = row.get("session_id", "").strip()
        if not sid:
            sid = str(uuid.uuid4())

        if sid in existing_ids:
            skipped += 1
            continue

        entry = {
            "session_id": sid,
            "日付":   row.get("日付", "").strip(),
            "book_id": row.get("book_id", str(uuid.uuid4())[:8]).strip(),
            "タイトル": row.get("タイトル", "").strip(),
            "目的":   row.get("目的", "").strip(),
            "メモ":   row.get("メモ", "").strip(),
            "回答":   row.get("回答", "").strip(),
            "モード": row.get("モード", "初回").strip(),
        }
        new_entries.append(entry)
        existing_ids.add(sid)

    all_sessions = existing + new_entries
    _save(all_sessions)

    return (
        f"✅ 移行完了\n"
        f"  新規追加: {len(new_entries)}件\n"
        f"  重複スキップ: {skipped}件\n"
        f"  合計セッション数: {len(all_sessions)}件\n"
        f"  保存先: {DATA_PATH}"
    )


# ============================================================
# Gemini API ヘルパー
# ============================================================

async def _call_gemini(api_key: str, prompt: str) -> str:
    """Gemini API にテキスト生成リクエストを送る。"""
    try:
        import httpx
    except ImportError:
        return "⚠️ httpx がインストールされていません。`uv add httpx` を実行してください。"

    url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            url,
            headers={"x-goog-api-key": api_key},
            json=payload,
        )
    if res.status_code != 200:
        return f"⚠️ Gemini API エラー (HTTP {res.status_code}): {res.text}"

    data = res.json()
    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    return text.strip() if text else "⚠️ Gemini API の応答が空でした。"


# ============================================================
# エントリポイント
# ============================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
