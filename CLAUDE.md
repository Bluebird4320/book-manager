# Book Manager 開発ルール（CLAUDE.md）

このファイルをClaude Codeに読み込ませてから作業を開始すること。

---

## プロジェクト概要

| 項目 | 内容 |
|------|------|
| アプリ名 | 読書ノート（Book Manager） |
| リポジトリ | https://github.com/Bluebird4320/book-manager |
| 公開URL | https://bluebird4320.github.io/book-manager/ |
| 構成 | 単一HTMLファイル（index.html）+ MCPサーバー（mcp/server.py） |
| データ | localStorage（WEBアプリ）/ books.json（MCPサーバー） |
| AI | Gemini API（gemini-2.0-flash） |
| ホスティング | GitHub Pages（Private / Pro） |

---

## ディレクトリ構成

```
/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/
├── index.html          ← WEBアプリ本体（GitHub Pages）
├── CLAUDE.md           ← このファイル
├── .gitignore
└── mcp/
    ├── server.py       ← MCPサーバー本体（FastMCP / Python）
    ├── books.json      ← ローカルDB（.gitignore済み）
    ├── pyproject.toml
    └── .venv/
```

---

## 開発チーム構成

Claude Codeのサブエージェント機能を使い、以下の3役割で開発を進める。
各エージェントは**自分の役割以外の作業をしてはいけない**。

---

### Agent 1：Coder（コーディング担当）

**役割:** 新機能の実装・バグ修正のコーディングのみ

**できること:**
- `index.html` / `mcp/server.py` の編集・追記
- 新機能のコード生成・バグ修正

**してはいけないこと:**
- `git add` / `commit` / `push`（Deployerの担当）
- ファイルの削除（必ずユーザーに確認を取る）
- Reviewerの確認前に「完了」とみなすこと

**コーディング規約:**
- 修正は最小限に留める（関係のない関数・変数には触れない）
- 修正前に「何をどこを変えるか」を必ず明示する
- 変更箇所には `// [修正] 理由` のコメントを添える
- ファイル全体を書き直さない

**作業完了の合図:**
```
[Coder完了] 実装内容：〇〇
変更ファイル：index.html（〇〇行付近）
Reviewerによる確認をお願いします。
```

---

### Agent 2：Reviewer（レビュー・テスト担当）

**役割:** コードレビューと動作確認のみ

**できること:**
- コードの問題点・改善点の指摘
- 動作確認手順の提示・バグの発見と報告

**してはいけないこと:**
- コードの修正（Coderの担当）
- `git push`（Deployerの担当）
- OKを出さずに次の工程へ進めること

**レビューチェックリスト:**
- [ ] 既存機能が壊れていないか
- [ ] モバイル・PC両対応か
- [ ] APIキーがコードに含まれていないか
- [ ] localStorageへの保存・読み込みが正しいか
- [ ] エラーハンドリングが適切か

**作業完了の合図:**
```
[Reviewer完了] レビュー結果：OK / NG
指摘事項：〇〇（NGの場合）
Deployerへの引き継ぎ：OK（OKの場合のみ）
```

---

### Agent 3：Deployer（実装・プッシュ担当）

**役割:** git操作とデプロイのみ

**できること:**
- `git add` / `commit` / `push`
- GitHub Pagesへのデプロイ確認

**してはいけないこと:**
- コードの修正（Coderの担当）
- Reviewerの承認なしにpushすること

**コミットメッセージのルール:**
```
feat:     新機能追加
fix:      バグ修正
refactor: リファクタリング
docs:     ドキュメント更新
style:    UIの変更
```

**デプロイ手順:**
```bash
cd "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント"
git add index.html
git commit -m "feat: 変更内容の説明"
git push
```

**作業完了の合図:**
```
[Deployer完了] pushしました。
コミット：〇〇
URL：https://bluebird4320.github.io/book-manager/
```

---

## 開発フロー

```
ユーザー（指示）
    ↓
Coder（実装）→ [Coder完了] を宣言
    ↓
Reviewer（確認）→ [Reviewer完了 OK] を宣言
    ↓
Deployer（push）→ [Deployer完了] を宣言
    ↓
ユーザー（動作確認）
```

NGが出た場合：
```
Reviewer（NG）→ Coderに差し戻し → 再実装 → 再レビュー → Deployer
```

---

## 削除ルール（全エージェント共通）

- ファイル削除が必要な場合は必ずユーザーに確認を取ること
- 削除対象のファイル名・パスを提示し、承認を得てから実行
- `rm -rf` などの一括削除は禁止
- 削除前に `ls` で対象を再確認する

---

## WEBアプリ仕様（index.html）

### 画面構成（5画面）

| 画面 | 機能 |
|------|------|
| 本棚 | 読書ログカレンダー・本一覧（PC：2カラム）・検索 |
| 登録 | 手入力 / 画像OCR（端末アップロード・Googleドライブ連携） |
| 目標 | 7日間チャレンジ・月間目標・長期目標（1ヶ月〜1年） |
| 統計 | 月別グラフ・モード別・最近の読書 |
| 設定 | APIキー保存・JSONエクスポート/インポート |

### データ構造（localStorage）

```javascript
// sessions（読書記録）
[{ session_id, 日付, book_id, タイトル, 目的, メモ, 回答, モード }]

// goals（目標・チャレンジ）
[{
  type,      // weekly / monthly / longterm / flashcard
  book_id,   // 関連する本（任意）
  text,      // 目標内容
  period,    // 期間
  deadline,  // 期限
  items,     // [{day, text, done}]（weeklyのみ）
  cards,     // [{q, a}]（flashcardのみ）
  created
}]
```

### Gemini API設定

- モデル：`gemini-2.0-flash`
- APIキー：`localStorage` に保存（コードに絶対書かない）
- 用途：OCR（Vision）・フラッシュカード生成・チャレンジ生成

### OCRフロー

```
【端末アップロード】
ファイル選択 → Canvas で長辺1200px以下にリサイズ
→ Base64変換 → Gemini Vision API → メモ欄に反映

【Googleドライブ】
「ドライブを開く」ボタン → フォルダが新タブで開く
（URL: https://drive.google.com/drive/folders/1K450s27GlW3DI9fmkno21sWSg9EA1olL）
→ ファイルのURLをコピー → URL入力欄に貼り付け → OCR解析
```

### レスポンシブ対応

| 画面幅 | レイアウト |
|--------|-----------|
| PC（768px以上） | 左サイドバーナビ・2カラムグリッド |
| スマホ（767px以下） | ボトムナビ・1カラム |

---

## MCPサーバー仕様（mcp/server.py）

### 接続コマンド
```bash
claude mcp add-json book-manager --scope user '{
  "command": "uv",
  "args": [
    "run", "--project",
    "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp",
    "python",
    "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp/server.py"
  ]
}'
```

### ツール一覧（8本）

| ツール名 | 機能 |
|----------|------|
| `add_book` | 本・セッション登録 |
| `search_books` | タイトル・目的・メモで検索 |
| `get_sessions` | セッション一覧取得 |
| `add_memo` | メモ追加・上書き |
| `get_flashcards` | フラッシュカード生成（Gemini） |
| `get_challenge` | 7日間チャレンジ生成（Gemini） |
| `get_stats` | 読書統計 |
| `migrate_from_sheets` | CSV → books.json 移行 |

---

## 今後の予定

- [ ] OCR精度の改善
- [ ] 長期目標のリマインド（Googleカレンダー連携）
- [ ] 読書統計グラフの強化
- [ ] 関連本レコメンド機能（Gemini）
- [ ] バックエンド追加によるGoogleドライブ直接連携
