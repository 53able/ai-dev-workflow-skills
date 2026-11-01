"""請求書の本文。"""
from shop.order import Order


def build_invoice(order: Order) -> str:
    rows = [f'請求書 No.{order.number}']
    for line in order.lines:
        rows.append(f'{line.sku} {line.qty} x {line.unit_price} = {line.unit_price * line.qty}')
    subtotal = sum(line.unit_price * line.qty for line in order.lines)
    tax = round(subtotal * 0.1)
    rows.append(f'小計 {subtotal}')
    rows.append(f'税 {tax}')
    rows.append(f'合計 {subtotal + tax}')
    return '\n'.join(rows)
