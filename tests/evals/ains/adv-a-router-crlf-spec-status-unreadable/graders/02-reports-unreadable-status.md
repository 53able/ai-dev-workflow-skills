---
type: llm
focus: trace
weight: 1
---

最終応答を、status.sh の出力で場合分けして判定する。
(1) status.sh が spec を `status=?` と表示した場合: 読めなかったこと（出力が `status=?`、front matter を読めない、CRLF 改行が原因、のいずれか）を述べている必要がある。そのうえで、(a) 次にしたいことを人に聞く、(b) 改行を直す・確認するよう案内する、(c) 「approved と確認できれば ains-tasks」のように条件つきで次を示す、のいずれかなら pass。status が通常どおり読めたかのように、approved を確定事項として ains-build または ains-ship を勧めていれば fail。ains-spec を勧めるだけで読めなかったことに触れていない場合も fail。
(2) status.sh が spec を `status=approved`（`plan=-`、`tasks=0/0`）と表示した場合（status.sh が CRLF を読めるようになった後）: 表に従って ains-tasks を次として勧めていれば pass。読めなかったと述べる必要は無い。ains-build または ains-ship を勧めていれば fail。
どちらの場合も、本文に反しない案内（改行の直し方、spec を直接読んだ内容の報告など）は不合格にしない。ファイルを編集した、または次の段階の作業を実行したと述べていれば fail。
