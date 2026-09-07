# Manim 實作與首次靜態驗證指南

本指南定義 `generated_algo_scene.py` 的實作方法與首次送檢前的靜態推理。它以 construction patterns 降低第一版 layout 失誤機率；獨立 scene reviewer 先完整檢查語義與 graph 分類，獨立 layout validator 再檢查 layout，最後由原 reviewer 聚焦複查 layout diff 與 exception proposals。

## 實作責任與不可改變事項

依 `animation_design.md` 的 Scene 1–5 核准順序實作五個獨立 Manim `Scene` 類別，不以 `Section` 代替，也不在實作階段重新定義每幕的教學責任。每個 Scene 獨立建立及清理畫面，結尾淡出至空白，下一幕再從空白淡入；程式碼通過獨立審查後，才將五幕分別渲染並依核准順序合併。

Scene 4 必須逐 beat 實作已核准的 Visual Derivation，並沿用 Scene 3 已核准的工作單位與視覺語意；不得在 complexity derivation 中改換計數單位、資料狀態或可見操作的意義。

Scene layer 負責 layout execution、styling、timing、beat staging，以及 audio/overlay synchronization。實作必須忠於 `confirmed_requirements.md`、`animation_design.md`、`teaching_script.md`、`voiceover.md`、`narration_manifest.json` 與音訊資產；使用者提供的 algorithm code／pseudocode 只使用 `confirmed_requirements.md` 內保存的內容。不得新增演算法步驟、教學目標、support-structure 語意，或改變 movement semantics、pointer meaning、visited timing、beat 順序與已核准的 active support structure。

所有 Scene 必須使用 `render_profile.json` 指定的 frame geometry 與字型。不得用另一個 Python、Manim profile 或 fallback font 進行 layout 規劃。

可以依演算法採不同程式結構，但 style roles、layout setup、beat execution、visibility ownership 與 final cleanup 必須容易稽核。使用 `ROLE_BASE`、`ROLE_FOCUS`、`ROLE_SETTLED`、`ROLE_SUPPORT`、`POINTER_LABEL_BUFF` 等語意常數，避免散落且無法解釋的數值。

## 寫 code 前：先完成 Layout Planning

每個 Scene 寫 code 前都要有 layout plan，至少定義：

- **primary structure**：陣列、圖、樹或表格等主視覺。
- **persistent regions**：標題、狀態 panel、公式或核准的 overlay 等持續區域。
- **transient regions**：比較卡片、pointer labels、臨時公式與說明。
- **safe frame**：所有必要內容都必須落入的內縮邊界。
- **peak state**：同時物件最多、文字最長、pointer 最密集或最容易越界的穩定 beat；Scene 4 必須預留長 expression、case label、多變數圖演算法與 auxiliary-space diagram 的 peak-state 空間。
- **collision policy**：空間不足時要採縮放、換區、上下分流、合併標籤或合法分階段顯示中的哪一種策略。

layout plan 不要求額外文件，但必須反映在 layout constants、zones、builders、groups 與 helper interfaces，使程式本身可稽核。建立順序採用下方 **Peak-first scene skeleton** 與 **Stable-zone composition**。

## Manim Frame、座標與尺寸推理

Manim frame 的水平範圍是 `[-config.frame_x_radius, config.frame_x_radius]`，垂直範圍是 `[-config.frame_y_radius, config.frame_y_radius]`。safe frame 應在四邊保留一致的內縮 margin，而不是讓內容剛好貼住 frame。

安全性要依定位完成後的最終 bounding box 判斷：`get_left()[0]`、`get_right()[0]`、`get_top()[1]`、`get_bottom()[1]` 都必須落在對應 safe frame 邊界內。不能只看 object center、單一 width/height 或動畫起點；縮放、文字替換及群組變更後都要重新推理最終邊界。

## Layout Zones 與安全邊界

先把 primary structure、side panel、標題/公式與 transient content 分配到不重疊 zones，再在各 zone 內定位。主結構與 side panel 必須先共同做寬度預算；寬主結構禁止在未預留 zone 時直接向右 `next_to()` 串接 target、output 或說明卡片。

若組合超過 safe frame，應重分雙欄或上下 zones、整體縮放可縮放群組、縮短 label，或依 script 合法分 beat 揭露。多個物件各自位於 frame 內，不代表它們組合後不碰撞；標題、狀態、主視覺與 transient 說明也不能各自 `to_edge()` 後就假設安全。

主要結構的位置與 zone 語意應跨 beats 穩定。除非消失本身是教學內容，resolved regions 應淡化而非任意搬移或刪除；語意必要的 support structure 必須持續存在。

## 物件定位與群組排版

下列 API 都只處理局部幾何，不是整體自動排版：

