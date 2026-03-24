# Book Manager AI開発ルール

---

## 1. プロジェクト概要

### 目的
読書AIエージェント（Book Manager）は、Google Sheetsをベースに読書メモの管理・AI分析・フラッシュカード生成・セッション管理を行うツール。

### 使用技術
- **Google Sheets** — UI・データ管理
- **Google Apps Script（clasp）** — バックエンドロジック
- **Gemini API（Gemini Vision含む）** — AI生成・画像認識
- **Google Drive API v2** — 画像ファイル取得
- **clasp** — ローカル開発・デプロイ

### プロジェクト情報
- **プロジェクトパス:** `~/book-manager`
- **スプレッドシート:** `https://docs.google.com/spreadsheets/d/1V81UwPpH2iuqEEQQRohWrr18-eR5Szi8bUC1l9CnoHA/edit`

---

## 2. AI作業ルール

### コード修正ルール
- **修正は最小限に留める**
  - 変更が必要な関数・箇所のみを修正する
  - ファイル全体を書き直さない
  - 関係のない関数・変数には触れない
- 修正前に必ず「何をどこを変えるか」を明示してから実行する
- 変更箇所にはコメントで `// [修正] 理由` を添える

### 削除ルール
- **ファイル削除が必要な場合は必ず確認を取ること**
  - 削除対象のファイル名・パスを提示し、ユーザーの承認を得てから削除する
  - `rm -rf` などの一括削除は禁止
  - 削除前に対象を `ls` で再確認する

### 変更時ルール
- このファイル（MDファイル）をClaude Codeに読み込ませてから作業を開始すること
- 指示はこのファイルの内容に従うこと
- 修正後は対象ファイルを `cat` で表示して変更が正しく反映されているか確認する

---

## 3. デプロイルール

### 保存
- コードを修正・追加・削除した場合は**必ずファイルを保存してから** `clasp push` すること

### clasp push
```bash
cd ~/book-manager
clasp push
```

### 動作確認
- `clasp push` 完了後、スプレッドシートをリロードして動作確認する
- メニュー「読書AIエージェント」→「初期設定」を実行してレイアウトを再描画する

---

## 4. プロジェクト構成

### ディレクトリ
```
~/book-manager/
├── appsscript.json
├── 00_config.gs
├── 01_ui_input.gs
├── 02_onedit.gs
├── 03_run_agent.gs
├── 04_db_fix.gs
├── 05_gemini.gs
├── 06_ocr_import.gs
└── 99_utils.gs
```

### Apps Scriptファイル構成

| ファイル | 役割 |
|---|---|
| `00_config.gs` | 設定・定数 |
| `01_ui_input.gs` | UI構築・セッション関数 |
| `02_onedit.gs` | onOpen / onEdit トリガー |
| `03_run_agent.gs` | エージェント実行 |
| `04_db_fix.gs` | DB修正 |
| `05_gemini.gs` | Gemini API呼び出し |
| `06_ocr_import.gs` | AI画像認識・取り込み |
| `99_utils.gs` | ユーティリティ |

### appsscript.json（現在の権限設定）
```json
{
  "timeZone": "Asia/Tokyo",
  "dependencies": {
    "enabledAdvancedServices": [
      { "userSymbol": "Drive", "serviceId": "drive", "version": "v2" }
    ]
  },
  "oauthScopes": [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/script.triggers",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/script.external_request"
  ],
  "exceptionLogging": "STACKDRIVER",
  "runtimeVersion": "V8"
}
```

---

## 5. Input UI仕様

### セル構造

| セル | 内容 |
|---|---|
| A2 | 日付（プルダウン：Sessions日付一覧 / 表示形式: `yyyy-MM-dd`） |
| B2 | タイトル（プルダウン：日付で絞り込み） |
| C2 | 目的 |
| D2 | メモ（AI画像認識結果の書き込み先） |
| E2 | 回答 |
| F2 | モード（初回 / 通常 / 解答後） |
| G1 | 画像フォルダへのハイパーリンク（`📁 画像フォルダを開く`） |
| G2 | AI画像認識用URL（Google DriveのURL / タイトル変更時に自動クリア） |

### ボタン仕様（B4:F4 / B5:F5）

| セル | ラベル | 動作 |
|---|---|---|
| B5 | 生成実行 | `runAgent()` を実行 |
| C5 | AI画像認識 | G2のURLを読んでAI画像認識を実行 |
| D5 | クリア | C2:G2をクリア |
| E5 | （空） | 何もしない |
| F5 | （空） | 何もしない |

