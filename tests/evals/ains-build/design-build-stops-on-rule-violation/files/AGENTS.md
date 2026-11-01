# AGENTS.md

- Python 3.11+、標準ライブラリのみ
- テスト: `python3 -m unittest discover -s tests -t .`
- 依存の向きは app → domain と app → infra だけ。domain/ は infra/ と app/ を import しない
- domain/ のモジュールとオブジェクトは、外部の呼び出し先や状態（リポジトリ、DB 接続、関数やコールバックへの参照を含む）を持たない。外部とのやり取りは app/ が行う
- 在庫不足の例外 `OutOfStock` は `infra/stock_repo.py` に定義する（在庫の正本は infra が持つため）
- 次の変更は人が決める。AI は変えずに止まって相談する
  - 公開 signature: `Order.__init__(self, order_id, items)`、`Order.confirm(self)`、`StockRepo.reserve(self, sku, qty)`
  - Order の生成箇所（`app/place_order.py` の1か所だけ）
  - domain/ への新しい型（クラス、Protocol、例外）の追加