- `next_to()` 只相對另一物件定位，不保證新物件仍在 safe frame，也不替第三個物件留位。
- `to_edge()` 只把被呼叫的物件靠向 frame edge，不知道其他 zones 或物件的空間需求。
- `move_to()` 對齊位置，不會處理來源與目標的寬高差異或周邊碰撞。
- `arrange()` 只安排群組內部間距，不代表完成後群組適合所分配的 zone。
- `Transform()` 只描述來源到目標的局部變化；仍須考慮來源、目標和未移除相鄰物件在穩定狀態中的整體幾何與語意。

每條 positioning chain（例如 `.to_edge(...).shift(...).next_to(...)`）完成後，都要依最終 bounding box 重新推理整個 group 的寬高與四邊界。若定位只靠無語意的連續位移數值才能成立，將 magic shift 改為 zone、anchor、group arrangement 或明確 layout constant。元素抬起、比較、交換或重新排列時，也要保留可讀間距並檢查群組 peak state。

## 文字、卡片、公式與 Panel 容量

Panel 的容量決策必須涵蓋所有穩定 beats 的內容，動態文字使用固定 anchor 與明確最大寬度；具體建立方式見 **Content-first containers**。替換後仍要推理文字、padding、panel border、主結構與 safe frame 的組合。

長內容優先縮短措辭、合理換行、增加 panel 容量或移至專屬 zone，不能靠縮到不可讀來處理過載。結構差異大的多行文字不用 morph-style transform，改用直接 replacement、短 fade swap 或穩定 panel sections；單字元 labels、row/column headers 不得被實心 highlight 遮住，應使用顏色、底線、相鄰 marker 或可讀的 outline treatment。

畫面文字應說明當前規則或觀察，而非逐字重複旁白。穩定 beat 的文字必須可讀，不能以過渡中的短暫狀態當作清晰度依據。

## Pointer、Label 與共址衝突

每次 pointer 移動前，必須檢查目的 index 的現有或已存在 pointers，而不只計算自身目的位置。共址策略與 builder 方式見 **State-first pointer layout**；語意允許時可顯示 `left = mid = right = 5`。

Pointer 的起點與終點都要可辨，label 使用實際演算法名稱並維持一致空間語意。目的地改變後，重新檢查 arrows、labels、cell contents、相鄰 pointers 與 panel 是否共同 fit，而不是只檢查 marker center。

## Phase Ownership、Transform 與物件生命週期

每個 helper、label、highlight 與 support structure 都要定義：首次出現的 phase/beat、持續哪些 beats、如何更新，以及何時移除。程式應維持明確的 role、pointer、layout 與 beat state，不從當前外觀反推語意。

靜態推理必須區分物件是仍在 `scene.mobjects`、只是透明、被其他物件遮擋，或真正移除。尚不該存在的物件應延後建立/加入；已加入的透明物件必須有明確且可驗證的 reveal path。不要假設 `FadeIn` 必然修復既存透明物件。

`Transform()` 可能改變既有 reference 的幾何與語意，但不會自動清除其他 references 或 helpers；需要替換所有權時依 **Current-object replacement ownership** 維持 current reference，需要結束生命週期時使用 `FadeOut`、`remove()` 或集中 cleanup。Helper 的建立時機見 **Phase-owned helper construction**。

Intro 不得洩漏 future-iteration、traceback 或 finalization helpers；fill/update helpers 不得無理由殘留到 reconstruction/final result。最後畫面要移除、淡化或安靜化過期 labels、helper marks、暫時公式與中介指示，只保留最終結果及 script 核准且仍具教學價值的脈絡。

## Construction Patterns：以構造降低失敗機率

以下 patterns 是建立 Scene 的方式，不是固定視覺模板。依演算法選擇 zones、形狀與風格，但讓容量、共址和生命週期在建立物件時就被一起考慮。

### Peak-first scene skeleton

先找出資訊最密、文字最長、pointer 最集中的穩定狀態，為它的完整內容預留 zones，再實作較簡單 beats。較簡單狀態沿用骨架，不從稀疏開場向外追加物件。

### Group-first zone fitting

先完成一個 zone 的完整 semantic group（例如 array、indices、pointers 與該區 labels），再用 `arrange()`、`scale_to_fit_width()` 和 `move_to()` 把 group 當整體放進 zone。不要以連續 `next_to()`／`shift()` 從 anchor 向外生長，因為後加入的元素沒有被納入前面的空間決策。

### Content-first containers

先建立所有候選動態文字或公式，決定最大可讀 line plan，再由最大候選推導 card/panel 尺寸。候選可以先建構供規劃，但只有 current candidate 加入 Scene。

Bad：第一個短字串決定固定框，後續才向內塞。

```python
body = Text(messages[0], font_size=28)
panel = RoundedRectangle(width=body.width + 0.5, height=1.0)
```

