from __future__ import annotations


def _money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"${value:,.2f}"


def render_digest_html(run_date: str, top_drops: list[dict], all_items: list[dict], coupons: list[dict]) -> str:
    top_rows = "".join(
        f"<tr><td>{item['product_name']}</td><td>{_money(item.get('current_price'))}</td><td>{item.get('drop_pct', 0):.1f}%</td></tr>"
        for item in top_drops
    )
    all_rows = "".join(
        "<tr>"
        f"<td>{item.get('product_name', '')}</td>"
        f"<td>{_money(item.get('current_price'))}</td>"
        f"<td>{_money(item.get('baseline_price'))}</td>"
        f"<td>{_money(item.get('target_price'))}</td>"
        "</tr>"
        for item in all_items
    )
    coupon_rows = "".join(
        f"<li><strong>{coupon.get('brand', 'Brand')}</strong>: {coupon.get('offer_text', '')} "
        f"(<a href=\"{coupon.get('source_url', '#')}\">source</a>)</li>"
        for coupon in coupons
    )

    return f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #1f2937;">
    <h1>Baby Product Price Alert Digest</h1>
    <p>Run date: {run_date}</p>

    <h2 style="color: #b91c1c;">Top Significant Drops</h2>
    <table border="1" cellpadding="8" cellspacing="0">
      <tr><th>Product</th><th>Current Price</th><th>Drop</th></tr>
      {top_rows}
    </table>

    <h2>All Tracked Products</h2>
    <table border="1" cellpadding="8" cellspacing="0">
      <tr><th>Product</th><th>Current</th><th>Baseline</th><th>Target</th></tr>
      {all_rows}
    </table>

    <h2>Coupon Opportunities</h2>
    <ul>{coupon_rows}</ul>
  </body>
</html>
""".strip()
