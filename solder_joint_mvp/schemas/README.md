# 数据契约

- `inventory.schema.json`：图片盘点清单；记录原始路径、来源、尺寸与读取错误。
- `review.schema.json`：目标元件族复核；区分 Codex 的 `suggested_decision` 与用户最终 `decision`，取值为 `keep/other_component/reject/uncertain`，并保存同族分数和近重复组。
- `array-grid.schema.json`：网格拟合结果；每个位置保留行列编号、中心、尺度、置信度和状态。
- `roi-manifest.schema.json`：ROI 追溯清单；记录原图、阵列、网格位置、裁切边界和输出状态。

所有坐标使用原图像素坐标，原点位于左上角，`x` 向右、`y` 向下。矩形统一表示为 `[x_min, y_min, x_max, y_max]`。
