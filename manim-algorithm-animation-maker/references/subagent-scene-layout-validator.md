# Scene Layout Validator Contract

## Role

在 pre-layout Scene Review 通過後，對五個核准 Scene 執行非渲染 layout audit，並以確定性工具將 raw JSON 聚合成供修正使用的精簡 triage。

## Ownership and hard boundaries

- 不 render 媒體、不修改任何輸入或 Scene source。
- 不省略 Scene，不自行豁免、忽略、摘要改寫或降級 raw findings。
- Raw JSON 與 runner gate result 永遠是權威；summary/triage 只供導航與節省 context。
- 不要求 Scene Writer 執行 runner或讀取完整 raw JSON。

## Required inputs

1. `Scene source`
2. `Project layout helper`
3. `Render profile`
4. `Pre-layout Scene review result`
5. `Layout audit guide`
6. `Layout audit runner`
7. `Layout audit summarizer`

## Required dispatch data

- `Scene classes and approved order`（五個 Scene 的核准順序）
- `Validation phase`：`initial`、`iteration` 或 `final`
- Reviewer 明確批准的 per-Scene exception paths/hashes（final run 才可提供；沒有時明記 none）

## Expected outputs

- `<project-root>/layout_audit_result.md`
- `<project-root>/layout_audit_summary.json`
- `<project-root>/layout_audit_triage.md`

## Preflight

- 所有 Required inputs 與 scripts 都存在且可讀。
- Scene review result 為 `PRELAYOUT_PASS` 或 final `PASS`。
- `initial` source hash 必須等於 `Pre-layout Reviewed Code SHA-256`；`iteration` 只接受 Coordinator 已確認未跨越 semantic/structural boundary 的 layout-only diff；`final` source hash 必須等於 `Final Reviewed Code SHA-256`。
- 五個 Scene class 正好五個、互不重複且存在於目前 source。
- Graph-root 註冊可在 source 中追溯。
- 只有 final Reviewer `PASS` 明確逐筆 `APPROVED` 的 exception 才能交給 runner；不得臨時建立或修改例外。

Preflight 失敗時仍建立 `layout_audit_result.md` 並寫入 `Result: FAIL`；只有連結果檔都無法建立時才回報 `BLOCKED`。

## Procedure

1. 記錄 source、runner、summarizer、render profile path/hash 與 profile 環境欄位。
2. 依核准順序對五幕執行 `run_layout_audit.py --audit-visible --require-adapter --visible-report-level warning`。初次與修正迭代不得套用未批准 exception。
3. 每幕保留完整 `layout_audit_report.<SceneClass>.json`、command、stdout、stderr、exit code、checkpoint 與 hash。
4. 對五個 raw reports 執行 `summarize_layout_audit.py`，固定產生 summary JSON 與 triage Markdown。Summary 按 Scene、severity、relation、完整 object pair、accepted/exception identity 聚合重複，保留 occurrence count、checkpoints、message variant count、代表訊息與 raw report hash。
5. `layout_audit_result.md` 逐幕照 raw JSON 原值記錄 totals、infos、accepted/unresolved warnings、errors 與 gate result；不得使用 grouped count 取代 raw gate count。
6. 有 blocking findings 時，只把 `layout_audit_triage.md` 與指定 groups 路由回 Writer。INFO 建議只作 best-effort，不得升成 gate。
7. Writer 修正後可重跑受影響 Scene 作迭代，但 final gate 必須重新完整執行五幕。
8. Final run 前，Scene Reviewer 必須已對最終 source 寫 `Result: PASS`，且 `Final Reviewed Code SHA-256` 與受檢 source 完全一致。Final run 只套用 Reviewer 明確批准且 hash 相符的 exceptions。

泛用 visible audit 是權威 gate：`unresolved warning count > 0 => FAIL`。同 graph line/line 等 best-effort findings 保留為 `INFO`；常見封閉 node 外形會先排除完整 containment，同 graph 的實際 node/node overlap 為 blocking `WARNING`，Circle/Circle 使用圓形 narrow phase；同 graph 文字遮擋也一律為 blocking `WARNING`。不同 graph、graph 對 non-graph、internal/cross-container spill、unexpected containment、畫面越界、adapter failure、缺少 checkpoint 或 hash 不一致仍會阻塞。

## Completion criteria

只有以下條件全部成立才能寫 `Result: PASS`：

- Final Scene review 為 `PASS`，reviewed hash 與 audited source 相同。
- 五幕完整受檢且 initial／beat／final checkpoint 完整。
- 五個 raw JSON 與兩個 derived summary outputs 都存在並記錄 hash。
- 每幕 unresolved warnings 與 errors 都是 `0`，必要 command 全部 exit `0`。
- Accepted warnings 全部有 Reviewer `APPROVED` 的 exact exception evidence。

其他情況一律寫 `Result: FAIL`。

## Final response

- `DONE`：回報結果與 summary 路徑、`PASS`／`FAIL` 及五幕 exit code。
- `BLOCKED`：僅在無法建立結果檔時使用。
