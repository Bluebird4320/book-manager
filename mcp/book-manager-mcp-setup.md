# 読書AIエージェント MCPサーバー セットアップ記録

作成日: 2026-03-22

---

## 概要

Google Sheets ベースの読書AIエージェント（Book Manager）を、
Claude Desktop から自然言語で操作できるよう MCP サーバー化した作業記録。

---

## 構成

```
Claude Desktop
    ↕ stdio
MCP Server (server.py / Python / FastMCP)
    ↕ 読み書き
books.json（ローカルDB / SSD001）
    ↕ オプション
Gemini API（フラッシュカード・チャレンジ生成）
```

### ファイル構成

```
/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp/
├── server.py        ← MCPサーバー本体
├── books.json       ← データストア（Google Sheets 移行先）
├── pyproject.toml   ← uv プロジェクト設定
└── .venv/           ← 仮想環境
```

---

## MCPツール一覧（8本）

| ツール名 | 機能 | 元のGAS機能との対応 |
|----------|------|-------------------|
| `add_book` | 本・セッション登録 | `saveSession_()` |
| `search_books` | タイトル・目的・メモで検索 | Sessions シート検索 |
| `get_sessions` | セッション一覧取得 | Sessions シート参照 |
| `add_memo` | メモ追加・上書き | D2（メモ欄）書き込み |
| `get_flashcards` | フラッシュカード生成（Gemini） | Gemini API呼び出し |
| `get_challenge` | 7日間チャレンジ生成（Gemini） | Gemini API呼び出し |
| `get_stats` | 読書統計（冊数・モード別等） | — |
| `migrate_from_sheets` | CSV → books.json 一括移行 | — |

---

## データ構造（books.json）

Google Sheets の Sessions シートと同一構造。

```json
[
  {
    "session_id": "uuid",
    "日付": "2026-03-22",
    "book_id": "abc12345",
    "タイトル": "本のタイトル",
    "目的": "読書の目的・問い",
    "メモ": "読書メモ（OCR結果等）",
    "回答": "気づき・回答",
    "モード": "初回 / 通常 / 解答後"
  }
]
```

---

## セットアップ手順

### 前提条件
- Python 3.11+
- uv インストール済み（`brew install uv`）
- Claude Code インストール済み

### ① フォルダ作成・ファイル配置

```bash
mkdir -p "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp"
# server.py を ~/Downloads から移動
mv ~/Downloads/server.py "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp/"
```

### ② uv 初期化・パッケージインストール

```bash
cd "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp"
uv init --bare
uv add "mcp[cli]" httpx fastmcp
```

**インストールされる主なパッケージ:**
- `mcp[cli]` 1.26.0
- `httpx` 0.28.1
- `fastmcp` 3.1.1

### ③ 起動確認

```bash
cd "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp"
uv run fastmcp run server.py
# → INFO: Uvicorn running on http://127.0.0.1:8000 が出ればOK
# Ctrl+C で終了
```

### ④ Claude Code / Claude Desktop に登録

```bash
claude mcp add-json book-manager --scope user '{
  "command": "uv",
  "args": [
    "run",
    "--project",
    "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp",
    "python",
    "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp/server.py"
  ]
}'
```

### ⑤ 接続確認

```bash
claude mcp list
# book-manager: ... - ✓ Connected  が出ればOK
```

### ⑥ Gemini API キー設定（オプション）

フラッシュカード・チャレンジ機能を使う場合は `~/.zshrc` に追記：

```bash
export GEMINI_API_KEY="your-api-key"
```

---

## トラブルシューティング

### `fastmcp: No such file or directory`
→ `fastmcp` が未インストール。`uv add fastmcp` を実行。

### `No module named mcp.__main__`
→ `fastmcp run server.py` で起動する（`python -m mcp` は不可）。

### `Failed to connect` のまま
→ `server.py` 末尾の `mcp.run()` を `mcp.run(transport="stdio")` に変更。
→ 登録コマンドを `uv run --project ... python server.py` 形式に変更。

### `fastmcp dev server.py` が `Unknown command "server.py"`
→ fastmcp 3.x では `dev` サブコマンドが `inspector` に変更された。
→ 動作確認は `fastmcp run server.py` を使う。

---

## Google Sheets からのデータ移行

1. Google Sheets の Sessions シートを開く
2. `ファイル → ダウンロード → カンマ区切り形式（CSV）`
3. Claude Desktop で以下のように話しかける：

> 「Sessionsシートの内容をCSVでエクスポートしたので移行して」
> → CSV の内容をそのまま貼り付ける

---

## 今後の予定

- [ ] Google Sheets CSVデータの移行実施
- [ ] Claude Desktop での動作確認・テスト
- [ ] GitHub Pages WEBアプリ化（全体設計済み）
