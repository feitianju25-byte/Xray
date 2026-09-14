# 规则圆形焊点阵列 MVP 实施记录

日期：2026-09-14  
对应 OpenSpec 变更：`sample-regular-solder-arrays`

## 本轮完成内容

已完成 OpenSpec 任务 1.1–3.1，共 7/23 项：

- 建立独立的 `solder_joint_mvp/` Python 工作区；
- 定义图片清单、人工复核、阵列网格和 ROI 清单四类 JSON Schema；
- 实现稳定样本 ID、图片头只读盘点、固定种子分层抽样；
- 实现以已确认样例为参考的缩略图相似度排序；
- 生成带样本 ID 和来源的候选联系表；
- 生成 JSON 与 Excel 友好的 CSV 人工复核模板；
- 添加结构、Schema、异常图片、可复现抽样和联系表测试。

未复制任何 JPG/JPEG/ZIP。`manifests/`、`reviews/` 和 `outputs/` 是本机工作数据并被 Git 忽略。

## 数据盘点结果

扫描范围：`DataV1/`

| 项目 | 结果 |
|---|---:|
| 图片总数 | 4,695 |
| 成功读取图片头 | 4,695 |
| 读取异常 | 0 |
| 来源目录 | 39 |

随机抽查 3 条记录，原始路径均存在，清单尺寸与实际图片尺寸一致。常见尺寸包括 1024×1024、1004×620、1024×1097 和 3200×2121。

## 首批候选结果

- 筛选范围：相对路径包含“未标注”的图片；
- 可选池：2,160 张；
- 固定随机种子：`20260914`；
- 参考图：`DataV1/数据集/X光图片20260603/未标注/焊点桥连/焊点桥连 (1).jpg`；
- 输出候选：40 张，40 个唯一 ID；
- 来源覆盖：18 个来源组；
- 参考图位置：联系表第 7 张。

候选集中同时保留规则阵列正例和芯片、侧视、空白等负例，以便人工复核明确首轮边界。

## 自动验证

```text
python -m pytest solder_joint_mvp/tests -q
7 passed
```

额外检查：

- 复核 JSON 符合 `review.schema.json`；
- 联系表是可读取 PNG；
- 40 个原始图片路径全部存在；
- Git 忽略规则覆盖本机清单、复核文件、联系表和 ROI 图片；
- `.gitkeep`、代码、配置、Schema 和文档仍可由 Git 管理。

## 需要人工完成的下一步

1. 打开 `solder_joint_mvp/outputs/contact_sheet.png` 查看 40 张候选；
2. 用 Excel 打开 `solder_joint_mvp/reviews/candidate_review.csv`；
3. 将每行 `decision` 填为 `keep`、`reject` 或 `uncertain`；
4. 至少确认 10 张 `keep`，保存后通知 Codex 继续。

这一阶段只判断“是否属于多行规则近圆形焊点阵列”，无需逐个焊点画轮廓。几何修正会在冻结验证集后进行。

## 可复现命令

完整命令见项目 [README](../README.md)。核心入口为：

```powershell
python solder_joint_mvp/run.py inventory ...
python solder_joint_mvp/run.py sample ...
python solder_joint_mvp/run.py contact-sheet ...
python -m pytest solder_joint_mvp/tests -q
```

