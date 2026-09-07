# Layout Audit

在 Stage 4 `LAYOUT VERIFICATION AND TRIAGE` 使用本文件。Audit 會建立真實 Manim mobjects 並把動畫直接推到穩定狀態，但不寫 frame 或 MP4。

## 執行輸入與 Preflight

執行前，確認派遣訊息中的所有 `Required inputs` 均存在且可讀，並確認 `Scene classes and approved order` 依核准順序列出五個互不重複、且存在於目前 `Scene source` 的 Scene class。

Preflight 失敗時，建立 `layout_audit_result.md` 並寫入 `Result: FAIL` 與失敗證據；只有連結果檔都無法建立時才是 `BLOCKED`。

## 適用範圍

- Scene Writer 只使用 project-side adapter/checkpoint contract。
- Scene Writer 不執行 runner、Layout Validator Preflight、必要命令，不直接整理完整 raw JSON，也不建立 `layout_audit_result.md`。
- Layout Validator 使用 execution input/Preflight、必要命令、gate/result。
- Scene Reviewer 在 audit 前批准 graph-root 分類，並在 final audit 前批准或拒絕 Writer 提出的 exception proposals。

## 目錄

- [權威 gate](#權威-gate)
- [元件責任](#元件責任)
- [明確註冊 graph root](#明確註冊-graph-root)
- [階層式 broad-to-narrow 規則](#階層式-broad-to-narrow-規則)
- [Graph 與非 graph routing](#graph-與非-graph-routing)
- [Containment](#containment)
- [文字 drawing order](#文字-drawing-order)
- [必要 checkpoint 與命令](#必要-checkpoint-與命令)
- [精確例外](#精確例外)
- [Derived summary 與 triage](#derived-summary-與-triage)
- [Gate 與完整 evidence](#gate-與完整-evidence)
- [限制](#限制)

## 權威 gate

`visible_layout_audit.py` 是所有可見物件的泛用權威掃描器；`scene_layout_audit.py` 的 scene-specific adapter 只補充具名 fit、spacing 與 checkpoint assertion，不能取代或壓掉泛用 finding。每一筆未解決的 `WARNING` 都是 blocking：

```text
unresolved warning count > 0 => FAIL
```

Validator 必須保留完整 finding，不得省略、截斷、摘要改寫、手動忽略或降級 warning。人類輸出的 `--visible-max-reports` 可以限制列印數量，但 runner 仍以全部 findings 判定 gate，並固定寫出完整 JSON report。

## 元件責任

- `run_layout_audit.py`：載入 Scene、套用 render profile、dry-run 動畫、套用精確例外、寫完整 report 並決定 exit code。
- `visible_layout_audit.py`：階層式掃描所有可見 leaf、frame overflow、碰撞、containment、文字遮擋與有限的 graph line narrow phase。
- `scene_layout_audit.py`：讓 Scene Writer 建立具名 adapter checkpoint，並以 `register_graph_root()` 明確註冊 graph wrapper。
- `summarize_layout_audit.py`：確定性聚合跨 checkpoint 的相同 finding pair，建立 derived summary/triage；不改變 raw findings 或 gate。

每個交付 Scene 都必須同時通過泛用掃描與 adapter。

## 加入 project

把 adapter helper 複製到 `generated_algo_scene.py` 同一層：

```text
<project>/
├── generated_algo_scene.py
└── scene_layout_audit.py
```

一般 Scene adapter：

```python
import os
from scene_layout_audit import LayoutAudit, register_graph_root

LAYOUT_AUDIT_ENABLED = os.getenv("MANIM_LAYOUT_AUDIT", "1").lower() not in {"0", "false", "no"}
LAYOUT_AUDIT_FAIL = os.getenv("MANIM_LAYOUT_AUDIT_FAIL", "0").lower() in {"1", "true", "yes"}

def _audit_layout(self, context, nodes, labels, panels, header=None, extra_items=None):
    audit = LayoutAudit(context=context, enabled=LAYOUT_AUDIT_ENABLED)
    header = header or []
    extra_items = extra_items or []
    all_items = nodes + labels + panels + header + extra_items
    for name, mob in all_items:
        audit.check_inside_frame(name, mob)
    audit.check_no_overlaps_between(header + extra_items, nodes + labels + panels, min_gap=0.05)
    audit.report(raise_on_issue=LAYOUT_AUDIT_FAIL)
```

只有真的應該分開的具名物件才放進 adapter 的 `check_no_overlap`。Adapter finding 仍然 blocking，因此不得用 adapter 把同一 graph root 內的排版重新升級成 blocking 檢查；圖內關係交給 visible audit 以 best-effort `INFO` 記錄。

## 明確註冊 graph root

不要從每個 `VGroup` 推測 graph；panel、table、header 與 card 也常用 `VGroup`。建立 graph 後、任何會觸發 visible audit 的 `play()` 前，註冊其穩定 structural wrapper：

```python
graph = VGroup(edges, nodes, labels)
register_graph_root(graph, "main traversal graph")  # name 只供 log 閱讀
self.play(FadeIn(graph))
```

Membership 完全由目前 Scene 中的 wrapper ancestry 與 object identity 推導，不使用額外 graph ID。若同一 leaf 同時屬於多個已註冊 graph roots，audit 以不可豁免 `ERROR` 失敗。已註冊 root 在某個 checkpoint 不在 Scene 時視為 inactive，不產生 finding；之後重新出現時自動恢復 graph 規則。若 root 消失但部分 children 獨立留在 Scene，這些 children 不再具有該 root membership，會回到嚴格規則。Replacement 可註冊新 wrapper；不需要取消舊 root。

## 階層式 broad-to-narrow 規則

每個 checkpoint 只計算並快取一次 scanner 所需的 object/container bounds。Traversal 從 top-level structural containers、已註冊 roots 與未被 container 擁有的可見物件開始：

1. Container bounding box 只作 broad phase，不直接形成 collision finding。
2. 兩個 container AABB 分離時停止；相交或互相包含時，只遞迴比較相交的 child branches。
3. Container 對 leaf 只下降可能相交的 branch。
4. 每個 container 也必須獨立執行 internal sibling/descendant audit，即使它與任何外部 container 都沒有碰撞。
5. 到達可見 leaf 才套用 pair rule；順序依 Scene/family 順序固定，確保 findings 可重現。

Internal path 必須捕捉 card 內的 sibling 關係。例如 heading 與 panel 同屬一個 card，而 heading 的 bounds 延伸到 panel 外，即使 card 沒撞到外部物件，仍要產生 `WARNING`。

`VGroup` 自身不是可見內容邊界；panel、box、background、node shape 等可見幾何才是 containment boundary。

## Graph 與非 graph routing

所有 pair 預設使用原本嚴格規則。兩個 leaves 明確且唯一地屬於同一個 registered graph root 時，圖內排版通常採 best-effort；唯一提升為 blocking 的圖內特例是常見封閉 node 外形之間的實際 overlap。

- 同 root 的 line/node、line/text 與一般 containment：幾何 relation 保留為 `INFO`；但若文字實際畫在遮擋物下方，會另外產生 blocking `text-occlusion WARNING`。
- 同 root line-like pair：AABB 相交後執行 segment narrow phase，以減少無意義 finding。
- 同 root 的 `Circle`、`Ellipse`、`Polygon`、`Rectangle`、`RoundedRectangle`、`Square`（含其 subclasses）先判斷完整 containment；同一直接 structural parent 下的包含是正常 owner/content 關係，不產生 finding，不同子組或 container 間的包含維持 `WARNING`。其餘 overlap 產生 `same-graph-node-overlap WARNING`。
- Circle/Circle 在排除 containment 後，以圓心距離與半徑 narrow phase 判斷；實際穿透才產生 warning，相切或只有 AABB 相交不產生 finding。其他 node 外形維持常數時間 AABB 判斷，不加入 polygon clipping 或 pixel mask。
- 不同 graph roots：嚴格規則。
- graph 對 non-graph：嚴格規則。
- non-graph 對 non-graph：嚴格規則。
- 未分類或 membership 不明：嚴格規則。

Best-effort 不等於刪除：writer 應在不破壞教學設計且修改風險低時改善明顯圖內排版，但 validator 不得自行把 INFO 升為 warning。只有 Scene Reviewer 已確認的真正 graph wrapper 可註冊；不得把 panel、table、card、matrix、整個 Scene 或混入無關 UI 的 umbrella group 包成 graph 來規避嚴格 gate。

每個 audit checkpoint 的可見 ownership 結構必須是一棵樹：leaf 或 subgroup 可以有多層巢狀 ancestors，但只能有一個直接 structural owner。同一物件若可由多個平行 Scene-visible branches 到達，產生不可豁免的 `ambiguous-structural-parent ERROR`。需要邏輯分類時使用 Python list/dict/set；暫時操作用的 `VGroup` 不得同時加入 Scene 或註冊成 graph root。`ambiguous-graph-membership ERROR` 仍獨立檢查巢狀或重疊 graph roots。

同 graph line-like narrow phase 只處理 `Line`、`DashedLine`、`Arrow`、`DoubleArrow` 可提供的直線 start/end：

- 共用端點：正常圖結構，不產生 finding。
- 橫向交叉：正常圖結構，不產生 finding。
- AABB 重疊但線段實際不相交：不產生 finding。
- 非零長度共線重疊：best-effort `INFO`。
- T 字或其他不支援的線接觸：best-effort `INFO`。
- 無法取得支援的直線幾何、曲線或 path：退回 AABB，但同 root 結果仍是 best-effort `INFO`。

不要求 edge incidence metadata，也不推測 topology。Graph 對 root 外的不相關 node/text/object 仍是嚴格 pair；同 root arrow/node/text 的一般幾何 finding 保留為 best-effort INFO，但文字遮擋另為 WARNING。除 Circle/Circle 的常數時間精確判斷外，不加入 polygon clipping、pixel mask、spatial library 或複雜 ownership engine。

## Containment

- 同一個非 graph structural owner 內，內容或 node label 完全位於自己的可見 panel/node boundary 內，且內容依 drawing order 位於 boundary 上方：正常 containment，不產生 finding。
- 同一直接 structural parent 下的完整 containment 不產生 finding；同 graph 但位於不同子組或 container 的 node shapes 仍維持 `WARNING`。
- 獨立 peer containers、不同 containers 的 objects，或其他不具 ownership ancestry 的嚴格 containment：`WARNING`。
- 合法 ancestor/descendant 或明確 nested owner 不視為獨立 peer。
- 不相關 opaque object 完全蓋住另一物件仍是 `WARNING`，不能因為「完全包含」而降為 INFO。
- Frame overflow 對任何物件都是不可豁免 `ERROR`。

## 文字 drawing order

不要求所有 `Text` 都有 Scene 全域最高 z-index。只有 precise/fallback geometry 與文字重疊的可見物件才檢查遮擋：

1. 先比較 `z_index`。
2. z-index 相同時，使用穩定的 Scene/family drawing order。
3. 若可能遮擋的 opaque/stroked object 會畫在文字上方，無論是否屬於同一 graph root，都產生 `text-occlusion WARNING`。

文字畫在自己的 background panel 上方可通過；透明且不描邊的物件不造成 false warning。Graph 內文字遮擋同樣會阻塞，不再降為 INFO。

## 必要 checkpoint 與命令

每幕至少呼叫 initial、至少一個 `beat:<id>` 與 final adapter checkpoint。重要文字、pointer、panel 或 object 組合每次改變後，都要在穩定狀態呼叫 adapter。

Scene 4 必須在每個必要 derivation phase 的 resolved state 建立 `beat:<id>` checkpoint，並把當下可見的公式、case label、多變數圖或 auxiliary-space diagram 納入具名 adapter；不能只檢查公式最後完整出現的畫面。

## 必要命令

對派遣訊息提供的五個 Scene class 依核准順序分別執行：

```bash
<render-profile-python> <absolute-runner-path> \
  <absolute-project-root>/generated_algo_scene.py <SceneClass> \
  --render-profile <absolute-project-root>/render_profile.json \
  --audit-visible \
  --require-adapter \
  --visible-report-level warning
```

Runner 預設寫出 `<project>/layout_audit_report.<SceneClass>.json`。若需要明確路徑，使用 `--visible-report <absolute-json-path>`。五幕依派遣訊息中的核准順序各執行一次。

Runner 會：

1. 驗證目前 Python、Manim 版本、字型與 `render_profile.json` 一致。
2. 套用 profile 記錄的 frame geometry、解析度、frame rate 與 renderer；未經使用者覆寫時即為 1920×1080、60 fps、Cairo。
3. 執行 Scene adapter 與泛用可見物件掃描。
4. 在 stdout 記錄 profile 設定與 adapter checkpoint 名稱。

## 精確例外

優先修復 layout；例外只用於使用者需求或已核准設計明確要求的罕見 warning。每個 exception file 只屬於一個 Scene；該幕選用 `--visible-exceptions <absolute-json-path>`，格式如下：

```json
{
  "exceptions": [
    {
      "scene_class": "TraversalScene",
      "checkpoint": "TraversalScene:after-play-0007",
      "objects": [
        "VGroup[0].Rectangle[0]",
        "VGroup[0].Text[1]"
      ],
      "relation": "overlap",
      "explanation": "The approved callout intentionally touches the highlighted cell.",
      "supporting_reference": "animation_design.md#scene-3-callout",
      "source_sha256": "<current generated_algo_scene.py SHA-256>"
    }
  ]
}
```

每筆例外必須精確綁定目前受檢 scene class、checkpoint、兩個完整 object names、relation、非空 explanation、支援的 user requirement/approved design reference 與目前 source SHA-256。禁止在同一檔混入其他 Scene，並禁止 wildcard、空欄位、模糊 pair 或 free-form「看起來是故意的」。Scene、source、pair、checkpoint 或 relation 改變後，例外立即失效；stale、duplicate、unmatched、scene-mismatched 或 unsupported record 會令 gate 失敗。

例外是 disposition，不是刪除：完整 JSON 中保留原 finding，標示 `accepted: true` 與 exception index。Writer 只能提出 proposal；Scene Reviewer 必須逐筆寫 `APPROVED`，Validator 才可套用。Text occlusion 只有 reference 明確指向 `confirmed_requirements.md` 或 `animation_design.md` 時可接受。以下 finding 不可豁免：

- frame overflow
- tool failure 或 exception-file error
- missing audit coverage/checkpoint
- ambiguous graph-root membership
- unclassified finding

## `layout_audit_result.md`

結果檔必須記錄：

- `Result: PASS` 或 `Result: FAIL`
- Render profile 及執行環境欄位
- 五個 Scene 的核准順序
- 每個實際 command、stdout、stderr 與 exit code
- 每個 Scene 的 adapter checkpoint summary
- 所有 blocking findings

只有 Preflight 通過、五個核准 Scene 全部受檢、每個 Scene 的 initial／beat／final checkpoint 完整，且五個必要 command 全部 exit `0` 時，才能寫入 `Result: PASS`。其餘情況寫入 `Result: FAIL`。

## Derived summary 與 triage

Validator 對五個完整 reports 執行 `summarize_layout_audit.py`，產生 `layout_audit_summary.json` 與 `layout_audit_triage.md`。Grouping key 使用 Scene report、severity、relation、完整 object pair、accepted 與 exception identity；保留 occurrence count、所有 checkpoints、message variant count、代表訊息及 raw report SHA-256。

```bash
<render-profile-python> <absolute-summarizer-path> \
  <report-1.json> <report-2.json> <report-3.json> <report-4.json> <report-5.json> \
  --json-output <project-root>/layout_audit_summary.json \
  --markdown-output <project-root>/layout_audit_triage.md
```

Triage 可限制展示的 warning/INFO group 數量以節省 context，但必須明示 omitted count 並連回 summary/raw report。Scene Writer 只接收 triage 與 Coordinator 指定 groups。Raw JSON totals、findings 與 runner exit code仍是唯一 gate，不能用 grouped count 判定 PASS。

## Adapter 可用檢查

- `check_inside_frame(name, mob, margin=0.1)`：物件是否留在 safe frame。
- `check_fits(inner_name, inner, outer_name, outer, padding=0.15)`：文字或內容是否放得進 panel。
- `check_no_overlap(a_name, a, b_name, b, min_gap=0.05)`：兩個具名物件是否重疊或距離不足。
- `check_no_internal_overlaps(items, min_gap=0.05)`：同一組 labels 或 repeated items 是否互撞。
- `check_no_overlaps_between(group_a, group_b, min_gap=0.05)`：兩組具名物件是否互撞。

## Gate 與完整 evidence

以下任一情況 exit `1`：

- Scene/dry-run/tool/profile 失敗。
- 任何 visible `ERROR`。
- unresolved warning count 大於零。
- Adapter finding 或缺少 initial/beat/final checkpoint。
- 例外檔無效、過期、未精確 match 或嘗試豁免不支援的 finding。

`layout_audit_result.md` 必須保留每幕完整 command、stdout、stderr、exit code、adapter checkpoints、完整 JSON report path/hash，以及：

- total findings
- infos（包含同 graph best-effort findings）
- accepted warnings
- unresolved warnings
- errors
- exception file path/hash（未使用時明記 none）
- final gate result

不得用人工整理的縮短摘要取代 JSON findings。Code、runner 或 render profile 改變後，既有 layout evidence 失效；source 改變也會使所有例外失效。

## 限制

- Dry-run 只檢查每次 `play()` 完成後與 final 的穩定狀態，不檢查 animation interpolation 中間影格。
- Line narrow phase 只支援直線 start/end；曲線與其他 path 退回 AABB。同 root 的 fallback 仍是 best-effort `INFO`，可能保留非阻塞 false positive；跨 root 或 graph 外 fallback 維持嚴格，可能保留 blocking false positive。
- Circle narrow phase 只適用 bounds 可確認為等寬等高的 `Circle`；非等比例縮放的 Circle 退回嚴格 AABB，可能保留 blocking false positive。Graph 內裝飾性 Circle 應避免被建模成獨立 node boundary，並由 Reviewer 檢查。
- Text 使用整體/fallback bounds，不做 glyph-level geometry。
- 部分透明物件只依目前 opacity API 判斷，複雜 blending 可能仍有誤判。
- Container bounds 只是 broad phase；scanner 不實作完整 graph topology 或一般計算幾何。
