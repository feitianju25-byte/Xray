# 规则圆形焊点阵列 MVP

本目录用于从现有 PCB X 光数据中抽样多行、规则、近圆形焊点阵列。程序只在清单中引用原图，不复制 JPG/JPEG/ZIP，也不要求逐个焊点画像素掩膜。

## 当前阶段

第一阶段生成：

1. 图片盘点清单和来源统计；
2. 固定种子的候选样本清单；
3. 最多 40 张候选联系表；
4. 待人工填写的 `keep/reject/uncertain` 复核文件。

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
python solder_joint_mvp/run.py sample --manifest "solder_joint_mvp/manifests/datav1_inventory.json" --output "solder_joint_mvp/manifests/regular_array_candidates.json" --limit 40 --seed 20260914 --include "未标注" --reference "DataV1/数据集/X光图片20260603/未标注/焊点桥连/焊点桥连 (1).jpg"
python solder_joint_mvp/run.py contact-sheet --manifest "solder_joint_mvp/manifests/regular_array_candidates.json" --output "solder_joint_mvp/outputs/contact_sheet.png" --review-output "solder_joint_mvp/reviews/candidate_review.json" --review-csv "solder_joint_mvp/reviews/candidate_review.csv"
```

联系表中每张图都带有稳定样本 ID。首轮可直接用 Excel 打开复核 CSV，将 `decision` 从 `uncertain` 改为 `keep` 或 `reject`；本轮至少确认 10 张 `keep`。JSON 版本用于后续几何修正，只填写阵列框、行列数、四角或少量中心点即可。

## 数据约定

- `manifests/`：本机路径、扫描结果和抽样结果，不提交 Git。
- `reviews/`：人工复核工作文件，默认不提交 Git。
- `outputs/`：可再生联系表、ROI 和报告，默认不提交 Git。
- `schemas/`：清单与标注的数据契约，可提交 Git。

字段定义见 [schemas/README.md](schemas/README.md)。
