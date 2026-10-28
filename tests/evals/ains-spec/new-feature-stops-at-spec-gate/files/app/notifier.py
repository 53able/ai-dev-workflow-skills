"""注文確定などのイベントでメールを送る。"""
from app import settings


def send_order_confirmation(user_id: str, order_id: str, outbox: list) -> None:
    outbox.append({"to": user_id, "template": "order_confirmation", "order_id": order_id})
