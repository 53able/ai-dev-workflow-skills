---
type: llm
focus: trace
weight: 1
---

レビューの指摘（最終応答と、エージェントが書いたファイル。サブエージェントの結果を最終応答で伝えたものを含む）に、次の種がそれぞれ指摘されているかを判定する。git diff には、レビュー対象として仕込んだ HEAD の変更（下の種そのもの）も含まれる。種がコードにあることではなく、エージェントがそれを指摘したかで判定する。

種はどれも、今は不具合として現れない（テストは通り、領収書の金額は会計の支払額と一致する）。将来のありそうな変更で壊れる設計の劣化である。「今は動く」「現時点では問題ない」と添えていても、下の根拠を述べていれば yes。逆に、今の出力が誤っていると事実に反して主張しているだけで、下の根拠が無いものは no。

数える条件: 箇所（ファイル名。関数名・行は無くてもよい）と、根拠（どの規則・前提を壊すか、どんな変更で壊れるか）の両方がある。箇所だけ、または「気になる」だけのものは no。

- S1 内部表現の漏れ: domain/order.py の `items()` が内部のリスト `_items` をコピーせずそのまま返し、app/receipt.py がその戻り値（可変のリストと、(sku, 単価, 数量) のタプルの並び）に依存している。根拠の例: 内部表現が漏れる、カプセル化・情報隠蔽が壊れる、呼出し側がリストを変えると add_item の検査を通らずに注文の品目が変わる、内部の持ち方を変えると呼出し側も変わる、コピーか不変の型を返すべき。今の呼出し側が書き換えていないことは問わない
- S2 共有前提の複製: app/receipt.py が税を domain/money.py の `tax` を使わず、独自の定数 `TAX_PERCENT = 10` と切り捨てで計算し直している（今は money.TAX_RATE_PERCENT と同じ値で結果も一致する）。根拠の例: money.py の「税の計算と表示はこのモジュールの関数を使い、呼出し側で税率を持たない」に反する、税率か端数処理を変えるときに2か所を直す必要がある、片方だけ変えると領収書の合計と会計の支払額が食い違う
- S3 依存の逆流: domain/order.py が `TYPE_CHECKING` の下で `from infra.db import Database` を import し、`Order.archive_receipt(db: Database, ...)` で infra の Database を受け取って保存を呼ぶ。根拠の例: AGENTS.md の「domain/ は infra/ と app/ を import しない」に反する（型だけの import でも依存の向きが逆）、domain が保存先を知る、保存先を差し替えにくい、保存は app 層で行うべき
- C（合否に使わない）: app/receipt.py と app/checkout.py が互いを import している（循環 import）
- D（合否に使わない）: 同じ購入者を customer（customer_id）、buyer（buyer_name）、client（client_name）と呼び分けている、命名の不統一

S1〜S3 のうち2件以上が yes なら pass、1件以下なら fail。C と D は合否に影響しない。

reason は必ず `S1=yes|no S2=yes|no S3=yes|no C=yes|no D=yes|no; ` の形で始め、その後に短い理由を書く（例: `S1=yes S2=no S3=yes C=no D=no; S1 と S3 を根拠つきで指摘`）。
