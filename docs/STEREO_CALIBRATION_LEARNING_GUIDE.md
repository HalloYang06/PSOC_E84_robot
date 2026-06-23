# 双 USB 摄像头完整双目标定学习指南

本文档用于把当前 NanoPi 双 USB 摄像头从“目标级像素视差”推进到“可验证的双目标定流程”。当前阶段仍然只做视觉上下文，不给机械臂运动授权。

## 0. 先分清三件事

1. 目标级视差：我们已经做到。左右图都识别 `bottle`，比较 bbox 中心，得到 `horizontal_disparity_px`。
2. 双目标定：下一步要做。用棋盘格求左右相机内参、畸变、外参和极线校正参数。
3. 米制深度：必须在标定后做。公式是 `Z = f * B / disparity`，但 `f`、`B`、校正矩阵和畸变都要先求出来。

## 1. 张正友法在做什么

张正友法的关键想法是：不需要昂贵的 3D 标定架，只需要一个已知方格尺寸的平面棋盘格，让相机从多个不同姿态观察它。棋盘格每个内角点在现实世界中的 3D 坐标是已知的，因为它们都在同一个平面上，例如：

```text
(0, 0, 0), (1*square, 0, 0), (2*square, 0, 0), ...
```

相机图像里能检测到这些角点的 2D 像素坐标。多张不同姿态的 `3D 平面点 -> 2D 图像点` 对应关系，可以反推出：

- 相机内参：焦距 `fx/fy`、主点 `cx/cy`
- 镜头畸变：径向/切向畸变
- 每张图的棋盘格姿态

对双目相机，还要进一步求：

- 左右相机之间的旋转 `R`
- 左右相机之间的平移 `T`
- 极线校正矩阵
- 视差转深度用的 `Q` 矩阵

## 2. OpenCV 函数对应关系

完整流程大致对应这些 OpenCV 函数：

```text
findChessboardCorners / cornerSubPix
  -> 找棋盘格内角点并做亚像素优化

calibrateCamera
  -> 分别求左相机、右相机内参和畸变

stereoCalibrate
  -> 求左右相机外参 R/T

stereoRectify
  -> 求极线校正矩阵和 Q 矩阵

initUndistortRectifyMap + remap
  -> 把左右图校正成同一水平扫描线

StereoBM / StereoSGBM
  -> 从校正后的左右图生成 dense disparity map

reprojectImageTo3D
  -> 用 Q 矩阵把视差转成 3D 点云/深度
```

## 3. 棋盘格文件

本仓库已生成一份 A4 可打印棋盘格：

- `docs/assets/calibration/zhang_chessboard_9x6_inner_20mm_A4.pdf`
- `docs/assets/calibration/zhang_chessboard_9x6_inner_20mm_A4_300dpi.png`

参数：

- 内角点：`9x6`
- 方格数量：`10x7`
- 方格边长：`20 mm`
- 命令参数：`--chessboard-size 9x6 --square-size-m 0.020`

打印要求：

- 选择 100% / Actual size / 实际大小。
- 不要选择“适合页面”。
- 打印后用尺量一个方格，确认是 20 mm。
- 最好贴到硬纸板或平整板上，不能弯曲。

## 4. 当前采集命令

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge stereo_chessboard_calibration.py \
  --chessboard-size 9x6 \
  --square-size-m 0.020 \
  --pretty
```

通过标准：

```text
left.found=true
right.found=true
pair_ok=true
corner_count=54
```

如果 `pair_ok=false`，先不要进入标定。通常原因是棋盘格没完整出现在两路画面里、太斜、反光、模糊、格子尺寸/内角点参数填错。

## 5. 应该采哪些姿态

至少采 15-20 张有效左右图，推荐姿态：

- 正中，平放
- 左上、右上、左下、右下
- 靠近、中距离、远一点
- 轻微绕水平轴倾斜
- 轻微绕垂直轴倾斜
- 轻微旋转，但不要让角点出画面

好样本的特点：

- 棋盘格同时完整出现在左右图。
- 角点清晰，不糊。
- 没有强反光。
- 覆盖画面不同区域，不要 20 张都在正中。

坏样本要丢弃：

- 任意一路 `found=false`
- 棋盘格被裁切
- 图像模糊
- 打印纸弯曲明显
- 光照过暗或反光过强

## 6. 为什么现在还不能输出米制深度

我们已经观察到瓶子从较近位置到较远位置时，视差从约 `87-88 px` 降到约 `80 px`。这个趋势是对的，但它只是定性验证。

要输出米制深度，需要：

```text
Z = f * B / disparity
```

其中：

- `f`：校正后相机焦距，单位是像素
- `B`：两相机基线距离，单位是米
- `disparity`：同一点在左右图的水平视差

没有标定时，`f` 不准、`B` 不准、畸变未消除、左右图未极线校正，所以不能把像素视差直接当深度。

## 7. 权威资料

- OpenCV Camera Calibration tutorial: https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html
- OpenCV calib3d module concepts/functions: https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html
- Zhang, "A Flexible New Technique for Camera Calibration": https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/tr98-71.pdf

