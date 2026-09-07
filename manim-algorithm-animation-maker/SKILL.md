---
name: manim-algorithm-animation-maker
description: 當使用者要求以 Manim 將演算法名稱、範例輸入或執行過程製作成完整的動畫時使用。適用於需要規劃、實作、渲染及驗證動畫成品的任務；不適用於純文字演算法解說、一般非演算法動畫，或只修改既有場景的局部需求。
---

# 演算法教學動畫

## 概述
此 skill 用來把使用者的演算法需求製作成完整的 Manim 教學動畫。整個製作過程包含動畫設計、撰寫教學腳本、製作旁白、場景實作、最終渲染與交付驗證，並在 `FINAL_RENDER_AND_DELIVERY_CHECK` 階段結束。
主要負責的 agent 必須確保所有步驟依序完成，並確認每個階段都符合要求。

## Subagent 委派契約

每次委派前，協調者必須完整閱讀並遵守本 skill 的 `references/subagent-delegation-protocol.md`。

每個角色初次委派時，依協定指定的 Dispatch Profile 呼叫 `spawn_agent`。協調者只使用 Dispatch Profile 與目前階段已知資訊建構 tool arguments 及派遣訊息；角色規格與專業參考文件由 subagent 依派遣訊息讀取。後續修正若階段明確要求繼續原本的 subagent，依委派協定使用 `followup_task`。

派遣訊息必須包含 Dispatch Profile 要求的全部必要欄位，並將角色規格、project root、必要輸入、參考文件及預期產物解析為絕對路徑。不得只提供角色名稱、假設 subagent 已知道目前對話內容，或要求 subagent 自行尋找角色規則。
如果 subagent 無法讀取派遣訊息提供的角色規格路徑，協調者必須在派遣訊息中完整附上角色規格內容，不得自行摘要、刪減或改寫。

收到 subagent 的回報後，協調者必須確認以下事項：

- 回報狀態為 `DONE` 或 `BLOCKED`
- 必要產物確實存在
- 所有關卡內容都已完成驗證

不得只因 subagent 在對話中聲稱「已完成」就直接進入下一步。

## 工作流程
依序執行以下階段：

1. `ANIMATION_DESIGN`
2. `SCRIPT`
3. `VOICEOVER`
4. `SCENE_IMPLEMENTATION`
5. `FINAL_RENDER_AND_DELIVERY_CHECK`

開始每個階段前確實閱讀完成目前階段需要的參考資料，不得跳過任何階段，也不得合併、提前或補做後續階段的工作來取代目前階段。
請照各階段的描述完成工作，且該階段規定的必要產物、審查與通過條件都已滿足後，才能進入下一個階段。

## 階段 1：ANIMATION_DESIGN

### 目標
先記錄使用者需求，再由主要 Agent 與使用者共同設計五個獨立 Manim Scene；動畫設計必須遵守 five-scene contract：問題與目標、演算法如何運作、完整演示演算法並顯示答案、完成已核准 `Complexity Scope` 的複雜度分析、最終總結。

### 子階段 1：COLLECT_REQUIREMENTS
此子階段由主要 Agent 負責。開始任何行動前，必須完整閱讀並遵循 `references/how-to-collect-requirements.md`，依其要求建立 `confirmed_requirements.md`；不要提前閱讀後續子階段的參考資料。

需求確認後，完整閱讀並遵循 `references/how-to-select-and-verify-manim-render-settings.md`，建立並驗證 `<project-root>/render_profile.json`。需求蒐集完成，且該檔案已成功建立並通過驗證後，才能進入 `DESIGN_DEVELOPMENT`。

### 子階段 2：DESIGN_DEVELOPMENT
開始前，主要 Agent 必須閱讀 `confirmed_requirements.md`、`references/how-to-design-animation.md` 與 `references/how-to-design-complexity-analysis.md`，閱讀完後遵循這些文件完成 DESIGN_DEVELOPMENT。

Scene 1–3 完成後，先決定動畫要講哪些複雜度內容。主要 Agent 依 `references/how-to-design-complexity-analysis.md` 整理分析依據（`Analysis Basis`），然後以完整的 `Complexity Analysis Proposal` 向使用者提出三項選擇：主要時間複雜度、是否比較其他情況，以及空間複雜度如何呈現。

使用者明確同意後，依 `references/how-to-design-animation.md` 將分析依據、核准內容及使用者的決定寫成完整的 `Complexity Scope`，並存入 `animation_design.md`。完成記錄後，才設計 Scene 4 的複雜度分析與 Scene 5 的總結。恢復舊設計時也遵守此流程；Scene 1–3 的既有決策不代表使用者已核准複雜度內容。若核准內容之後改變，必須重新提出方案並取得同意。

