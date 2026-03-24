# Book Manager 開発履歴

このファイルは開発の変更履歴とコードスニペットのアーカイブです。
現在の仕様は `book-manager-dev-rules.md` を参照してください。

---

## セッション一覧

| 日付 | 内容 |
|---|---|
| 2026-03-01頃 | 初期構成・Drive OCR実装・フォルダ自動スキャン |
| 2026-03-04 | Drive OCR → Gemini Vision移行・ボタン3つに整理・複数URL対応 |
| 2026-03-05 | Sessionsシート追加・日付プルダウン・入力復元・UI改善 |

---

## v0: 初期構成（〜2026-03-03）

### 概要
- Google Sheets + Apps Script + Gemini APIで読書AIエージェントを構築
- G2にGoogle DriveのURLを貼るとOCRしてD2に読書メモを反映
- OCRは `Drive.Files.copy + ocr:true` 方式
- フォルダ自動スキャン（`importMemoFromFolder`）を30分トリガーで実行
- ボタン構成: 初期設定 / 接続テスト / 生成実行 / 最新表示 / レイアウト修復（B5〜F5）

### 判明した問題点
- **HEIC非対応**: `Drive.Files.copy` のOCRはJPEG・PNG・GIF・PDFのみ対応。iPhoneのHEICは変換エラー
- **G2無視バグ**: 30分トリガーの `importMemoFromFolder` が独立して動き、G2に貼ったURL以外のファイルが読み込まれる（`OCR_DONE_FOLDER_ID` 未設定でファイルが移動されず再取り込みが発生）
- **チェックボックス無効**: `onEditInstalled` がG2専用になっており、B5〜F5チェックボックスが弾かれていた

---

## v1: Drive OCR → Gemini Vision移行（2026-03-04）

### 変更内容

#### `06_ocr_import.gs` — Gemini Vision対応

**変更理由**: Drive OCRはHEIC非対応のため、すでに使用中のGemini APIで画像を直接読む方式に変更。

```javascript
// 変更前（ocrFile_ 呼び出し）
const text = ocrFile_(file);

// 変更後（Gemini Vision呼び出し）
const text = analyzeImageWithGemini_(file);  // [修正] Drive OCR→Gemini Vision
```

**追加関数 `analyzeImageWithGemini_`（06_ocr_import.gs末尾に追記）:**
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

#### `appsscript.json` — Drive権限追加

**変更理由**: `DriveApp.getFileById` 呼び出し時に権限エラーが発生したため。

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

#### `importMemoFromFolder` 30分トリガーを停止

**変更理由**: G2に貼ったURL以外のファイルが読み込まれるバグの根本原因。G2ボタン起動方式に統一。

- メニュー「読書AIエージェント」→「自動取り込みトリガーを削除」を実行して停止

#### `01_ui_input.gs` — ボタンを3つに整理

**変更前のボタン構成（B5〜F5）:**

| セル | ラベル | 処理 |
|---|---|---|
| B5 | 初期設定 | `setupBookManagerUI()` |
| C5 | 接続テスト | `testConnection()` |
| D5 | 生成実行 | `runAgent()` |
| E5 | 最新表示 | `renderLatestForSelectedBook()` |
| F5 | レイアウト修復 | `hardResetInputLayout()` |

**変更後（現在の仕様）:**

| セル | ラベル | 処理 |
|---|---|---|
| B5 | 生成実行 | `runAgent()` |
| C5 | AI画像認識 | G2のURLを参照して実行 |
| D5 | クリア | C2:G2をクリア |
| E5 | （空） | 何もしない |
| F5 | （空） | 何もしない |

**変更前の `hardResetInputLayout` 内ラベル設定:**
```javascript
// 変更前
.setValues([["初期設定", "接続テスト", "生成実行", "最新表示", "レイアウト修復"]])

// 変更後
.setValues([["生成実行", "AI画像認識", "クリア", "", ""]])
```

**変更前の `handleInputButtons_`:**
```javascript
function handleInputButtons_(a1) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = mustOrCreateSheet_(ss, SHEETS.INPUT);

  try {
    if (a1 === "B5") {
      setupBookManagerUI();
    } else if (a1 === "C5") {
      testConnection();
    } else if (a1 === "D5") {
      runAgent();
    } else if (a1 === "E5") {
      renderLatestForSelectedBook();
    } else if (a1 === "F5") {
      hardResetInputLayout();
      repairDbSheetLayouts_();
      setStatus_("✅ Inputレイアウトを修復しました");
    }
  } finally {
    setInternalEdit_(1200);
    sh.getRange(a1).setValue(false);
  }
}
```

#### `02_onedit.gs` — `onEditInstalled` にチェックボックス処理を追加

