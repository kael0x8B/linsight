# 固定算法验收集

每个不可变测试集放在独立版本目录中，完成标注复核后再把 `current` 指向该目录。真实验收目录必须包含：

- `manifest.json`：`schemaVersion=1.0`、唯一 `datasetVersion`、`dataOrigin=REAL_FIELD`；
- `ground-truth.jsonl`：每行一个人工复核样本，含 `sampleId`、`algorithmCode`、`condition`、`positive`、相对媒体路径和媒体 SHA256；
- `predictions.jsonl`：现场 Runtime/任务回放器输出，必须与标注样本一一对应；
- `media/`：真实图片或视频，禁止 Mock、生成图片或空占位文件用于生产验收。

车牌样本还应填写 `expectedLabel`、`plateType`；车辆样本填写 `vehicleClass`，取值为
`sedan/suv/van/small_truck/box_truck/medium_truck/heavy_truck/trailer/engineering_vehicle`。
预测中的车牌阳性结果必须包含
`ocrConfidence`、`trackId`、`vehicleTrackId` 和 `plateFinalizedFromFrames >= 2`。

预测行最小示例：

```json
{"sampleId":"field-001","positive":true,"latencyMs":120,"preprocessMs":8,"inferenceMs":95,"postprocessMs":17,"framesProcessed":30,"elapsedSeconds":2,"predictedLabel":"皖A12345","ocrConfidence":0.93,"trackId":"plate-1","vehicleTrackId":"vehicle-1","plateFinalizedFromFrames":3}
```

执行：

```bash
python3 scripts/algorithm-benchmark.py --dataset acceptance/datasets/current \
  --runner-command '/opt/linsight/bin/export-field-predictions'
```

如果没有真实数据或真实预测，输出会保持 `WAITING_FOR_REAL_DATA` / `WAITING_FOR_FIELD_VIDEO`。
