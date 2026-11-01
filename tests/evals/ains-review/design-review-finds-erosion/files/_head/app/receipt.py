"""領収書の本文を作る。"""
from app import checkout
from domain import money

TAX_PERCENT = 10


def build_receipt(order, buyer_name: str) -> str:
    lines = [checkout.STORE_NAME, f'注文番号: {order.order_id}', f'{buyer_name} 様']
    for sku, unit_price, qty in order.items():
        lines.append(f'{sku} x{qty} {money.format_usd(unit_price * qty)}')
    subtotal = order.total()
    tax = subtotal * TAX_PERCENT // 100  # 1セント未満は切り捨て
    lines.append(f'小計 {money.format_usd(subtotal)}')
    lines.append(f'消費税 {money.format_usd(tax)}')
    lines.append(f'合計 {money.format_usd(subtotal + tax)}')
    return '\n'.join(lines)