**変更前:**
```javascript
function onEditInstalled(e) {
  try {
    if (!e || !e.range) return;
    if (isInternalEdit_()) return;

    const range = e.range;
    const sheet = range.getSheet();

    // G2 のみ担当（その他は onEdit の simple trigger が処理する）
    if (sheet.getName() !== SHEETS.INPUT) return;
    if (range.getA1Notation() !== "G2") return;

    const url = String(e.value || "").trim();
    if (url) importMemoFromUrl_(url);

  } catch (err) {
    console.error(err);
    try { setStatus_("⚠️ OCR処理でエラーが発生しました（ログ確認）"); } catch (_) {}
  }
}
```

**変更後（G2自動起動を削除してチェックボックスを追加）:**
```javascript
function onEditInstalled(e) {
  try {
    if (!e || !e.range) return;
    if (isInternalEdit_()) return;

    const range = e.range;
    const sheet = range.getSheet();
    const a1 = range.getA1Notation();

    if (sheet.getName() !== SHEETS.INPUT) return;

    // [修正] チェックボックス（B5~D5）処理
    if (INPUT_UI.BTN_A1S.includes(a1) && String(e.value).toUpperCase() === "TRUE") {
      handleInputButtons_(a1);
      return;
    }

    // G2 URL → OCR（自動実行は削除。C5ボタン押下時のみ実行）

  } catch (err) {
    console.error(err);
    try { setStatus_("⚠️ 処理でエラーが発生しました（ログ確認）"); } catch (_) {}
  }
}
```

#### `06_ocr_import.gs` — 複数URL対応 & G2自動起動削除

**複数URL対応の変更内容:**
- 引数を `url`（1件）→ `urlText`（複数URL含む文字列）に変更
- 改行・カンマ・空白で分割して複数URL対応
- `fileId` で `Set` を使って重複排除
- 各ファイルごとにエラーを収集して続行（1件失敗しても残りを処理）
- 結果を「N件完了 / M件エラー」形式で表示

**G2自動OCRを削除（`importMemoFromUrl_` 末尾から削除）:**
```javascript
// 削除した箇所（importMemoFromUrl_ の末尾にあったG2クリア処理）
withInternalEdit_(() => {
  SpreadsheetApp.getActiveSpreadsheet()
    .getSheetByName(SHEETS.INPUT).getRange("G2").clearContent();
});
```

**理由**: G2は入力欄のため、AI画像認識後もURLを保持すべき。クリアはD5（クリアボタン）で行う。

#### `00_config.gs` — DEFAULT_MODEL変更

**変更理由**: `gemini-2.5-flash` は新モデルで無料枠が少ない（1日20回）。レート制限エラーが頻発したため変更。

```javascript
// 変更前
DEFAULT_MODEL: "gemini-2.5-flash",

// 変更後
DEFAULT_MODEL: "gemini-1.5-flash",  // 1日1500回まで無料
```

---

## v2: Sessionsシート追加・UI改善（2026-03-05）

### 変更内容

#### `00_config.gs` — SESSIONS定数追加

```javascript
// SHEETS に追加
SESSIONS: "Sessions",

// DB_HEADERS に追加
SESSIONS: ["session_id", "日付", "book_id", "タイトル", "目的", "メモ", "回答", "モード"],

// DOC_PROP_KEYS に追加
LAST_INPUT_DATE: "LAST_INPUT_DATE",
```

#### `01_ui_input.gs` — Sessions初期化・プルダウン・復元関数を追加

**`setupBookManagerUI()` 内に追加:**
```javascript
const sessions = mustOrCreateSheet_(ss, SHEETS.SESSIONS);
// initDataSheets_ の後に追加:
initSessionsHeaderIfNeeded_(sessions);
```

**追加した関数群（ファイル末尾に追記）:**
```javascript
/** Sessionsシートのヘッダ初期化 */
function initSessionsHeaderIfNeeded_(sheet) {
  if (sheet.getLastRow() > 0) return;
  sheet.appendRow(DB_HEADERS.SESSIONS);
  sheet.setFrozenRows(1);
}

/** Sessionsシートに現在のInput内容を保存 */
function saveSession_(ss, bookId, title, purpose, memo, answers, mode, date) {
  const sheet = mustOrCreateSheet_(ss, SHEETS.SESSIONS);
  initSessionsHeaderIfNeeded_(sheet);
  const sessionId = Utilities.getUuid();
  const dateStr = Utilities.formatDate(date || new Date(), "Asia/Tokyo", "yyyy-MM-dd");
  sheet.appendRow([sessionId, dateStr, bookId, title, purpose, memo, answers, mode]);
}

/** Sessionsから日付一覧を取得してA2のプルダウンを更新 */
function refreshDateDropdown_(ss) {
  const sheet = mustOrCreateSheet_(ss, SHEETS.SESSIONS);
  const data = sheet.getDataRange().getValues();
  const dates = [...new Set(
    data.slice(1)
      .map(r => String(r[1] || "").trim())
      .filter(d => d.length > 0)
  )].sort().reverse();

  const input = mustOrCreateSheet_(ss, SHEETS.INPUT);
  const cell = input.getRange(INPUT_UI.DATE);

  if (dates.length === 0) {
    cell.clearDataValidations();
    return;
  }

  const today = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy-MM-dd");
  if (!dates.includes(today)) dates.unshift(today);

  cell.setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(dates, true)
      .setAllowInvalid(true)
      .build()
  );
}

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

#### `02_onedit.gs` — A2/B2変更時の処理を追加

**`onEditInstalled` 内 Input ブロックに追加:**
```javascript
// A2変更 → B2プルダウンを日付で絞り込む [修正] 追加
if (a1 === INPUT_UI.DATE) {
  const dateStr = String(e.value || "").trim();
  if (dateStr) filterTitlesByDate_(e.source, dateStr);
  return;
}