五幕設計完成後，依 `references/subagent-delegation-protocol.md` 的 `animation_design_reviewer` Dispatch Profile 呼叫 `spawn_agent`，派遣新的獨立 reviewer。主要 Agent 依該 profile 解析完整的派遣訊息必要欄位；建構派遣時不讀取 reviewer 角色規格或審查 references 的內容。

修正審查問題時，若能在不改變使用者已明確選定的教學呈現、範例、視覺語意或核心動畫動作下完成，應直接修正。若修正會改變任一已選定設計決策，必須先提出具體修正方案並取得使用者同意，才能修改設計。

每次修改 `animation_design.md` 後，舊的 `animation_design_review.md` 立即失效，必須重新派遣新的獨立審查；若修改同時改變已核准 cases 或 space treatment，還必須先重新取得 scope approval。

在 subagent 明確回報 `DONE`、目前版本的 `animation_design_review.md` 存在且清楚判定為 `PASS` 後，下一步請使用者核准整份五幕設計。

只有當使用者明確核准設計後，才能離開 `ANIMATION_DESIGN` 並開始 `SCRIPT`。

## 階段 2：SCRIPT

### 目標
將已確認的需求與已核准動畫設計整理成適合教學的動畫節拍與內容順序。

### 執行事項
依 `references/subagent-delegation-protocol.md` 的 `script_writer` Dispatch Profile 呼叫 `spawn_agent`，初次派遣 writer 完成教學腳本並建立 `teaching_script.md`。

當 `script_writer` 回報 `DONE` 且 `teaching_script.md` 存在後，依同一協定的 `script_reviewer` Dispatch Profile 呼叫 `spawn_agent`，初次派遣另一個獨立 subagent 審查教學腳本並建立 `script_review_result.md`。

若 `script_review_result.md` 判定為 `FAIL`，留在 `SCRIPT`。協調者使用 `followup_task`，將該 review 的絕對路徑交回原本的 `script_writer`，由 writer 依 findings 修正 `teaching_script.md`；協調者與 reviewer 都不修改腳本。

每次修改 `teaching_script.md` 後，舊的 `script_review_result.md` 立即失效。Writer 回報 `DONE` 後，協調者使用 `followup_task` 再次啟動原本的獨立 `script_reviewer`，讓 reviewer 完整審查目前的 `teaching_script.md` 並更新 `script_review_result.md`。重複修正與完整重審，直到目前 review 判定為 `PASS`。

當 `script_reviewer` 回報 `DONE` 且其產出的 `script_review_result.md` 判定為 `PASS` 時，進入下一階段 `VOICEOVER`。

## 階段 3：VOICEOVER

### 目標
根據已通過審查的教學腳本，產生每個 beat 的旁白文字與實際音訊。

### 執行事項
依 `references/subagent-delegation-protocol.md` 的 `voiceover_generator` Dispatch Profile 呼叫 `spawn_agent`，初次派遣 generator 完成旁白文字與音訊，並建立 `voiceover.md`、`narration_manifest.json` 與 `audio/voiceover/`。

當 `voiceover_generator` 回報 `DONE` 後，協調者確認三類產物都存在、manifest 涵蓋所有 beats，且每個音檔驗證均通過。

若 subagent 回報 `BLOCKED`、必要產物缺失、manifest 未涵蓋所有 beats 或任一音檔驗證失敗，留在 `VOICEOVER`。協調者使用 `followup_task`，將具體缺口及新增或已更新輸入的絕對路徑交回原本的 `voiceover_generator` 修正；協調者不修改旁白產物。重複修正與驗證，直到目前三類產物完整、manifest 涵蓋所有 beats，且所有音檔驗證均通過。

任何音訊生成或驗證失敗都不得以靜音或其他替代方案繞過。只有目前三類產物通過上述 gate 後，才能進入 `SCENE_IMPLEMENTATION`。


## 階段 4：SCENE_IMPLEMENTATION

### 目標
將已核准的上游內容實作為五個 Scene，並在任何正式 Manim render 之前完成非渲染 layout 驗證與契約審查。此階段只能產生程式碼與 gate 證據；目前版本的 MP4 既不是必要輸出，也不得作為通關證據。

### 子階段 1：CODE_PREPARATION
依 `references/subagent-delegation-protocol.md` 的 `scene_writer` Dispatch Profile 呼叫 `spawn_agent`，初次派遣 writer。

只有原本的 `scene_writer` 回報 `DONE`，且兩個 Writer Expected outputs `generated_algo_scene.py` 與 `scene_layout_audit.py` 都存在時，`CODE_PREPARATION` gate 才能通過。若回報 `BLOCKED` 或輸出不完整，留在 `CODE_PREPARATION`，使用 `followup_task` 將具體缺口交回原本的 `scene_writer`。

