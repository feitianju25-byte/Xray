# PCB X-ray 项目结构

本文档定义当前仓库各目录的职责。为避免破坏训练脚本中的既有路径，当前整理以明确边界为主，不批量移动数据集和训练产物。

## 核心程序

| 路径 | 职责 |
| --- | --- |
| `run_app.py` | Windows 桌面识别程序入口 |
| `screen_recognition_app/` | 截屏、识别流水线、透明标注层、设置和历史记录 |
| `screen_recognition_app_config.json` | 当前运行后端、模型、阈值和历史记录设置 |

## 训练与数据准备脚本

| 文件 | 职责 |
| --- | --- |
| `prepare_void_yolo_dataset.py` | 将空洞 LabelMe 标注转换为 YOLO 检测数据集 |
| `prepare_void_roi_dataset.py` | 生成空洞/正常 ROI 二分类数据集 |
| `prepare_defect_roi_dataset.py` | 生成桥连或透锡不足 ROI 二分类数据集 |
| `train_void_yolo.py` | 训练空洞 YOLO 检测模型 |
| `train_void_roi_cls.py` | 训练空洞 ROI 分类模型 |
| `train_defect_roi_cls.py` | 训练桥连或透锡不足 ROI 分类模型 |
| `annotate_void_roi_val_predictions.py` | 绘制空洞 ROI 预测结果 |
| `categorize_defect_roi_predictions.py` | 按正确/错误类别整理 ROI 预测结果 |

## 数据与实验

| 路径 | 职责 | Git 策略 |
| --- | --- | --- |
| `DataV1/数据集/` | 三批五类缺陷原图、椭圆标注以及 Qwen LoRA 对比实验 | JSON、脚本和结果入库；JPG 忽略 |
| `DataV1/数据集2/` | 1024×1024 切片及矩形框标签 | JSON、CSV 入库；JPG 忽略 |
| `pcb_xray_annotation_workspace/images/` | 去重后的三类 LabelMe 标注源图 | JSON 入库；JPG 忽略 |
| `pcb_xray_annotation_workspace/*_roi_dataset/` | ROI 分类数据集、清单、训练曲线和权重 | 文本入库；PNG/PT 使用 LFS；JPG/ZIP 忽略 |
| `pcb_xray_annotation_workspace/yolo_void_dataset/` | 空洞 YOLO 检测数据集和训练结果 | 标签/配置入库；PNG/PT 使用 LFS；JPG 忽略 |
| `reference_good/`、`reference_defect/` | 合格与缺陷参考图片 | JPG 忽略 |
| `test_images/`、`annotated_results/` | 早期测试输入和绘制结果 | JPG 忽略 |
| `runs/` | 桌面识别历史 | JSON/JSONL 入库；PNG 使用 LFS；JPG 忽略 |
| `weights/` | 额外模型权重 | PT 使用 LFS |

## 文档与规格

| 路径 | 职责 |
| --- | --- |
| `README.md` | 桌面识别程序运行说明 |
| `PCB_Xray_*.md`、`ROI缺陷训练结果记录.md` | 数据、训练路线与历史实验记录 |
| `docs/` | 项目级结构和维护说明 |

## 当前数据格式

项目内存在三种 JSON 标注，不应直接混用：

1. `pcb_xray_annotation_workspace/images/` 使用 LabelMe 矩形框。
2. `DataV1/数据集/` 使用自定义缺陷类别和旋转椭圆。
3. `DataV1/数据集2/` 使用切片级 `image_label` 和对象 `bbox`。

## 版本管理边界

- 所有 JPG/JPEG 和 ZIP 均由 `.gitignore` 排除，保留在本地或独立数据存储中。
- Python 字节码、训练缓存和 IDE 状态不入库。
- PT、PNG 及其他大型二进制文件通过 Git LFS 管理。
- 代码、Markdown、JSON、JSONL、CSV、YAML 和配置文件由普通 Git 管理。
- 克隆仓库后需要从数据存储恢复 JPG，仓库中的清单和 JSON 可用于核对文件完整性。
