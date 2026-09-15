# 规则圆形焊点阵列 MVP

本目录用于从现有 PCB X 光数据中抽样多行、规则、近圆形焊点阵列。程序只在清单中引用原图，不复制 JPG/JPEG/ZIP，也不要求逐个焊点画像素掩膜。

## 当前阶段

第一阶段生成：

1. 图片盘点清单和来源统计；
2. 感知近重复组与目标元件族评分；
3. 最多 120 张、每批 40 张的候选联系表；
4. 区分 `keep/other_component/reject/uncertain` 的复核文件。

## 环境

- Python 3.11+
- Pillow
- NumPy
- PyYAML
- jsonschema（开发与格式校验）

在仓库根目录运行测试：

```powershell
python -m pytest solder_joint_mvp/tests -q
```

## 生成首批候选

```powershell
python solder_joint_mvp/run.py inventory --root "datav1=DataV1" --output "solder_joint_mvp/manifests/datav1_inventory.json"
python solder_joint_mvp/run.py screen-family --manifest "solder_joint_mvp/manifests/datav1_inventory.json" --output "solder_joint_mvp/manifests/frontal_chip_candidates.json" --limit 120 --seed 20260915 --include "未标注" --reference "DataV1/数据集/X光图片20260804/未标注/焊点桥连/焊点桥连 (2).jpg"
python solder_joint_mvp/run.py contact-sheets --manifest "solder_joint_mvp/manifests/frontal_chip_candidates.json" --output-dir "solder_joint_mvp/outputs/frontal_chip_candidates" --review-output "solder_joint_mvp/reviews/frontal_chip_review.json" --review-csv "solder_joint_mvp/reviews/frontal_chip_review.csv" --batch-size 40
python solder_joint_mvp/run.py apply-suggestions --manifest "solder_joint_mvp/manifests/frontal_chip_candidates.json" --suggestions "solder_joint_mvp/examples/frontal_chip_suggestions_2026-09-15.json" --review-output "solder_joint_mvp/reviews/frontal_chip_review.json" --review-csv "solder_joint_mvp/reviews/frontal_chip_review.csv"
python solder_joint_mvp/run.py apply-confirmations --manifest "solder_joint_mvp/manifests/frontal_chip_candidates.json" --review "solder_joint_mvp/reviews/frontal_chip_review.json" --confirmations "solder_joint_mvp/examples/frontal_chip_user_confirmations_2026-09-15.json" --output "solder_joint_mvp/reviews/frontal_chip_review.json" --review-csv "solder_joint_mvp/reviews/frontal_chip_review.csv"
python solder_joint_mvp/run.py import-review-csv --review "solder_joint_mvp/reviews/frontal_chip_review.json" --csv "solder_joint_mvp/reviews/frontal_chip_review.csv" --output "solder_joint_mvp/reviews/frontal_chip_review.json"
python solder_joint_mvp/run.py freeze-split --review "solder_joint_mvp/reviews/frontal_chip_review.json" --output "solder_joint_mvp/manifests/frontal_chip_frozen_split.json" --validation-count 10 --seed 20260915
python solder_joint_mvp/run.py prepare-geometry-review --split "solder_joint_mvp/manifests/frontal_chip_frozen_split.json" --output-dir "solder_joint_mvp/reviews/validation_geometry_2026-09-15"
python solder_joint_mvp/run.py import-geometry-review --review "solder_joint_mvp/reviews/frontal_chip_review.json" --split "solder_joint_mvp/manifests/frontal_chip_frozen_split.json" --csv "solder_joint_mvp/reviews/validation_geometry_2026-09-15/geometry_review.csv" --output "solder_joint_mvp/reviews/frontal_chip_review.json"
python solder_joint_mvp/run.py detect-region --image "DataV1/数据集/X光图片20260804/未标注/焊点桥连/焊点桥连 (2).jpg" --bbox "300,40,765,500" --output-json "solder_joint_mvp/outputs/anchor_001_analysis.json" --overlay "solder_joint_mvp/outputs/anchor_001_overlay.png"
python solder_joint_mvp/run.py export-labelme --analysis "solder_joint_mvp/outputs/anchor_001_analysis.json" --output "solder_joint_mvp/outputs/anchor_001_labelme.json"
```

联系表中每张图都带有稳定样本 ID、同族分数和近重复组。Codex 先填写 `suggested_decision`；用户可用 Excel 打开复核 CSV，将最终 `decision` 改为 `keep`、`other_component`、`reject` 或 `uncertain`。本轮至少确认 10 张 `keep`。JSON 版本用于后续几何修正，只填写芯片框、行列数、四角或少量中心点即可。

Excel 可能把 CSV 保存为 GBK/GB18030；`import-review-csv` 会安全识别 UTF-8、GB18030 和 UTF-16，并严格检查样本 ID，避免错行覆盖。验证集按近重复组冻结，`prepare-geometry-review` 会生成 10 张验证图的联系表、CSV 和只引用原图路径的 LabelMe JSON，不复制原始图片。

## 数据约定

- `manifests/`：本机路径、扫描结果和抽样结果，不提交 Git。
- `reviews/`：人工复核工作文件，默认不提交 Git。
- `outputs/`：可再生联系表、ROI 和报告，默认不提交 Git。
- `schemas/`：清单与标注的数据契约，可提交 Git。

字段定义见 [schemas/README.md](schemas/README.md)。
