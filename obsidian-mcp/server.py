import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from mcp.server.fastmcp import FastMCP

MCP_NAME = "obsidian"
DEFAULT_VAULT_PATH = Path("/Users/yoshikawasho/Library/Mobile Documents/iCloud~md~obsidian/Documents/vault")
VAULT_PATH = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(DEFAULT_VAULT_PATH)))
mcp = FastMCP(MCP_NAME)

def _resolve(folder: str, filename: str = "") -> Path:
    base = VAULT_PATH / folder if folder else VAULT_PATH
    if filename:
        name = filename if filename.endswith(".md") else f"{filename}.md"
        return base / name
    return base

def _parse_sections(content: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: Optional[str] = None
    for line in content.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}

def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback

@mcp.tool()
def list_notes(folder: str = "01_読書ノート") -> str:
    """Vault内のフォルダにあるMarkdownノートの一覧を返す。"""
    target = _resolve(folder)
    if not target.exists():
        return f"⚠️ フォルダが見つかりません: {target}"
    notes = sorted(target.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not notes:
        return f"📂 ノートが見つかりませんでした: {target}"
    lines = [f"📚 {folder or 'vault'} 内のノート（{len(notes)} 件）\n"]
    for note in notes:
        mtime = datetime.fromtimestamp(note.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        try:
            title = _extract_title(note.read_text(encoding="utf-8"), note.stem)
        except Exception:
            title = note.stem
        lines.append(f"📄 {note.name}  |  更新: {mtime}  |  {title}")
    return "\n".join(lines)

@mcp.tool()
def read_note(filename: str, folder: str = "01_読書ノート") -> str:
    """指定したノートの本文をそのまま返す。"""
    path = _resolve(folder, filename)
    if not path.exists():
        return f"⚠️ ファイルが見つかりません: {path}"
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"⚠️ 読み込みエラー: {e}"

@mcp.tool()
def get_parsed_note(filename: str, folder: str = "01_読書ノート") -> str:
    """ノートをパースしてタイトル・各セクションを構造化テキストで返す。"""
    path = _resolve(folder, filename)
    if not path.exists():
        return f"⚠️ ファイルが見つかりません: {path}"
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return f"⚠️ 読み込みエラー: {e}"
    title = _extract_title(content, path.stem)
    sections = _parse_sections(content)
    def s(key: str) -> str:
        for k, v in sections.items():
            if key in k:
                return v
        return "（なし）"
    return "\n".join([
        f"# {title}", "",
        f"【著者】{s('著者')}", f"【ジャンル】{s('ジャンル')}", f"【読み始め】{s('読み始め')}", "",
        "【この本を読む目的】", s("この本を読む目的"), "",
        "【重要ポイント】", s("重要ポイント"), "",
        "【刺さった言葉】", s("刺さった言葉"), "",
        "【自分の言葉で要約】", s("自分の言葉で要約"), "",
        "【すぐ実行すること】", s("すぐ実行すること"),
    ])

@mcp.tool()
def search_notes(query: str, folder: str = "01_読書ノート") -> str:
    """フォルダ内のノートをキーワードで全文検索する。"""
    target = _resolve(folder)
    if not target.exists():
        return f"⚠️ フォルダが見つかりません: {target}"
    notes = sorted(target.glob("*.md"))
    hits: list[tuple[Path, list[str]]] = []
    q = query.lower()
    for note in notes:
        try:
            lines = note.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        matched = [ln.strip() for ln in lines if q in ln.lower() and ln.strip()]
        if matched:
            hits.append((note, matched[:3]))
    if not hits:
        return f"🔍 「{query}」に一致するノートが見つかりませんでした。"
    out = [f"🔍 「{query}」 — {len(hits)} 件ヒット\n"]
    for note, snippets in hits:
        out.append(f"📄 {note.name}")
        for sn in snippets:
            out.append(f"   …{sn}…")
        out.append("")
    return "\n".join(out)

@mcp.tool()
def list_folders() -> str:
    """Vault直下のフォルダ一覧を返す。"""
    if not VAULT_PATH.exists():
        return f"⚠️ Vault が見つかりません: {VAULT_PATH}"
    folders = sorted(p for p in VAULT_PATH.iterdir() if p.is_dir() and not p.name.startswith("."))
    if not folders:
        return "📂 フォルダが見つかりませんでした。"
    lines = [f"📁 Vault フォルダ一覧（{VAULT_PATH}）\n"]
    for f in folders:
        count = len(list(f.glob("*.md")))
        lines.append(f"📁 {f.name}/  （{count} ノート）")
    return "\n".join(lines)

if __name__ == "__main__":
    mcp.run(transport="stdio")
