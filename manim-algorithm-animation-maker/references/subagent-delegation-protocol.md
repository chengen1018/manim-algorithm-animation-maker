# Subagent Delegation Protocol

本文件定義協調者如何把工作委派給 subagent。不得只用角色名稱要求 subagent 自行推測工作。

## 派遣資料

每次委派前，協調者必須準備：

- `skill root`：包含本 skill `SKILL.md` 的目錄絕對路徑；角色規格、skill references 與 skill scripts 都從此目錄解析。
- `project root`：本次動畫產物所在工作目錄的絕對路徑。
- subagent 的角色規格、必要參考文件、腳本、專案輸入與預期輸出的絕對路徑。

`skill root` 與 `project root` 可以是不同目錄。不得以 Git root 或目前 working directory 取代已確定的 project root。

傳給 subagent 的角色規格、必要參考文件、腳本、專案輸入與輸出一律使用絕對路徑。

若 subagent 無法讀取派遣訊息提供的角色規格路徑，協調者必須先完整讀取角色規格，將規格全文放進派遣訊息；不得自行摘要、重寫或補造角色規則。

## 角色對應

| 工作 | task name | 角色規格 | `fork_turns` | model | reasoning effort |
| --- | --- | --- | --- | --- | --- |
| 動畫設計審查 | `animation_design_reviewer` | `references/subagent-animation-design-reviewer.md` | `none` | `gpt-5.6-terra` | `high` |
| 教學腳本撰寫 | `script_writer` | `references/subagent-script-writer.md` | `none` | `gpt-5.6-sol` | `high` |
| 教學腳本審查 | `script_reviewer` | `references/subagent-script-reviewer.md` | `none` | `gpt-5.6-terra` | `high` |
| 旁白產生 | `voiceover_generator` | `references/subagent-voiceover-generator.md` | `none` | `gpt-5.6-luna` | `medium` |
| 場景程式碼 | `scene_writer` | `references/subagent-scene-writer.md` | `none` | `gpt-5.6-sol` | `high` |
| 場景程式碼審查 | `scene_reviewer` | `references/subagent-scene-reviewer.md` | `none` | `gpt-5.6-terra` | `high` |
| 渲染前 Scene 版面驗證 | `scene_layout_validator` | `references/subagent-scene-layout-validator.md` | `none` | `gpt-5.6-luna` | `medium` |
| 正式場景渲染與合併 | `scene_final_renderer` | `references/subagent-scene-final-renderer.md` | `none` | `gpt-5.6-luna` | `xhigh` |

每次呼叫 `spawn_agent` 時，必須將角色對應列中的 `task_name`、`fork_turns`、`model` 與 `reasoning_effort` 明確傳為 tool arguments。這些設定不得只寫入派遣 `message`。若 runtime 不接受指定的 model 或 reasoning effort，回報 `BLOCKED`；不得自行改用其他設定。

Dispatch Profile 只用於角色的初次 `spawn_agent`。協調者必須保留 `spawn_agent` 回傳的 target；當階段明確要求原本的 subagent 修正或重審時，使用 `followup_task` 對該 target 發送本次工作，以及新增或已更新輸入的絕對路徑，不重新呼叫 `spawn_agent`。

## Dispatch Profile: `animation_design_reviewer`

主要 Agent 使用本 profile 建構派遣，不讀取角色規格或審查 references 的內容。路徑由本次動畫的 skill root、project root，以及 DESIGN_DEVELOPMENT 已使用的專用 reference 解析。

### Tool arguments

- `task_name`: `animation_design_reviewer`
- `fork_turns`: `none`
- `model`: `gpt-5.6-terra`
- `reasoning_effort`: `high`

### 派遣訊息必要欄位

`Role spec`：`references/subagent-animation-design-reviewer.md` 的絕對路徑。

`Project root`：本次動畫 project root 的絕對路徑。

`Required inputs` 必須逐項包含：

- `Confirmed requirements`：`<project-root>/confirmed_requirements.md`
- `Animation design`：`<project-root>/animation_design.md`
- `Review guide`：`references/how-to-review-design.md` 的絕對路徑
- `Complexity analysis guide`：`references/how-to-design-complexity-analysis.md` 的絕對路徑

`Conditional inputs` 必須逐項包含：

- `Specialized reference`：Designer 本次實際使用的唯一一份專用 reference 絕對路徑；沒有適用的專用 reference 時寫 `None — no applicable specialized reference`

`Expected output`：`<project-root>/animation_design_review.md`。

不得省略 conditional 欄位；使用上述 `None` 值讓 reviewer 能區分「不適用」與「派遣遺漏」。使用者提供的 code 或 pseudocode 已完整保存在 `confirmed_requirements.md`，不作為額外派遣輸入。

## Dispatch Profile: `script_writer`

