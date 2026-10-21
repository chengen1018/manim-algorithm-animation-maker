# How to Review Manim Scene Code

本文件說明獨立 scene-reviewer 如何在任何 Manim render 前分兩階段審查 `generated_algo_scene.py`：先做完整 pre-layout 語義審查，layout 收斂後再做聚焦 diff、graph 註冊與 exception disposition 複查。Reviewer 不重做幾何計算；raw layout findings 由 Validator 提供。

## 必要輸出

回傳 `scene_review_result.md`，內容需包含：

- `PASS` 或 `FAIL`
- 審查結果必須由獨立 reviewer 撰寫
- reviewer 負責 Stage 4 `SCENE_IMPLEMENTATION` 的 `CONTRACT_REVIEW` gate 程式碼審查
- 分類好的阻塞性 findings
- 指向程式碼位置的 evidence references
- 修復方向：Stage 4 `SCENE_IMPLEMENTATION` 的 `CODE_PREPARATION`

使用以下 finding 類別：

- `implementation fidelity`
- `algorithm/state correctness`
- `lifecycle/ownership and cleanup`

## 審查輸入

Initial full review 要求上游契約、目前 Scene source、project layout helper 與本指南存在，不要求 layout result。通過時寫 `PRELAYOUT_PASS` 與 baseline source hash。Final focused review 另讀 baseline result、layout triage、目前 source diff，以及有 proposal 時的精確 raw findings／report hashes。

## 程式碼審查問題

### Source Fidelity

- 是否有五個 `Scene` 類別，並依 `animation_design.md` 的 Scene 1–5 核准順序忠實實作每幕的教學責任與主要 beat？
- 程式碼是否忠實實作已確認需求、已核准設計與已審查 script，而非新增自己的演算法步驟或教學目標？
- 已核准為必要的 support structure、pointer 意義與 state 更新是否在程式碼中可追溯？
- Scene 4 的 case labels、assumptions、工作單位與逐 beat 呈現是否和已核准 derivation 一致？Complexity claim 的數學正確性由 design review 擁有，scene-reviewer 只檢查 source fidelity，不重做該數學審查。

### Algorithm, State, Lifecycle, and Cleanup

- `Transform`、`ReplacementTransform` 與可替換物件的 current reference 是否一致？
- helper、label、highlight 與 support structure 是否有明確的建立、更新、淡出或移除時點？
- 各 Scene 是否自行建立與清理物件，並在程式碼中明確淡出至空白後再銜接下一幕？
- 教學流程是否充分呈現核准步驟，而非用過度簡化的跳步、摘要文字或未展示的 state transition 取代？
- 每個 registered graph root 是否為 identity 穩定的真實 graph wrapper，且沒有包含 panel、table、card、matrix、整個 Scene 或無關 UI？

實際 mobject geometry、bounding box、碰撞、遮擋與 safe-frame 由 raw layout reports 決定；scene-reviewer 不得重做。Reviewer 只判斷 graph 分類是否誠實，以及 exception 理由是否有核准來源且值得保留。

### Maintainability

- 語意常數、builders、groups 與 visibility ownership 是否足以讓演算法與狀態意圖被稽核？
- 是否存在無法追溯至上游契約的演算法或教學解讀？

## 審查範圍

第一次程式碼審查必須檢查完整 `generated_algo_scene.py`。位置、尺寸、間距、font size、z-index 等不改內容與結構的 layout-only diff 可局部複查。Beat、文字、演算法資料、state transition、Transform ownership、helper 語意、graph-root 範圍或可見內容改變時，必須重新完整審查。

Final review 對每筆 exception proposal 寫 `APPROVED` 或 `REJECTED`，並記錄 proposal path/hash、scene/checkpoint/object pair/relation、理由、supporting reference 與目前 source hash。Scene Writer 的理由本身不構成批准。

每個 finding 的修正目標為 Stage 4 `SCENE_IMPLEMENTATION` 的 `CODE_PREPARATION`。scene-reviewer 不得修改 `generated_algo_scene.py` 或任何 render 產物。

## PASS 標準

只有在以下條件成立時才能通過：

- `generated_algo_scene.py` 忠實實作已確認需求、已核准設計與已審查 script
- 程式碼中的演算法狀態、物件生命週期、ownership 與 Scene cleanup 可稽核
- Initial review 已對完整 source 寫 `PRELAYOUT_PASS`；final review 已核對 baseline-to-final diff，並對最終 source 寫 `PASS`
- 每個 graph root 合法，且所有 exception proposals 都有逐筆 disposition；任何 `APPROVED` warning 綁定目前 source hash 與可追溯核准來源
- `scene_review_result.md` 由獨立 reviewer 撰寫，而非 scene-writer，並記錄 `Pre-layout Reviewed Code SHA-256` 與 `Final Reviewed Code SHA-256`

## 常見失敗

- 要求先渲染或要求 MP4 才開始程式碼審查。
- 因程式通過語法或靜態檢查就通過，即使它發明了語意或遺漏 script beat。
- 因為沒有影片，就跳過演算法 state、教學完整性、生命週期、ownership 或 cleanup 的程式碼推理。
- scene-reviewer 重做 geometry、bounding-box、碰撞、遮擋或 safe-frame 判定，而不是核對 Validator 提供的 raw finding evidence。
- 接受 Writer 自行批准、只有人工說明、沒有 exact machine-readable disposition 的 warning，或接受已因 source/hash 改變而失效的 proposal。
- 把 assumptions 過度延伸、不可追溯或新增教學內容的問題誤標成 styling。
- 回傳 `FAIL` 卻沒有指向相關程式碼或說明修復方向。
- 用過去的 MP4、截圖或畫面外觀作為渲染前程式碼審查的證據。