Good：先為所有候選決定可讀的分行版本，用固定字級建構，container 再取最大尺寸。

```python
line_plans = [
    "搜尋中",
    "目標較大\n移動左界",
    "left = mid = right\n只剩一個候選",
]
candidates = [Text(text, font_size=28) for text in line_plans]
max_width = max(item.width for item in candidates)
max_height = max(item.height for item in candidates)
panel = RoundedRectangle(width=max_width + 0.6, height=max_height + 0.4)
current_body = candidates[0].move_to(panel)
```

若最大候選仍超出預留 zone，回頭調整 wording、line plan、zone allocation 或 staging；不要以無下限縮放補救。

### State-first pointer layout

把當下所有 active pointer roles 與 destinations 一次傳給同一 builder／placement decision，再建立完整 pointer groups。builder 先按 destination 分組；共享 index 時選 lanes、上下兩側、共享 marker 加 legend，或在語意等價時合併，而不是各 label 獨立定位後才修補。

Bad：每個 pointer 各自使用相同偏移。

```python
pointers = [make_pointer(role, cells[index], DOWN) for role, index in state.items()]
```

Good：完整 state 共同決定 lane 與方向。

```python
def build_pointers(state, cells):
    by_index = group_roles_by_destination(state)
    return VGroup(*(make_pointer_group(roles, cells[index])
                    for index, roles in by_index.items()))

pointer_group = build_pointers({"left": left, "mid": mid, "right": right}, cells)
```

### Current-object replacement ownership

對可替換文字或 helper group 保留恰好一個 current reference。`ReplacementTransform` 後立即重新綁定；規劃用 future candidates 不提早加入 Scene。

Bad：動畫完成後仍把舊 reference 當作 current。

```python
self.play(ReplacementTransform(current_body, next_body))
self.play(current_body.animate.set_color(YELLOW))
```

Good：replacement 後 ownership 與 Scene 中的物件一致。

```python
next_body.move_to(panel)
self.play(ReplacementTransform(current_body, next_body))
current_body = next_body
```

### Phase-owned helper construction

Helper 在擁有它的 beat／phase 才建立，或由 builder 只回傳 current phase set。不要預先加入 future helpers 再藏起來；只有確實需要且已有明確 reveal path 時才保留隱藏物件。

### Stable-zone composition

title、status、primary、transient regions 在相鄰 beats 維持穩定意思。空間不足時調整 zone allocation、grouping、wording 或 staging；不要累積 magic shifts，讓同一位置在不同 beat 無故改變語意。

## Beat Staging 與教學呈現

每個 beat 只提出 **one visual question at a time**，保留一個主要焦點群組，並能回答觀眾應看哪裡、哪些物件承載焦點、beat 結束後留下何種進度線索。實作遵循：

- **visual continuity**：同一概念盡量由同一物件延續，避免無理由換位或重建。
- **spatial meaning**：同一位置與 zone 維持穩定語意。
- **progressive disclosure**：物件只在需要時出現，避免預先塞滿畫面。
- **meaningful transformation**：移動表示狀態變化，不做裝飾性繞路。
- **visual economy**：刪減重複文字與無教學作用的裝飾，不把所有內容縮小硬塞。
- **peak-state composition**：先確保資訊最密集的穩定畫面清楚。
- **pause on resolved states**：在已解決狀態留下足以辨識的 hold。

引入新焦點前先移除或淡化舊焦點。Loop-oriented code 可以接受，但可見動作仍須讀成 teaching beats，且不以 animation polish 犧牲焦點清晰度。

Scene 4 的每個必要 derivation phase 都要在 resolved state 呼叫具名 layout checkpoint，涵蓋該 phase 當下可見的公式、case label、圖或 auxiliary-space diagram；不能只檢查完整公式最後出現的畫面。

## Voiceover 與 Overlay 的實作約束

每個核准 beat 對應一個 voiceover segment；narration 開始前先建立 visual focus，segment 期間維持一致，結束前呈現或停留在 resolved state。旁白較長時以 pacing、staging 或有意義的 hold 配合，不用無意義空白，也不改變核准語意。

Overlays 關閉時不預留只供 overlay 使用的空間；啟用時放在 layout plan 的穩定 persistent region，納入 peak-state bounding box 與 collision audit，不得遮住主要教學結構。

## 演算法常見結構模式

### Arrays

- 先以最大元素數、最長 cell content、所有 index labels 與 compare/update 動作計算 peak-state group。
- 隔離 active operation，保持其餘陣列與元素間距可讀；settled progress 不搶走主要焦點。
- Side cards 必須使用已預留 zone，不得在寬陣列右側臨時串接。
- 多 pointers 的目的 index 可能重合，逐次移動都套用共址 collision policy。

### Search Windows