Writer 必須依 `references/layout-audit.md` 建立 checkpoint adapter、明確註冊真正的 graph wrapper，且不得忽略、隱藏或降級泛用掃描產生的 warning。
可見 leaf 或 subgroup 在 checkpoint 只能有一個直接 structural owner；邏輯分類使用 Python collection，不得用同時掛入 Scene 的共享 `VGroup` 製造多 parent。Graph 內文字若被上層可見物件遮擋也必須回報 blocking `WARNING`。

### 子階段 2：PRE-LAYOUT CONTRACT REVIEW
CODE_PREPARATION gate 通過後，先依 `scene_reviewer` Dispatch Profile 初次派遣 reviewer。此時不要求 layout result；reviewer 必須完整檢查教學流程／演算法是否充分、state、beat、lifecycle、cleanup，以及每個 registered graph root 是否真為 graph 且未混入 panel、table、card、matrix、整幕或其他無關 UI。

只有 `scene_review_result.md` 為 `PRELAYOUT_PASS` 才能進入 layout。`FAIL` 時將具體 findings 交回原本的 `scene_writer` 大幅修正，再由原 reviewer 完整重審目前 source。

### 子階段 3：LAYOUT VERIFICATION AND TRIAGE
PRELAYOUT_PASS 後，依 `scene_layout_validator` Dispatch Profile 初次派遣 validator。Validator 是唯一可執行 runner、讀取完整 raw JSON 與產生 `layout_audit_result.md` 的角色；另以 `scripts/summarize_layout_audit.py` 產生 `layout_audit_summary.json` 與 `layout_audit_triage.md`。Raw JSON 與 gate result 保持權威，grouped summary 不改變任何 finding 或 PASS/FAIL。

Layout FAIL 時，Coordinator 只將 triage 路徑與指定 blocking groups 交回原本 Writer，不把完整 reports 注入 Writer context。Writer 不得自行執行 audit、讀取完整 raw JSON、降級 warning 或批准豁免；修正後由原 Validator 重跑。迭代可只跑受影響 Scene，但 final gate 必須完整重跑五幕。

泛用可見掃描中，同 graph line/line 等排版仍為 `INFO` best-effort；常見封閉 node 外形之間先排除完整 containment，再將實際 node/node overlap 視為 blocking `WARNING`，其中 Circle/Circle 使用圓形 narrow phase。其他 warning 不得忽略或降級，且 `unresolved warning count > 0` 必須 `FAIL`。

### 子階段 4：FINAL DIFF AND EXCEPTION REVIEW
Layout 修正收斂後，使用 `followup_task` 交回原本 reviewer。Reviewer 比較 pre-layout baseline 與目前 source：純位置、尺寸、間距、font size、z-index 等 layout-only diff 可聚焦複查；若 beat、文字、演算法資料、state、Transform ownership、helper 語意、graph-root 範圍或可見內容改變，必須回到完整 contract review。

若 Writer 因使用者要求或核准設計提出 exception proposal，Reviewer 必須逐筆核對 raw finding、source hash、精確 Scene/checkpoint/object pair/relation 與 supporting reference，寫出 `APPROVED` 或 `REJECTED`。Writer 不得批准自己的 proposal，Validator 也不得自行接受理由。

Reviewer 對最終 source 寫入 `Result: PASS` 與 `Final Reviewed Code SHA-256` 後，Validator 才執行最後一次完整五幕 audit，並只套用 reviewer 明確批准的 exceptions。只有 final audit `PASS`、reviewed/audited source hash 相同、summary outputs 完整且五幕 command 全部 exit `0`，Stage 4 才通過。

### Source-repair invariant
語義或結構性修改會同時使 pre-layout review、final review 與 layout evidence 失效，回到完整 PRE-LAYOUT CONTRACT REVIEW。明確的 layout-only 修改可保留 pre-layout baseline，但仍須 final focused review；任何 source 修改都使舊 raw reports、summary、final review hash 與 exceptions 失效。對已派遣角色一律使用 `followup_task` 重用原 target。

### 必要輸出
Stage 4 只建立並接受：

- `generated_algo_scene.py`
- `scene_layout_audit.py`
- `layout_audit_result.md`
- `layout_audit_summary.json`
- `layout_audit_triage.md`
- 五個完整 `layout_audit_report.<SceneClass>.json`
- 每幕專用的 layout exception JSON（只有核准來源明確要求 warning disposition 時）
- `scene_review_result.md`

五個 Scene MP4、合併 MP4 與 `render_manifest.md` 都屬於 Stage 5，不得用來補足或取代 Stage 4 gate。

### Exit gate
只有以下條件全部成立才能進入 `FINAL_RENDER_AND_DELIVERY_CHECK`：

