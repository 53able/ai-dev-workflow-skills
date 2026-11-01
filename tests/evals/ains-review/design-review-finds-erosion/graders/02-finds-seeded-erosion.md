---
type: llm
focus: trace
weight: 1
---

レビューの指摘（最終応答と、エージェントが書いたファイル。サブエージェントの結果を最終応答で伝えたものを含む）に、次の種がそれぞれ指摘されているかを判定する。git diff には、レビュー対象として仕込んだ HEAD の変更（下の種そのもの）も含まれる。種がコードにあることではなく、エージェントがそれを指摘したかで判定する。

数える条件: 箇所（ファイル名。関数名・行は無くてもよい）と、根拠（何が壊れるか、どの規則・前提に反するか）の両方がある。箇所だけ、または「気になる」だけのものは no。

- S1 内部表現の漏れ: domain/order.py の `items()` が内部のリスト `_items` をそのまま返し、app/receipt.py がそれを `sort()` で並べ替えて Order の内部状態を書き換える（またはその恐れ）。根拠の例: 内部表現が漏れる、カプセル化・情報隠蔽が壊れる、呼出し側が注文の品目の順序を変えてしまう、コピーか不変の型を返すべき
- S2 共有前提の複製: app/receipt.py が金額の単位（domain/money.py の整数のセント）を「円」として表示している、または税を独自の定数（TAX_RATE = 0.08、浮動小数点）で計算し domain/money.py の tax・税率（10%）と食い違う。根拠の例: money.py の前提（セント、税と表示は money.py の関数を使う）と矛盾する、領収書の合計が checkout の支払額と一致しない。単位と税のどちらか一方の指摘でよい
- S3 依存の逆流: domain/order.py が infra（infra.db の save_receipt）を import している。根拠の例: AGENTS.md の「domain/ は infra/ と app/ を import しない」に反する、依存の向きが逆、domain が DB なしでテストできなくなる
- C（合否に使わない）: app/receipt.py と app/checkout.py が互いを import している（循環 import）
- D（合否に使わない）: 同じ購入者を customer（customer_id）、buyer（buyer_name）、client（client_name）と呼び分けている、命名の不統一

S1〜S3 のうち2件以上が yes なら pass、1件以下なら fail。C と D は合否に影響しない。

reason は必ず `S1=yes|no S2=yes|no S3=yes|no C=yes|no D=yes|no; ` の形で始め、その後に短い理由を書く（例: `S1=yes S2=no S3=yes C=no D=no; S1 と S3 を根拠つきで指摘`）。
