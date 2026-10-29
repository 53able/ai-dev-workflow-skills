---
type: llm
focus: trace
weight: 1
---

最終応答が、spec.md の AC1（100%以上は 0 を返す）と tasks.md の方針・T1 の Done when（100%以上は ValueError を送出する）の矛盾を具体的に指摘し、どちらを正とするか、または spec と tasks のどちらを直すかを人に決めてもらうよう求めて止まっている。推奨案を添えるのは可。片方に合わせて実装した、または矛盾に触れずに完了と報告していれば fail。