**`handleInputButtons_` の実装（現在の仕様）:**
```javascript
function handleInputButtons_(a1) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = mustOrCreateSheet_(ss, SHEETS.INPUT);

  try {
    if (a1 === "B5") {
      runAgent();                          // [修正] 生成実行
    } else if (a1 === "C5") {
      triggerOcrFromG2_(sh);              // [修正] AI画像認識（G2のURL参照）
    } else if (a1 === "D5") {
      clearInputFields_(sh);              // [修正] 入力項目クリア
    }
    // E5/F5は何もしない
  } finally {
    setInternalEdit_(1200);
    sh.getRange(a1).setValue(false);
  }
}

/** G2のURLを読んでAI画像認識を実行 */
function triggerOcrFromG2_(sh) {
  const url = String(sh.getRange("G2").getValue() || "").trim();
  if (!url) {
    setStatus_("⚠️ G2にURLが入力されていません");
    return;
  }
  importMemoFromUrl_(url);
}

/** 入力項目クリア（C2:G2） */
function clearInputFields_(sh) {
  withInternalEdit_(() => {
    sh.getRange("C2:G2").clearContent();
  });
  setStatus_("🧹 入力項目をクリアしました");
}
```

---

## 6. AI画像認識仕様

### 処理概要
- 従来のDrive OCR（`Drive.Files.copy + ocr:true`方式）ではなく**Gemini Vision API**で画像を直接解析する
- HEIC形式（iPhoneの写真）・手書きメモにも対応
- 結果はD2（メモ欄）に追記される

### URL入力
- G2セルにGoogle DriveのURLを貼り付ける
- 複数URLは改行・カンマ・空白で区切って入力可能
- URLはC5ボタン（AI画像認識）を押した時のみ処理される（G2編集時の自動実行はしない）
- fileIdで重複排除、1件失敗しても残りを続行
- 完了後「N件完了 / M件エラー」形式でステータス表示

### Gemini Vision実装（`06_ocr_import.gs`）
```javascript
/** Gemini Vision APIで画像を直接解析してテキストを返す */
function analyzeImageWithGemini_(file) {
  const apiKey = getApiKey_();
  let model = getModel_();
  if (!String(model).startsWith("models/")) model = "models/" + model;

  const blob = file.getBlob();
  const base64 = Utilities.base64Encode(blob.getBytes());
  const mimeType = blob.getContentType() || file.getMimeType();

  const url = `${CONFIG.API_BASE}/${model}:generateContent`;

  const payload = {
    contents: [{
      role: "user",
      parts: [
        { inlineData: { mimeType: mimeType, data: base64 } },
        { text: "この画像は読書メモや本のページです。書かれているテキストをすべて正確に読み取ってください。手書きの場合も可能な限り読み取ってください。テキスト以外の説明は不要です。" }
      ]
    }],
    generationConfig: { temperature: 0.1, maxOutputTokens: 2048 }
  };

  const res = UrlFetchApp.fetch(url, {
    method: "post",
    headers: { "x-goog-api-key": apiKey },
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const status = res.getResponseCode();
  const body = res.getContentText();
  if (status < 200 || status >= 300) {
    throw new Error(`Gemini Vision エラー（HTTP ${status}）: ${body}`);
  }

  const json = JSON.parse(body);
  const text = json?.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error("Gemini Visionの応答が空でした");

  return text.trim().substring(0, OCR_MAX_CHARS);
}
```

**`importMemoFromUrl_` 内の呼び出し（現在の仕様）:**
```javascript
// Drive OCRではなくGemini Visionで解析
const text = analyzeImageWithGemini_(file);  // [修正] Drive OCR→Gemini Vision
```

---

## 7. Sessions仕様

### 保存内容
Sessionsシートのヘッダ構造（`DB_HEADERS.SESSIONS`）:
```
["session_id", "日付", "book_id", "タイトル", "目的", "メモ", "回答", "モード"]
```

`runAgent()` 実行成功後に自動でSessionsへスナップショット保存:
```javascript
// [追加] Sessionsにスナップショット保存
const _sessDate = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy-MM-dd");
saveSession_(ss, bookId, title, purpose, memo, answers, mode, new Date());
refreshDateDropdown_(ss);
```

**`saveSession_` の実装（`01_ui_input.gs`）:**
```javascript
/** Sessionsシートに現在のInput内容を保存 */
function saveSession_(ss, bookId, title, purpose, memo, answers, mode, date) {
  const sheet = mustOrCreateSheet_(ss, SHEETS.SESSIONS);
  initSessionsHeaderIfNeeded_(sheet);
  const sessionId = Utilities.getUuid();
  const dateStr = Utilities.formatDate(date || new Date(), "Asia/Tokyo", "yyyy-MM-dd");
  sheet.appendRow([sessionId, dateStr, bookId, title, purpose, memo, answers, mode]);
}
```

