# 目标芯片元件族筛选实施记录

日期：2026-09-15  
对应 OpenSpec 变更：`sample-regular-solder-arrays`

## 本轮结论

筛选目标已从“所有黑色圆形阵列”收窄为 `frontal-chip-internal-dot-grid-v1`：以
`DataV1/数据集/X光图片20260804/未标注/焊点桥连/焊点桥连 (2).jpg`
为锚点，要求芯片封装正视、本体边界可辨，且封装内部的圆点形成二维规则阵列。
连接器、插针、BGA 背面、其他模块中的相似圆点不算同族。

OpenSpec 当前完成 11/27 项；已完成自动候选生成和 Codex 初审，流程暂停在需要用户确认的任务 3.3。

## 筛选实现

- 扫描 `DataV1` 的 2,160 张“未标注”图片；
- 对每张图计算方向兼容的全图、中心、边缘、周期性和封装比例特征；
- 计算 256 位感知摘要，将近重复图片归为 1,881 组；
- 每组最多保留 1 张，共输出排序最高的 120 张；
- 生成 3 张联系表，每张 40 个候选；
- 每个缩略图显示全局排名、稳定样本 ID、同族分数、重复组和来源；
- 初审建议可由 `examples/frontal_chip_suggestions_2026-09-15.json` 重放到复核 JSON/CSV。

同族分数只用于排序，不直接决定 `keep`。本轮高分区仍包含大量连接器、其他芯片封装和整板缩略图，因此人工族别判断仍是必要环节。

## Codex 初审统计

| 建议标签 | 数量 | 含义 |
|---|---:|---|
| `keep` | 10 | 建议属于目标芯片正视元件族 |
| `other_component` | 50 | 图像可用，但圆阵列来自其他元件 |
| `reject` | 57 | 视角、裁切、清晰度或结构不适合本实验 |
| `uncertain` | 3 | 具有内部点阵，但元件结构与锚点差异较大 |

建议 `keep` 的联系表编号：`001, 003, 020, 031, 041, 042, 049, 065, 100, 105`。

其中 `020` 主体偏暗但能看到 2×3 内部圆点，建议用户在确认 keep 时重点查看。

## 需要用户确认的边界项

| 编号 | 原图 | 初审疑点 |
|---:|---|---|
| 044 | `数据集2/X光图片20260907/未标注/X光图片20260907_000079.jpg` | 矩形封装内部有规则点阵，但同时存在明显环形芯片结构 |
| 062 | `数据集/X光图片20260603/未标注/多余物/多余物 (8).jpg` | 中央点阵清晰，但双圆形芯片结构与锚点差异较大 |
| 088 | `数据集/X光图片20260603/未标注/多余物/多余物 (6).jpg` | 与 062 类似，可能是同一类非目标模块 |

用户只需要确认：上述 10 张建议 `keep` 是否都属于目标元件族，以及 044/062/088 应改为 `keep` 还是 `other_component`。目前不需要逐点或逐像素标注。

## 输出位置

- 候选清单：`solder_joint_mvp/manifests/frontal_chip_candidates.json`
- 联系表：`solder_joint_mvp/outputs/frontal_chip_candidates/contact_sheet_001_040.png` 等 3 张
- JSON 复核表：`solder_joint_mvp/reviews/frontal_chip_review.json`
- CSV 复核表：`solder_joint_mvp/reviews/frontal_chip_review.csv`
- 可重放建议：`solder_joint_mvp/examples/frontal_chip_suggestions_2026-09-15.json`

图片、候选清单、复核表和联系表均保留在本机并受忽略规则保护；Git 只同步代码、规则、Schema、测试、建议映射和本实施记录，不同步 JPG/JPEG/ZIP。

## 验证结果

```text
python -m pytest solder_joint_mvp/tests -q
11 passed
```

- 120 条候选对应 120 个唯一稳定 ID；
- 120 条复核建议无遗漏、无重复；
- 120 个原图路径全部存在；
- 复核 JSON 通过 `review.schema.json` 校验；
- 3 张联系表均成功生成；
- OpenSpec 严格校验在提交前再次执行。

