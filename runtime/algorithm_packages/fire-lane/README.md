# 消防通道占用

检测消防通道内持续静止的车辆、座椅和箱包；不覆盖沙堆、托盘、纸箱等模型未支持的障碍物。

模型必须具备以下标签：car, truck, bus, bicycle, motorcycle, chair, couch, bench, backpack, handbag, suitcase。复用现有 COCO ONNX/RKNN，规则配置指定区域、连续帧与持续时间。默认持续 30 秒，按现场调整。无单帧告警，不以包结构校验代替现场效果验收。