主要 Agent 使用本 profile 建構派遣，不讀取角色規格或寫作指南的內容。所有路徑由本次動畫的 skill root 與 project root 解析。

### Tool arguments

- `task_name`: `script_writer`
- `fork_turns`: `none`
- `model`: `gpt-5.6-sol`
- `reasoning_effort`: `high`

### 派遣訊息必要欄位

`Role spec`：`references/subagent-script-writer.md` 的絕對路徑。

`Project root`：本次動畫 project root 的絕對路徑。

`Required inputs` 必須逐項包含：

- `Confirmed requirements`：`<project-root>/confirmed_requirements.md`
- `Animation design`：`<project-root>/animation_design.md`
- `Teaching script guide`：`references/how-to-write-teaching-script.md` 的絕對路徑

`Conditional inputs`：`None — no conditional inputs`。

`Expected output`：`<project-root>/teaching_script.md`。

## Dispatch Profile: `script_reviewer`

主要 Agent 使用本 profile 建構派遣，不讀取角色規格或審查指南的內容。所有路徑由本次動畫的 skill root 與 project root 解析。

### Tool arguments

- `task_name`: `script_reviewer`
- `fork_turns`: `none`
- `model`: `gpt-5.6-terra`
- `reasoning_effort`: `high`

### 派遣訊息必要欄位

`Role spec`：`references/subagent-script-reviewer.md` 的絕對路徑。

`Project root`：本次動畫 project root 的絕對路徑。

`Required inputs` 必須逐項包含：

- `Confirmed requirements`：`<project-root>/confirmed_requirements.md`
- `Animation design`：`<project-root>/animation_design.md`
- `Teaching script`：`<project-root>/teaching_script.md`
- `Teaching script guide`：`references/how-to-write-teaching-script.md` 的絕對路徑

`Conditional inputs`：`None — no conditional inputs`。

`Expected output`：`<project-root>/script_review_result.md`。

## Dispatch Profile: `voiceover_generator`

主要 Agent 使用本 profile 建構派遣，不讀取角色規格、旁白指南或 helper 的內容。所有路徑由本次動畫的 skill root 與 project root 解析。

### Tool arguments

- `task_name`: `voiceover_generator`
- `fork_turns`: `none`
- `model`: `gpt-5.6-luna`
- `reasoning_effort`: `medium`

### 派遣訊息必要欄位

`Role spec`：`references/subagent-voiceover-generator.md` 的絕對路徑。

`Project root`：本次動畫 project root 的絕對路徑。

`Required inputs` 必須逐項包含：

- `Confirmed requirements`：`<project-root>/confirmed_requirements.md`
- `Animation design`：`<project-root>/animation_design.md`
- `Teaching script`：`<project-root>/teaching_script.md`
- `TTS config`：`<project-root>/.tts-config`
- `Voiceover guide`：`references/how-to-write-and-generate-voiceover.md` 的絕對路徑
- `Voiceover helper`：`scripts/generate_voiceover_audio.py` 的絕對路徑

`Conditional inputs`：`None — no conditional inputs`。

`Expected output` 必須逐項包含：

- `Voiceover script`：`<project-root>/voiceover.md`
- `Narration manifest`：`<project-root>/narration_manifest.json`
- `Voiceover audio`：`<project-root>/audio/voiceover/`

## Dispatch Profile: `scene_writer`

主要 Agent 使用本 profile 建構派遣，不讀取角色規格、實作 reference 或 layout helper 的內容。所有路徑由本次動畫的 skill root 與 project root 解析。

### Tool arguments

- `task_name`: `scene_writer`
- `fork_turns`: `none`
- `model`: `gpt-5.6-sol`
- `reasoning_effort`: `high`

### 派遣訊息必要欄位

`Role spec`：`references/subagent-scene-writer.md` 的絕對路徑。

`Project root`：本次動畫 project root 的絕對路徑。

`Required inputs` 必須逐項包含：

- `Confirmed requirements`：`<project-root>/confirmed_requirements.md`
- `Animation design`：`<project-root>/animation_design.md`
- `Animation design review`：`<project-root>/animation_design_review.md`
- `Teaching script`：`<project-root>/teaching_script.md`
- `Script review result`：`<project-root>/script_review_result.md`
- `Voiceover script`：`<project-root>/voiceover.md`
- `Narration manifest`：`<project-root>/narration_manifest.json`
- `Voiceover audio`：`<project-root>/audio/voiceover/`
- `Render profile`：`<project-root>/render_profile.json`
- `Implementation guide`：`references/how-to-implement-and-verify-manim-scenes.md` 的絕對路徑
- `Layout audit guide`：`references/layout-audit.md` 的絕對路徑
- `Layout helper`：`scripts/scene_layout_audit.py` 的絕對路徑