// B2変更 → タイトル切替 + Session復元 [修正] restoreSessionToInput_ を追加
if (a1 === INPUT_UI.TITLE) {
  handleInputTitleEdit_(e);
  const dateStr = String(e.source.getSheetByName(SHEETS.INPUT)
    .getRange(INPUT_UI.DATE).getDisplayValue() || "").trim();
  const title = String(e.value || "").trim();
  if (dateStr && title) restoreSessionToInput_(e.source, dateStr, title);
  return;
}
```

#### `03_run_agent.gs` — runAgent実行時にSessionsへ保存

**生成成功後（`setStatus_` 直前）に追記:**
```javascript
// [追加] Sessionsにスナップショット保存
const _sessDate = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy-MM-dd");
saveSession_(ss, bookId, title, purpose, memo, answers, mode, new Date());
refreshDateDropdown_(ss);
```

※ `bookId`, `title`, `purpose`, `memo`, `answers`, `mode` は実際のコード内の変数名に合わせること。

#### `01_ui_input.gs` — A2日付フォーマット修正

**変更理由**: `setValue(new Date())` だと `Tue Mar 03 2026 00:00:00 GMT+0900` と表示されていたため。

```javascript
// 変更前
sh.getRange(INPUT_UI.DATE).setValue(new Date());

// 変更後
sh.getRange(INPUT_UI.DATE).setValue(
  Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy-MM-dd")
);
sh.getRange(INPUT_UI.DATE).setNumberFormat("@");  // テキスト形式で表示
```

#### `01_ui_input.gs` — G1をフォルダリンクに変更

**変更理由**: フォルダへのアクセスをワンクリックで行えるようにするため（ファイルピッカーAPIは実装複雑なため代替案として採用）。

```javascript
// 変更前
sh.getRange("G1")
  .setValue("PDF/画像URL（G2に貼付→OCR）")
  .setFontWeight("bold")
  ...

// 変更後
sh.getRange("G1")
  .setFormula('=HYPERLINK("https://drive.google.com/drive/folders/1K450s27GlW3DI9fmkno21sWSg9EA1olL","📁 画像フォルダを開く")')
  .setFontWeight("bold")
  ...
```

#### `01_ui_input.gs` — タイトル変更時にG2もクリア

**変更理由**: タイトルを切り替えた際に前のURLが残り続けるのを防ぐため。

```javascript
// handleInputTitleEdit_ 内の既存クリア処理の後に追加
INPUT_UI.CLEAR_RANGES_ON_SWITCH_OK.forEach(a1 => input.getRange(a1).clearContent());
input.getRange("G2").clearContent(); // [修正] タイトル変更時にG2のURLもクリア
```

---

## 判断メモ・設計上の選択

### Sessionsシートを新規作成した理由
既存の複数シート（Memos・Runs・Books）をまたいで結合する案（案②）と比較して、以下の理由で新規シート（案①）を選択：
- 「入力当時の状況を再現する」という目的にはスナップショット1行保存が最適
- 複数シート結合は複雑でバグが出やすい
- Memosシートとは役割が重複する部分があるが、即削除は危険なためSessionsを追加して並行運用

### Drive OCRからGemini Visionに変更した理由
- Drive OCRはHEIC非対応（iPhone標準形式）
- すでにGemini API使用中で追加コストゼロ
- 手書きメモや文脈理解も可能
- 1つのAPIで「AI分析」と「画像読み取り」を両方カバーできる

### フォルダ自動スキャン（30分トリガー）を停止した理由
- G2貼り付け方式と競合してバグの原因になっていた
- `OCR_DONE_FOLDER_ID` 未設定で処理済みファイルが移動されず、同じファイルが繰り返し取り込まれていた
- 現在はC5ボタン（AI画像認識）による手動起動方式に統一

### gemini-1.5-flash に変更した理由
- `gemini-2.5-flash` は1日20回の無料枠しかなくレート制限が頻発
- `gemini-1.5-flash` は1日1500回まで無料で日常使いに適している