- `layout_audit_result.md = PASS`，五個核准 Scene 的必要命令都 exit `0`。
- `layout_audit_summary.json` 與 `layout_audit_triage.md` 都存在並記錄於 layout result；兩者只作 derived navigation，不取代 raw gate。
- 五個完整 machine-readable visible reports 都存在並保留 graph 內的 `INFO`，且每幕 unresolved warnings 與 errors 都是 `0`；accepted warnings 皆有有效精確例外。
- `scene_review_result.md = PASS`，且由未參與程式碼撰寫的獨立 reviewer 產出。
- 目前 `generated_algo_scene.py` SHA-256、layout result 的 `Audited Code SHA-256` 與 review result 的 `Final Reviewed Code SHA-256` 全部一致；所有 accepted warning 都在 review result 中逐筆 `APPROVED`。
- layout result 記錄的 `Render Profile SHA-256` 等於目前 `render_profile.json` 的 SHA-256。
- PASS 後程式碼、Stage 4 Required inputs、runner 或 `render_profile.json` 都沒有改變。

本機自行檢查、dry-run 可執行、非正式 review 或提早產生的 MP4 都不能取代上述 gate。

## 階段 5：FINAL_RENDER_AND_DELIVERY_CHECK

### 目標
直接使用 Stage 4 已通過的目前 source 與 `render_profile.json` 完成正式渲染、建立 render evidence，並執行技術性交付檢查。Layout 與演算法語意以 Stage 4 的核准證據為準。

Stage 5 直接承接 Stage 4 的 `Exit gate`；正式渲染的核准集合是 Stage 4 核准的 scene source、`layout_audit_result.md` 與 `scene_review_result.md`。

### 子階段 1：FINAL_RENDER
依 `references/subagent-delegation-protocol.md` 的 `scene_final_renderer` Dispatch Profile 呼叫 `spawn_agent`，初次派遣 renderer。

只有原本的 `scene_final_renderer` 回報 `DONE`，且該 profile 的全部 Expected outputs 存在時，`FINAL_RENDER` gate 才能通過。若回報 `BLOCKED` 或輸出不完整，依下方 Stage 5 repair and rollback invariant 處理。

### 子階段 2：DELIVERY_CHECK
`FINAL_RENDER` 完成後，由 coordinator 執行交付檢查。

- project inputs：`generated_algo_scene.py`、`render_profile.json`、`render_manifest.md`、五個 Scene MP4 與合併 MP4
- delivery helper：`scripts/verify_delivery.py` 的絕對路徑
- 預期產物：`delivery_check_result.md`

執行：

```bash
<profile-python> <absolute-skill-root>/scripts/verify_delivery.py --source <absolute-project-root>/generated_algo_scene.py --profile <absolute-project-root>/render_profile.json --manifest <absolute-project-root>/render_manifest.md --output <absolute-project-root>/delivery_check_result.md
```

Helper 以唯讀方式對五個 Scene MP4 + combined MP4 = 六個 MP4 執行 `ffprobe`、解碼 combined MP4，並檢查 video/audio streams、解析度、frame rate、duration 與 render exit codes。

任一 `ffprobe` 或 combined decode 失敗時，依下方 Stage 5 repair and rollback invariant 處理。

### Stage 5 repair and rollback invariant
若問題只涉及輸出、render command、concat、manifest 或 media decode，且 source、render profile 與 Stage 4 gate evidence 都未改變，留在 `FINAL_RENDER`。Coordinator 使用 `followup_task` 將失敗證據與需重建的絕對路徑交回原本的 `scene_final_renderer`，由 renderer 依 render guide 修復受影響的輸出與 manifest。Renderer 回報 `DONE` 且目前 Expected outputs 完整後，Coordinator 重新執行 `DELIVERY_CHECK`。

若 Stage 4 PASS 後程式碼改變，回到 Stage 4 `CODE_PREPARATION`；若 `render_profile.json` 改變，回到 `CODE_PREPARATION`；若 profile 未改變但執行環境、runner 或 summarizer 改變，回到 `LAYOUT VERIFICATION AND TRIAGE` 並重建 final audit evidence；若上游需求、設計、腳本或旁白契約改變，回到擁有該內容的 Stage。只要重新產生任一 MP4 或 manifest，舊的 `delivery_check_result.md` 立即失效；必須依目前產物重新執行 `DELIVERY_CHECK`。

### 必要輸出與 Exit gate
Stage 5 必須建立：

- 依核准順序的五個非空 Scene MP4
- 非空的最終合併 MP4
- `render_manifest.md`
- `delivery_check_result.md = PASS`

Delivery result 必須記錄六個 `ffprobe` 結果、combined decode 結果、媒體規格與 duration comparison。
