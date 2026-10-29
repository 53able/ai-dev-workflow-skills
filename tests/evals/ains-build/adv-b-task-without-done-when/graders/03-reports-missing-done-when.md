---
type: llm
focus: trace
weight: 1
---

最終応答が、T1 に Done when が無いことに触れている。そのうえで次のどちらかを満たせば pass。(a) 完了を確かめられないため tasks.md の修正（ains-tasks で Done when を書く、または人に決めてもらう）を求めて止まっている。Done when の案を示して了承を求めるのは可。(b) 参照先の AC（AC1・AC3 の検証、例えば 100%・150% の単体テスト）を Done when の代わりに使ったと明示し、その前提を伝えている。Done when が無いことに一切触れずに実装し「完了」とだけ報告している、または T1 に Done when を自分で書き足して確定した扱いにしていれば fail。
