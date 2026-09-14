# Bridge 与透锡不足 ROI 训练结果记录

更新时间：2026-09-03

## 1. 项目背景

本次训练沿用 void ROI 基线流程：先根据 LabelMe 标注框，以缺陷框中心裁剪多尺度正方形 ROI，再统一缩放到 224×224，使用 YOLO11n-cls 做“目标缺陷 vs normal”二分类。

两个缺陷分别训练独立模型：

- `bridge`：焊点桥连
- `insufficient_through_solder`：透锡不足

数据按源图划分为 train/val/test，同一张原图生成的多个 patch 不会跨集合出现。

## 2. 数据核验与数据集规模

原始标注核验结果：

| 类别 | 图片数 | 有效标注框数 | 备注 |
|---|---:|---:|---|
| bridge | 34 | 47 | 34 张图片均有 JSON |
| insufficient_through_solder | 104 | 255 | 109 张图片中有 5 张没有 JSON，已排除 |

ROI patch 统计：

| 数据集 | train | val | test | 合计 |
|---|---:|---:|---:|---:|
| bridge | 1,636（390/1,246） | 536（180/356） | 313（135/178） | 2,485 |
| insufficient_through_solder | 3,645（2,505/1,140） | 1,181（855/326） | 629（465/164） | 5,455 |

括号内为“正类/normal”数量。normal 样本来自合格图及其他缺陷图的随机局部区域；未配套 JSON 的同类图片没有作为 normal 使用。

## 3. 训练配置

- 模型：`YOLO11n-cls`（`yolo11n-cls.yaml`）
- 输入尺寸：`224×224`
- batch：`32`
- 最大 epochs：`80`
- patience：`20`
- seed：`42`
- workers：`2`
- device：`0`（NVIDIA GeForce RTX 2060，CUDA）
- Ultralytics：`8.4.138`
- PyTorch：`2.5.1+cu121`

## 4. 训练与测试结果

| 类别 | 实际训练轮数 | 最佳轮次 | 最佳验证 top-1 | 测试集准确率 |
|---|---:|---:|---:|---:|
| bridge | 64 | 44 | 0.8862 | 0.8435（264/313） |
| insufficient_through_solder | 49 | 29 | 0.9492 | 0.8537（537/629） |

### 4.1 测试集混淆统计

`bridge`：

- bridge → bridge：95
- bridge → normal：40
- normal → bridge：9
- normal → normal：169

`insufficient_through_solder`：

- insufficient_through_solder → insufficient_through_solder：398
- insufficient_through_solder → normal：67
- normal → insufficient_through_solder：25
- normal → normal：139

## 5. 输出文件

### Bridge

- 数据集：`E:\Xray\Xray\pcb_xray_annotation_workspace\bridge_roi_dataset`
- 最佳模型：`E:\Xray\Xray\pcb_xray_annotation_workspace\bridge_roi_dataset\runs\bridge_roi_cls_baseline\weights\best.pt`
- 训练曲线与日志：`...\runs\bridge_roi_cls_baseline\results.csv`、`results.png`
- 测试归类：`E:\Xray\Xray\pcb_xray_annotation_workspace\bridge_roi_dataset\test_predictions_categorized`

### 透锡不足

- 数据集：`E:\Xray\Xray\pcb_xray_annotation_workspace\insufficient_through_solder_roi_dataset`
- 最佳模型：`E:\Xray\Xray\pcb_xray_annotation_workspace\insufficient_through_solder_roi_dataset\runs\insufficient_through_solder_roi_cls_baseline\weights\best.pt`
- 训练曲线与日志：`...\runs\insufficient_through_solder_roi_cls_baseline\results.csv`、`results.png`
- 测试归类：`E:\Xray\Xray\pcb_xray_annotation_workspace\insufficient_through_solder_roi_dataset\test_predictions_categorized`

每个 `test_predictions_categorized` 目录包含：

- `correct/`：预测正确的图片
- `wrong/`：预测错误的图片
- `predictions.csv`：真实标签、预测标签、置信度和输出图片路径

## 6. 复现命令

```powershell
E:\Anaconda\envs\pt_env\python.exe prepare_defect_roi_dataset.py --label bridge
E:\Anaconda\envs\pt_env\python.exe train_defect_roi_cls.py --label bridge --device 0
E:\Anaconda\envs\pt_env\python.exe categorize_defect_roi_predictions.py --label bridge --split test

E:\Anaconda\envs\pt_env\python.exe prepare_defect_roi_dataset.py --label insufficient_through_solder
E:\Anaconda\envs\pt_env\python.exe train_defect_roi_cls.py --label insufficient_through_solder --device 0
E:\Anaconda\envs\pt_env\python.exe categorize_defect_roi_predictions.py --label insufficient_through_solder --split test
```

## 7. 结果解读与后续建议

这两组结果证明 ROI 分类流程可以学习到两类缺陷的明显特征，但测试准确率低于最佳验证准确率，说明仍存在一定泛化差距。

优先改进方向：

1. 重点复核 `bridge/wrong` 中的 40 个漏检样本，确认桥连框是否包含足够的相邻焊点上下文。
2. 复核透锡不足的 67 个漏检样本，统一插针、焊盘和透锡柱的框选范围。
3. 增加与缺陷形态相近的人工挑选 normal ROI，减少随机负样本带来的分布偏差。
4. 后续评估应同时报告每类召回率和精确率，不能只看总体准确率。

当前模型属于 ROI 二分类基线，不等同于整张 X-ray 图像上的最终缺陷检测模型。