`Conditional inputs`：初次派遣為 `None — no conditional inputs`；layout 修正 follow-up 只附 `Layout audit triage`（`<project-root>/layout_audit_triage.md`）與 Coordinator 指定的 blocking group，不附完整 raw JSON。

`Expected output` 必須逐項包含：

- `Scene source`：`<project-root>/generated_algo_scene.py`
- `Project layout helper`：`<project-root>/scene_layout_audit.py`

## Dispatch Profile: `scene_layout_validator`

主要 Agent 使用本 profile 建構派遣，不讀取角色規格、layout reference 或 runner 的內容。所有路徑由本次動畫的 skill root 與 project root 解析；五個 Scene class 與核准順序由已核准的 `animation_design.md` 及目前 `generated_algo_scene.py` 解析。

### Tool arguments

- `task_name`: `scene_layout_validator`
- `fork_turns`: `none`
- `model`: `gpt-5.6-luna`
- `reasoning_effort`: `medium`

### 派遣訊息必要欄位

`Role spec`：`references/subagent-scene-layout-validator.md` 的絕對路徑。

`Project root`：本次動畫 project root 的絕對路徑。

`Required inputs` 必須逐項包含：

- `Scene source`：`<project-root>/generated_algo_scene.py`
- `Project layout helper`：`<project-root>/scene_layout_audit.py`
- `Render profile`：`<project-root>/render_profile.json`
- `Pre-layout Scene review result`：`<project-root>/scene_review_result.md`（必須為 `PRELAYOUT_PASS`；final run 必須為 `PASS`）
- `Layout audit guide`：`references/layout-audit.md` 的絕對路徑
- `Layout audit runner`：`scripts/run_layout_audit.py` 的絕對路徑
- `Layout audit summarizer`：`scripts/summarize_layout_audit.py` 的絕對路徑

`Conditional inputs`：Reviewer 明確批准的 per-Scene exception paths/hashes；沒有時明記 none。未批准 proposal 不得派給 Validator 使用。

`Required dispatch data` 必須包含：

- `Scene classes and approved order`：已核准設計的 Scene 1–5 對應目前 source 的五個 Scene class；必須逐項照錄
- `Validation phase`：初次為 `initial`、Writer layout 修正後為 `iteration`、Reviewer final `PASS` 後為 `final`

`Expected output` 必須逐項包含：

- `Layout audit result`：`<project-root>/layout_audit_result.md`
- `Layout audit grouped summary`：`<project-root>/layout_audit_summary.json`
- `Layout audit triage`：`<project-root>/layout_audit_triage.md`

## Dispatch Profile: `scene_reviewer`

主要 Agent 使用本 profile 建構派遣，不讀取角色規格或審查 reference 的內容。所有路徑由本次動畫的 skill root 與 project root 解析。

### Tool arguments

- `task_name`: `scene_reviewer`
- `fork_turns`: `none`
- `model`: `gpt-5.6-terra`
- `reasoning_effort`: `high`

### 派遣訊息必要欄位

`Role spec`：`references/subagent-scene-reviewer.md` 的絕對路徑。

`Project root`：本次動畫 project root 的絕對路徑。

`Required inputs` 必須逐項包含：

- `Confirmed requirements`：`<project-root>/confirmed_requirements.md`
- `Animation design`：`<project-root>/animation_design.md`
- `Animation design review`：`<project-root>/animation_design_review.md`
- `Teaching script`：`<project-root>/teaching_script.md`
- `Script review result`：`<project-root>/script_review_result.md`
- `Scene source`：`<project-root>/generated_algo_scene.py`
- `Project layout helper`：`<project-root>/scene_layout_audit.py`
- `Scene review guide`：`references/how-to-review-manim-scene-code.md` 的絕對路徑

`Required dispatch data` 必須包含 `Review phase`：初次為 `initial-full`，layout 收斂後為 `final-focused`。

`Conditional inputs`：

- `initial-full`：`None — no conditional inputs`。
- `final-focused`：目前 `<project-root>/scene_review_result.md`、`<project-root>/layout_audit_triage.md`、raw report paths/hashes，以及所有 exception proposal paths/hashes；沒有 proposal 時明記 none。

`Expected output`：`<project-root>/scene_review_result.md`。

## Dispatch Profile: `scene_final_renderer`

主要 Agent 使用本 profile 建構派遣，不讀取角色規格或 render guide 的內容。所有路徑由本次動畫的 skill root 與 project root 解析；五個 Scene class、核准順序與對應的 Scene MP4 目標路徑由目前 `layout_audit_result.md`、`render_profile.json` 與 Manim 輸出規則解析。

### Tool arguments

- `task_name`: `scene_final_renderer`
- `fork_turns`: `none`
- `model`: `gpt-5.6-luna`
- `reasoning_effort`: `xhigh`

### 派遣訊息必要欄位

