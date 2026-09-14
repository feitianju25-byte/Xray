# PCB Xray 空洞 ROI 训练说明

## 当前目标

当前先把问题收窄为“ROI 小图内是否存在空洞 void”。这一步不再直接让模型在整张 X 光图里找很小的缺陷，而是先验证：如果已经裁到焊点附近，模型能不能判断该局部是否有空洞。

## ROI 划分原则

- 人工标注框只标空洞本体，不要求标完整焊点。
- 脚本以空洞框中心为中心，向外扩成正方形 ROI。
- ROI 边长按缺陷框最大边的 `3x / 4x / 5x` 生成，并设置最小边长 `224` 像素、最大边长 `768` 像素。
- 每个 ROI 最终统一缩放为 `224x224`，用于分类模型训练。
- 对同一个空洞框，会生成不同尺度和轻微中心偏移的多个正样本 patch。

## 样本构成

- 正样本 `void`：来自已完成标注的空洞图片，排除之前确认不参与训练的 4 张多余标签图片。
- 负样本 `normal`：来自原始库中的合格图，以及桥连、透锡不足图片中的随机局部区域。
- 数据按源图切分为训练、验证、测试，避免同一张原图裁出的 patch 同时进入训练集和验证集。

## 输出位置

- ROI 数据集：`D:\Xray\pcb_xray_annotation_workspace\void_roi_dataset`
- 数据清单：`D:\Xray\pcb_xray_annotation_workspace\void_roi_dataset\manifest.csv`
- 数据摘要：`D:\Xray\pcb_xray_annotation_workspace\void_roi_dataset\summary.json`
- 训练输出：`D:\Xray\pcb_xray_annotation_workspace\void_roi_dataset\runs\void_roi_cls_baseline`

## 当前基线结果

- 训练模型：`YOLO11n-cls`
- 输入尺寸：`224x224`
- 早停轮次：`77`
- 最佳轮次：`57`
- 最高验证准确率：`0.964`
- 最佳权重：`D:\Xray\pcb_xray_annotation_workspace\void_roi_dataset\runs\void_roi_cls_baseline\weights\best.pt`

这说明 ROI 级别的“空洞 vs 正常”分类已经能学到明显信号了，比直接整图检测更有希望。但它仍然是第一版基线，后面最该补的是更像真正常焊点的负样本和更稳的 ROI 规则。

## 注意事项

这版负样本主要是自动随机裁剪，质量还不等同于人工挑选的“正常焊点 ROI”。如果模型后续误报很多，优先改进负样本：多加入真正相似但无空洞的焊点局部，而不是单纯继续加训练轮数。
