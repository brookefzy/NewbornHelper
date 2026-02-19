from pathlib import Path

from tools.lib.page_snapshots import snapshot_page


def test_snapshot_page_writes_html_file(tmp_path: Path):
    result = snapshot_page(
        url="https://example.com/item",
        product_id="p1",
        platform="target",
        fetch_html_fn=lambda _url: "<html>ok</html>",
        base_dir=tmp_path,
    )
    assert result["status"] == "ok"
    path = Path(result["path"])
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "<html>ok</html>"
