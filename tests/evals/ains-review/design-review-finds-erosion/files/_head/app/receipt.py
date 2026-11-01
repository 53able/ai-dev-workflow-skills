"""領収書の本文を作る。"""
from app import checkout

TAX_RATE = 0.08


def build_receipt(order, buyer_name: str) -> str:
    items = order.items()
    items.sort(key=lambda item: item[1] * item[2], reverse=True)  # 金額の大きい順に載せる
    lines = [checkout.STORE_NAME, f'注文番号: {order.order_id}', f'{buyer_name} 様']
    for sku, unit_price, qty in items:
        lines.append(f'{sku} x{qty} {unit_price * qty}円')
    subtotal = order.total()
    tax = int(subtotal * TAX_RATE)
    lines.append(f'小計 {subtotal}円')
    lines.append(f'消費税 {tax}円')
    lines.append(f'合計 {subtotal + tax}円')
    return '\n'.join(lines)
