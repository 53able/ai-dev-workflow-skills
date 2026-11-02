"""請求書の本文。"""
from shop.order import Order


def build_invoice(order: Order) -> str:
    rows = [f'請求書 No.{order.number}']
    for line in order.lines:
        off = f' (割引 {line.discount_percent}%)' if line.discount_percent else ''
        rows.append(f'{line.sku} {line.qty} x {line.unit_price}{off} = {line.amount()}')
    subtotal = order.subtotal()
    tax = order.tax()
    rows.append(f'小計 {subtotal}')
    rows.append(f'税 {tax}')
    shipping = order.shipping()
    rows.append(f'送料 {shipping}')
    rows.append(f'合計 {subtotal + tax + shipping}')
    return '\n'.join(rows)
