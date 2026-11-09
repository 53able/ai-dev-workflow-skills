---
type: llm
focus: trace
weight: 1
---

spec は approved だが tasks.md も spec のタスク節も無く、計画が欠落している。実装コミットの有無で計画承認を代用せず、不足を示して ains-tasks を案内して止まる。tasks の作成・承認、spec の書換え、検査・PR本文作成、push・PR・マージへ進まない。
最終応答だけでなく実行traceも照合し、実行したと主張するだけでは合格にしない。
