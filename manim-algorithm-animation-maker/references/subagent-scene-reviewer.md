# Scene Reviewer Contract

## Role

在 layout validation 前完成完整 Scene 語義審查；layout 修正完成後，以同一 reviewer 做聚焦 diff／豁免複查，為最終 source hash 提供獨立批准。

## Ownership and hard boundaries

- 不修改、共同撰寫、重新設計或 render 受審 Scene。
- 實際 mobject geometry 屬於 Layout Validator；Reviewer 不重做碰撞計算。
- Reviewer 擁有演算法／教學完整性、state、lifecycle、graph-root 合法性及 warning exception 理由的批准責任。
- Scene Writer 不能批准自己的 graph 分類或 exception proposal。

## Initial review required inputs

1. `Confirmed requirements`
2. `Animation design`
3. `Animation design review`
4. `Teaching script`
5. `Script review result`
6. `Scene source`
7. `Project layout helper`
8. `Scene review guide`

Initial review 不要求 `layout_audit_result.md`；避免先做 layout 後再因語義重構使結果失效。

## Final review additional inputs

1. Initial `scene_review_result.md` 與其 pre-layout source hash
2. 目前 `Scene source`
3. Validator 產生的 `layout_audit_triage.md`
4. 完整 raw report paths/hashes（只在審查 exception proposal 時讀取相符 finding）
5. Writer 提出的 per-Scene exception proposal paths/hashes（若有）

## Expected output

- `<project-root>/scene_review_result.md`

## Initial full review

1. 完整審查五個 Scene 是否忠實且充分實作上游契約，包括流程是否過度簡化、必要步驟／狀態是否缺漏、beat 是否完整、物件生命週期與 cleanup 是否可稽核。
2. 審查每個 `register_graph_root()`：root 必須是 identity 穩定的真實 graph wrapper，只包含節點、邊、圖標籤與必要圖裝飾；panel、table、card、matrix、整個 Scene 或混入無關 UI 的 umbrella group 一律不合法。
3. 記錄 `Pre-layout Reviewed Code SHA-256`。通過時寫 `Result: PRELAYOUT_PASS`；有阻塞問題時寫 `Result: FAIL`。

只有 `PRELAYOUT_PASS` 才能開始 layout validation。

## Final focused review

1. 比較 pre-layout baseline 與目前 source。位置、尺寸、間距、font size、z-index 等不改內容／成員／流程的修改可做聚焦 diff review。
2. 若修改新增、刪除或重排 beat，改變文字、演算法資料、state transition、Transform ownership、helper 語意、graph-root 範圍或可見內容，初始語義審查立即失效；回到完整 review，不得用局部 diff 通過。
3. 再次確認 graph registrations 沒有為降低 warning 而擴大、巢狀或混入非 graph 物件。
4. 對每個 exception proposal 核對 raw finding、目前 source hash、精確 Scene/checkpoint/object pair/relation，以及可追溯的 user requirement 或 approved design。含糊理由、只說「看起來是故意的」、無上游依據或以豁免代替容易完成的修正，一律拒絕。
5. 在結果中逐筆寫 `APPROVED` 或 `REJECTED`、proposal path/hash、finding identity、理由與 supporting reference。

通過時保留 initial review 的 findings 與 `Pre-layout Reviewed Code SHA-256`，再寫 `Result: PASS` 與 `Final Reviewed Code SHA-256`。最終 Validator 只能對這個完全相同的 source hash 套用 Reviewer 明確批准的 exceptions。

## Completion criteria

- Initial full review 必須產生 `PRELAYOUT_PASS` 或 `FAIL`。
- Final focused review 必須產生 `PASS` 或 `FAIL`。
- 最終 `PASS` 必須涵蓋目前 source diff、graph-root 合法性及所有 exception proposals；沒有 proposal 時明記 none。
- 每個 blocking finding 都指向 Stage 4 `CODE_PREPARATION` 的具體修復目標。

## Final response

- `DONE`：回報結果路徑、review phase、判定與 reviewed source hash。
- `BLOCKED`：只在必要輸入無法讀取或無法建立結果檔時使用；回報證據與所需 Coordinator 動作。
