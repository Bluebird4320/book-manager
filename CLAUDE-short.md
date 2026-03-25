# Book Manager 開発ルール（短縮版）

## プロジェクト
- リポジトリ: https://github.com/Bluebird4320/book-manager
- 公開URL: https://bluebird4320.github.io/book-manager/
- メインファイル: /Volumes/SSD001/Dev/AI エージェント/読書用エージェント/index.html
- MCPサーバー: /Volumes/SSD001/Dev/AI エージェント/読書用エージェント/mcp/server.py
- データ: localStorage / books.json（gitignore済み）
- AI: Gemini API（gemini-2.0-flash）・APIキーはlocalStorageに保存

## 絶対ルール
- 修正は最小限（関係ない箇所は触らない）
- 削除前は必ずユーザーに確認
- APIキーをコードに書かない
- git pushはDeployerのみ

## 役割
- Coder: 実装のみ・pushしない
- Reviewer: レビューのみ・修正しない
- Deployer: git push のみ・コード触らない

## デプロイ
```bash
cd "/Volumes/SSD001/Dev/AI エージェント/読書用エージェント"
git add index.html && git commit -m "fix: 内容" && git push
```

詳細ルール → docs/CLAUDE.md
