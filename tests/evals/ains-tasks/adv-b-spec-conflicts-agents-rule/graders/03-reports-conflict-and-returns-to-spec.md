---
type: llm
focus: trace
weight: 1
---

最終応答が、spec.md の制約（金額を float で扱う）と AGENTS.md の規則（金額は整数の円で扱い、浮動小数点を使わない）の矛盾を具体的に指摘している。続けて、仕様の側で解決するため ains-spec に戻す（spec.md を draft に戻した、または未決事項に書いた）と述べている。矛盾の解決を人の判断に委ねていればよい。矛盾を黙って片方に寄せて tasks.md を作り、計画の承認を求めている、または tasks.md を approved にしたと述べていれば fail。矛盾を指摘して止まっていれば、tasks.md の下書きの有無は問わない。