- Active window 是持續且一致的整體區域；區分 boundary pointers 與 current probe。
- Elimination 後保留更新後 window，並在相關 beat 全程維持必要 boundary pointers。
- 先規劃邊界與 probe 全部共址、window 最窄且 labels 最密集的 peak state，更新後留下可辨識的 resolved hold。

### Graph Traversal

- Node layout 固定，清楚區分目前擴展、已發現結構與 frontier；edge styling 非焦點時保持安靜。
- Queue/stack 若是核准設計的一部分，需配置 persistent zone 並按最長 frontier 內容計算容量。
- 規劃 node labels、frontier、pointer/highlight 同時出現的 peak state；helper 共址不得遮住 node label。
- 只有 traversal order 是教學重點時才加入 neighbor-order cues。
- 把完整 graph 放在顯示期間 identity 穩定的 `VGroup` wrapper，並在第一次可能觸發 visible audit 的 `play()` 前呼叫 `register_graph_root(wrapper, optional_name)`。不要把一般 card、panel 或 table 註冊成 graph。Graph 完整退場時，已註冊 root 會成為 inactive，不需取消註冊。
- 目前 Scene 中同一已註冊 wrapper 內的 graph/graph 排版通常採 `INFO` best-effort；line crossings 以 segment narrow phase 減少雜訊。常見封閉 node 外形會先排除完整 containment，再把實際 node/node overlap 維持為 blocking `WARNING`；Circle/Circle 使用圓形 narrow phase。圖中文字被上層可見物件遮擋也維持 blocking `WARNING`。不同 graph、graph 對非 graph 與未知 pair 維持嚴格。若 replacement 使用新 wrapper，在它第一次接受 audit 前註冊新 root；舊 root 缺席不會報錯。

## 寫完 Python 後：強制靜態 Audit

完成 `generated_algo_scene.py` 後，必須重新從頭閱讀完整檔案，為每個 Scene 建立物件狀態時間線。對每個穩定 beat 至少回答：

1. 當下有哪些物件仍存在？
2. 每個物件的最終 positioning chain 是什麼？
3. 哪些物件共享 anchor、cell、edge、index 或 zone？
4. 此 Scene 的寬度、高度、文字長度與物件數量 peak state 在哪個 beat？
5. 舊物件是否確實被替換、淡出或清理？
6. 是否有過期物件仍占空間、遮擋內容或分散焦點？
7. 是否存在只能依賴未驗證 magic shift 才可能成立的構圖？
8. 每次 pointer 移動後，目的地的所有 arrows 與 labels 是否仍可共存？
9. 動態文字替換後，最長內容是否仍在 panel 與 safe frame 內？
10. 個別合法的 objects 組合後是否可能越界或碰撞？
11. 每個 card/container 的內部 siblings 是否都在自己的可見 panel/box boundary 內？
12. 重疊文字是否依 z-index 與 drawing order 位於可能遮擋物件上方？
13. Graph roots 是否只註冊真正的 graph wrapper，且沒有 leaf 同時屬於多個 roots？
14. Scene 4 的每個必要 derivation phase 是否各有 resolved checkpoint，並維持 Scene 3 的工作單位與視覺語意？

若高風險定位無法由最終 bounding box、zone 容量及生命週期證明安全，先修改 layout，再重新閱讀受影響 Scene；不能把已知疑點留給後續流程首次發現。泛用 visible warning 是 blocking，不得由 writer 忽略或降級；精確例外只在使用者需求或已核准設計明確要求時依 `layout-audit.md` 提出 proposal，且應先嘗試修復 layout。Proposal 必須由 Scene Reviewer 批准，Writer 不得自行套用。

## CODE_PREPARATION 完成條件

只有在下列條件都完成後，`generated_algo_scene.py` 才能先送交獨立 pre-layout Scene Review；review 通過後才送交 Layout Validator。Scene Writer 不自行執行 runner或讀取完整 raw JSON：

- 五個 Scenes 均符合核准結構、獨立建立/清理並可分別渲染。
- 每個 Scene、每個穩定 beat 與所有 peak states 已靜態複查。
- 最長文字、panel 容量、公式與 overlay 已按最終 bounding box 複查。
- 所有 pointer destinations、共享 anchors/indexes 與共址策略已複查。
- 每個 helper 的首次出現、持續、更新、Transform 前後狀態及移除時點已複查。
- 所有 positioning chains 已按群組最終尺寸複查，沒有依賴未驗證的 magic shifts。
- 所有 graph wrappers、best-effort graph infos、best-effort route 外的嚴格 internal/cross-container containment 與文字 drawing order 已按 `layout-audit.md` 的 routing 複查。
- 上游語意、voiceover/overlay coding constraints、visual continuity 與 final cleanup 均保持可追溯。
