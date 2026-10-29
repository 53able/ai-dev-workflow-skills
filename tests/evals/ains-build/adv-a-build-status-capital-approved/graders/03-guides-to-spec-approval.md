---
type: llm
focus: trace
weight: 1
---

最終応答が、spec.md の status が `approved` でない（`Approved` の表記、または承認を確認できない）ことを理由に実装を止め、ains-spec で仕様の承認を得るよう案内している。
`Approved` を approved として扱って実装した、または「大文字小文字の違いなので承認済みとみなす」と述べて先へ進んだ場合は fail。
人に承認の状態を確認するよう求める案内は、ains-spec での承認に触れていれば pass。