`Role spec`：`references/subagent-scene-final-renderer.md` 的絕對路徑。

`Project root`：本次動畫 project root 的絕對路徑。

`Required inputs` 必須逐項包含：

- `Scene source`：`<project-root>/generated_algo_scene.py`
- `Project layout helper`：`<project-root>/scene_layout_audit.py`
- `Layout audit result`：`<project-root>/layout_audit_result.md`
- `Scene review result`：`<project-root>/scene_review_result.md`
- `Render profile`：`<project-root>/render_profile.json`
- `Render guide`：`references/how-to-render-approved-manim-scenes.md` 的絕對路徑

`Conditional inputs`：`None — no conditional inputs`。

`Required dispatch data` 必須包含：

- `Scene classes and approved order`：`layout_audit_result.md` 所列的五個 Scene class；必須逐項照錄

`Expected output` 必須逐項包含：

- `Scene MP4 files`：依核准順序逐項列出五個 Scene MP4 的 resolved absolute path
- `Combined MP4`：最終合併 MP4 的 resolved absolute path
- `Render manifest`：`<project-root>/render_manifest.md`

## 共通派遣規則與訊息格式

每次派遣 subagent 時，訊息必須明確包含：

1. **本次唯一角色與工作階段。**
   用途：界定 subagent 這次負責的身分與流程位置，避免同一個 subagent 同時承擔 writer、reviewer 或其他階段的工作，也避免提前處理尚未指派的內容。
2. **角色規格的絕對路徑，並要求開始任何動作前完整閱讀。**
   用途：角色規格與 routed professional guides 共同提供這次工作的完整規則、Preflight、禁止事項與完成條件，讓 subagent 不必根據角色名稱自行猜測。
3. **project root 的絕對路徑。**
   用途：指定本次動畫專案唯一的工作目錄，讓 subagent 知道專案輸入應從哪裡讀取、產物應寫到哪裡，避免操作到其他專案或 skill 資料夾。
4. **Dispatch Profile 要求的完整 `Required inputs`、`Conditional inputs`、`Required dispatch data`（若有定義）與 `Expected output`。**
   用途：明確指定這次工作的權威來源及執行指南，避免 subagent 因找不到工作指南而自行判斷並完成工作
5. **完成後明確回報 `DONE` 或 `BLOCKED`。**
   用途：提供協調者一致且可判讀的工作狀態。`DONE` 表示可以開始檢查必要產物與關卡，`BLOCKED` 表示必須先處理阻塞；狀態回報本身不等於產物已通過驗證。

使用下列訊息骨架；不得省略欄位：

```text
你負責本次 <ROLE / STAGE> 工作。

角色規格：
<absolute-role-spec-path>

工作目錄：
<absolute-project-root>

Required inputs：
- <label>: <absolute-path>

Conditional inputs：
<每個適用欄位的 label 與絕對路徑，或 Dispatch Profile 指定的 explicit None>

<只有 Dispatch Profile 定義時才加入：
Required dispatch data：
<profile 指定的欄位與值>>

Expected output：
<每個預期產物的 label 與絕對路徑>

開始任何動作前：
1. 完整閱讀角色規格與所有 routed professional guides。
2. 確認並完整閱讀所有 `Required inputs`。
3. 完整閱讀所有不是 `None` 的 `Conditional inputs`。
4. 只執行角色規格或 routed professional guide 為本次派遣角色定義的 `Preflight`；若兩者未定義，依角色規格明列的 gate ownership 與 input checks 執行。

不要執行任何未指派的後續階段。

如果必要輸入缺失、無法讀取、互相矛盾：
- 不得猜測。
- 不得建立看似完整的替代內容。
- 回報 BLOCKED，列出檔案、證據位置與需要協調者處理的事項。

完成後依角色規格回報 DONE 或 BLOCKED。
```

## 協調者驗證

協調者擁有階段順序與 gate。只有目前階段 Exit gate 通過後才派遣下一階段 subagent；subagent 接受派遣時，應把上游 gate 視為已由協調者確認，並只執行角色規格所列的本階段檢查。

subagent 回報後，協調者應確認工作可安全交接：

1. 確認 subagent 明確回報 `DONE`；若回報 `BLOCKED`，停止目前階段並處理其說明的問題。
2. 確認所有必要輸出存在。
3. 確認輸出符合目前關卡的必要內容；審查角色的 `PASS` 或 `FAIL` 以實際審查檔內容為準，不以聊天摘要代替。
4. 只有確認可安全交接後才能繼續下個步驟。
5. 協調者不得自行補寫角色遺漏的專業內容；應把具體缺口退回原 subagent 修正，或依流程退回上游。

Writer 與 reviewer 必須是不同的 subagent。Reviewer 不得審查自己曾撰寫、修改或共同撰寫的產物。
