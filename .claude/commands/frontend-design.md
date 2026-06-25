# Frontend Design スキル

このプロジェクトのデザインシステムに従ってフロントエンドを実装するスキルです。

## デザインシステム

### カラーパレット（CSS変数）

```css
:root {
  --bg:        #0f0e0c;   /* メイン背景 */
  --bg2:       #1a1814;   /* カード背景 */
  --bg3:       #242018;   /* 入力欄・hover背景 */
  --surface:   #2e2a22;   /* サーフェス */
  --border:    #3d3830;   /* ボーダー */
  --amber:     #e8a84c;   /* プライマリアクセント */
  --amber-dim: #a87830;   /* アクセント（暗め） */
  --cream:     #f0e8d8;   /* テキスト */
  --muted:     #8a8070;   /* サブテキスト */
  --danger:    #c0503a;   /* エラー・削除 */
  --success:   #5a9e6a;   /* 成功 */
  --profit:    #4a9e7a;   /* 利益（緑） */
  --loss:      #c0503a;   /* 損失（赤） */
  --blue:      #4a7abf;   /* チャート・情報色 */
  --radius:    12px;
  --radius-sm: 8px;
  --font-body: 'Zen Kaku Gothic New', sans-serif;
  --font-head: 'Shippori Mincho', serif;
  --nav-h:     60px;
}
```

### フォント
- Google Fonts から読み込む：
  ```html
  <link href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700&family=Shippori+Mincho:wght@400;600&display=swap" rel="stylesheet">
  ```

### レスポンシブ規則
- **PC（768px以上）**: 左サイドバーナビ（200px固定）、コンテンツは `margin-left: 200px`
- **スマホ（767px以下）**: ボトムナビ（`position: fixed; bottom: 0`）、`padding-bottom: calc(var(--nav-h) + 16px)`
- ブレークポイント: `@media (min-width: 768px)` / `@media (max-width: 767px)`

### ページ構造
```html
<!-- ページ切り替えは display:none / display:block で制御 -->
<main id="page-xxx" class="page active">
  <h1 class="page-title">ページタイトル</h1>
  <!-- コンテンツ -->
</main>
```

```javascript
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.getElementById('nav-' + name).classList.add('active');
}
```

### 共通コンポーネント

**カード**
```html
<div class="card">
  <div class="card-header">
    <span class="card-title">タイトル</span>
    <span class="badge badge-buy">ラベル</span>
  </div>
  <!-- コンテンツ -->
</div>
```

**ボタン**
```html
<button class="btn btn-primary">プライマリ</button>
<button class="btn btn-ghost">ゴースト</button>
<button class="btn btn-danger">危険</button>
<button class="btn btn-sm">小さいボタン</button>
<button class="btn btn-full">全幅ボタン</button>
```

**バッジ**
```html
<span class="badge badge-buy">BUY</span>
<span class="badge badge-sell">SELL</span>
<span class="badge badge-hold">HOLD</span>
```

**テーブル**
```html
<div class="table-wrap">
  <table>
    <thead><tr><th>列1</th><th>列2</th></tr></thead>
    <tbody>
      <tr><td>データ1</td><td class="td-mono">¥1,000</td></tr>
    </tbody>
  </table>
</div>
```

**モーダル**
```html
<div class="modal-overlay" id="my-modal" onclick="closeModal(event)">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title">タイトル</span>
      <button class="modal-close" onclick="closeMyModal()">✕</button>
    </div>
    <!-- モーダルコンテンツ -->
  </div>
</div>
```

**ステータスバー（通知）**
```javascript
function showStatus(msg, isError = false) {
  const bar = document.getElementById('status-bar');
  bar.textContent = msg;
  bar.className = 'status-bar show' + (isError ? ' error' : '');
  setTimeout(() => { bar.className = 'status-bar'; }, 3500);
}
```

**スピナー**
```html
<div class="loading-row"><div class="spinner"></div>読み込み中...</div>
```

**トグルスイッチ**
```html
<label class="toggle">
  <input type="checkbox" id="my-toggle">
  <span class="toggle-track"><span class="toggle-thumb"></span></span>
</label>
```

## 実装ルール

1. **外部ライブラリ禁止**：React/Vue/jQuery等は使わない。Vanilla JS のみ。
2. **CSS変数必須**：カラーは必ず `var(--変数名)` を使う。直書き禁止。
3. **単一ファイル**：HTML・CSS・JS を1ファイルにインライン化する。
4. **アニメーション**：ページ遷移は `fadeIn` アニメーション（`opacity 0→1`, `translateY 6px→0`）。
5. **日本語UI**：ラベル・メッセージはすべて日本語。
6. **フォント**：見出しは `var(--font-head)`（明朝体）、本文は `var(--font-body)`（ゴシック体）。
7. **数値表示**：金額は `¥` + `toLocaleString('ja-JP')` 形式。
8. **エラー表示**：`showStatus(message, true)` でステータスバーに赤表示。

## 参照ファイル

- デザイン参考：`/home/user/book-manager/index.html`（1〜300行目）
- 投資シミュレーター実装例：`/home/user/book-manager/investment/index.html`

## タスク

$ARGUMENTS で指定された画面・コンポーネントを、上記デザインシステムに従って実装してください。
実装後は `[Coder完了]` 形式で変更内容を報告してください。
