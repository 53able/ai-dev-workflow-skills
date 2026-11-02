---
type: llm
focus: trace
weight: 1
---

docs/changes/2026-11-02-order-confirmation-mail/tasks.md（git diff に新規ファイルとして現れる）を読み、次の (a)(b)(c) を判定する。最終応答だけに書かれたものは数えない。

- (a) 「方針」節に、守る依存方向か境界が、モジュール名（domain/order.py、app/place_order.py、infra/smtp_client.py など、パスかモジュール名）を使って1つ以上書かれている。例:「domain/order.py はメール送信を知らない」「送信は app/place_order.py から infra/smtp_client.py を呼ぶ」「domain は infra を import しない」。「層を守る」「既存の構造に従う」のように、モジュール名が無いものは数えない。
- (b) 「方針」節に、この変更で変えない interface が、名前（Order.confirm、SmtpClient.send、place_order など、関数名・メソッド名・クラス名）で1つ以上書かれ、それを変えないことが読み取れる。
- (c) 「方針」節か「承認」節に、人が決める項目が、具体的な名前で1つ以上書かれている。例:「SmtpClient を place_order に渡す方法（引数で受けるか、中で作るか）は人が決める」「送信失敗時に記録するかどうかを承認時に決めてほしい」。「何かあれば相談する」のような一般的な文は数えない。

(a)(b)(c) の3つが揃えば pass。1つでも欠ければ fail。tasks.md が無い場合は fail。reason は `a=yes|no b=yes|no c=yes|no; ` で始める。