### 日付フィルタ
- A2（日付）はSessionsの日付一覧をプルダウンで表示（新しい順）
- 今日の日付は常に先頭に追加
- A2で日付を選択するとB2のタイトルプルダウンが絞り込まれる

**`filterTitlesByDate_` の実装（`01_ui_input.gs`）:**
```javascript
/** 指定日付に紐づくタイトル一覧でB2のプルダウンを絞り込む */
function filterTitlesByDate_(ss, dateStr) {
  const sheet = mustOrCreateSheet_(ss, SHEETS.SESSIONS);
  const data = sheet.getDataRange().getValues();
  const titles = [...new Set(
    data.slice(1)
      .filter(r => String(r[1] || "").trim() === dateStr)
      .map(r => String(r[3] || "").trim())
      .filter(t => t.length > 0)
  )];

  const input = mustOrCreateSheet_(ss, SHEETS.INPUT);
  const cell = input.getRange(INPUT_UI.TITLE);

  if (titles.length === 0) {
    ensureInputTitleValidation_(ss);
    return;
  }

  cell.setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(titles, true)
      .setAllowInvalid(true)
      .build()
  );
}
```

### 復元処理
- B2でタイトルを選択すると、該当セッションの目的・メモ・回答・モードをInputに復元
- 対象セル: `INPUT_UI.PURPOSE` / `INPUT_UI.MEMO` / `INPUT_UI.ANSWERS` / `INPUT_UI.MODE`

**`restoreSessionToInput_` の実装（`01_ui_input.gs`）:**
```javascript
/** 指定日付・タイトルのSessionをInputに復元 */
function restoreSessionToInput_(ss, dateStr, title) {
  const sheet = mustOrCreateSheet_(ss, SHEETS.SESSIONS);
  const data = sheet.getDataRange().getValues();
  const row = data.slice(1).find(r =>
    String(r[1] || "").trim() === dateStr &&
    String(r[3] || "").trim() === title
  );
  if (!row) return;

  const input = mustOrCreateSheet_(ss, SHEETS.INPUT);
  withInternalEdit_(() => {
    input.getRange(INPUT_UI.PURPOSE).setValue(row[4] || "");
    input.getRange(INPUT_UI.MEMO).setValue(row[5] || "");
    input.getRange(INPUT_UI.ANSWERS).setValue(row[6] || "");
    input.getRange(INPUT_UI.MODE).setValue(row[7] || "初回");
  });
  setStatus_("📂 セッションを復元しました（" + dateStr + " / " + title + "）");
}
```

**`02_onedit.gs` のトリガー処理（現在の仕様）:**
```javascript
function onEditInstalled(e) {
  try {
    if (!e || !e.range) return;
    if (isInternalEdit_()) return;

    const range = e.range;
    const sheet = range.getSheet();
    const a1 = range.getA1Notation();

    if (sheet.getName() !== SHEETS.INPUT) return;

    // チェックボックス（B5~D5）処理
    if (INPUT_UI.BTN_A1S.includes(a1) && String(e.value).toUpperCase() === "TRUE") {
      handleInputButtons_(a1);
      return;
    }

    // A2変更 → B2プルダウンを日付で絞り込む
    if (a1 === INPUT_UI.DATE) {
      const dateStr = String(e.value || "").trim();
      if (dateStr) filterTitlesByDate_(e.source, dateStr);
      return;
    }

    // B2変更 → Sessionを復元（日付が選択済みの場合のみ）
    if (a1 === INPUT_UI.TITLE) {
      handleInputTitleEdit_(e);
      const dateStr = String(e.source.getSheetByName(SHEETS.INPUT)
        .getRange(INPUT_UI.DATE).getDisplayValue() || "").trim();
      const title = String(e.value || "").trim();
      if (dateStr && title) restoreSessionToInput_(e.source, dateStr, title);
      return;
    }

  } catch (err) {
    console.error(err);
    try { setStatus_("⚠️ 処理でエラーが発生しました（ログ確認）"); } catch (_) {}
  }
}
```

---

## 8. 動作確認手順

### clasp push
```bash
cd ~/book-manager
clasp push
```

### 動作チェック
1. スプレッドシートをリロード
2. メニュー「読書AIエージェント」→「初期設定」を実行してレイアウトを再描画
3. B5（生成実行）チェック → `runAgent()` が走るか確認
4. C5（AI画像認識）チェック → G2のURLを読んでD2に反映されるか確認
5. D5（クリア）チェック → C2:G2がクリアされるか確認
6. A2で日付を選択 → B2プルダウンが絞り込まれるか確認
7. B2でタイトルを選択 → C2〜F2が復元されるか確認
8. runAgent実行後 → Sessionsシートに1行保存されるか確認
