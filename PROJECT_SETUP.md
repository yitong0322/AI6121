# AI6121 本地 SfM 环境与运行指南

本仓库实现教学用途的增量式 Structure-from-Motion（SfM）流程，从已标定的多视图图像
生成带颜色的稀疏点云。主入口是 `main.ipynb`；`scripts/run_i_sfm_notebook.py` 用于
无界面、可复现实验运行。

## 1. 安装环境

需要 Conda。下列命令会创建或更新 Python 3.10 环境，并注册 Jupyter kernel：

```bash
bash scripts/bootstrap.sh
conda activate ai6121-sfm
python -m pytest -q tests/test_reconstruction.py
```

环境定义在 `environment.yml`，包括 NumPy、SciPy、OpenCV（SIFT、图像读写和投影）、
Open3D、JupyterLab、Matplotlib 和 FFmpeg。

## 2. 输入数据

每个数据集目录必须包含按拍摄顺序命名的图像，以及与图像分辨率、设备和焦段对应的
3x3 相机内参矩阵 `K.txt`：

```text
datasets/scene_a/
├── 00.jpg
├── 01.jpg
├── ...
└── K.txt
```

相邻帧建议保留 60%--80% 的重叠，以平移为主并减少纯旋转；不要混用分辨率、数码变焦
或焦段。视频先抽帧：

```bash
bash scripts/extract_frames.sh input.mp4 datasets/scene_a 2
```

最后一个参数是每秒抽取帧数。相机内参可用 `camera calibration.ipynb` 标定。

## 3. 运行重建

交互式运行：

```bash
conda activate ai6121-sfm
jupyter lab main.ipynb
```

在 Notebook 的配置单元设置 `dataset_path`，并选择 `Python (AI6121 SfM)` kernel。

无界面运行 Temple Ring 或自定义数据集：

```bash
python scripts/run_i_sfm_notebook.py \
  datasets/templeRing \
  outputs/temple_ring \
  --nfeatures 3000 \
  --min-baseline-inliers 50 \
  --min-parallax-deg 2.0
```

命令会写出 `i_sfm_executed.ipynb`（带日志的执行记录）和
`i_sfm_reconstruction.ply`（带颜色的稀疏点云及相机中心）。

## 4. 实现与合规边界

项目允许使用通用库完成图像读写、SIFT 特征、描述子匹配、线性代数、通用数值优化和
可视化；核心 SfM 几何不调用现成的 SfM/PnP/三角化求解 API，也不调用 COLMAP。

当前流程为：

1. SIFT 提取与 Lowe ratio 匹配；
2. 本地 NumPy/SVD/RANSAC 基础矩阵估计；
3. 本地 Essential 矩阵分解、秩约束和正深度候选选择；
4. 本地 DLT-RANSAC PnP，随后使用 SciPy 通用鲁棒最小二乘精化位姿；
5. 本地线性三角化，随后验证双相机正深度和双视图重投影误差；
6. SciPy Bundle Adjustment 和 PLY 导出。

代码不使用 `cv2.findFundamentalMat`、`cv2.findEssentialMat`、
`cv2.recoverPose`、`cv2.solvePnPRansac` 或 `cv2.triangulatePoints`。

## 5. Temple Ring 实验记录

下表使用同一 Temple Ring 数据、Python 3.10 环境及 headless 参数
`--nfeatures 3000 --min-baseline-inliers 50`。原始版本来自初始 Git 提交
`c727a36`，仅用于比较合规修改的影响。

| 实现 | 注册图像 | 最终 3D 点 | 平均重投影误差 | PLY 顶点 |
| --- | ---: | ---: | ---: | ---: |
| 初始 Git 版本 | 46/46 | 7180 | 0.45 px | 7226 |
| 早期合规基线 | 40/46 | 10336 | 250.09 px | 3890 |
| 当前组合版 | 13/46 | 1522 | 1.56 px | 1535 |

当前组合版显著降低了局部点云的重投影误差，但严格的双视图过滤减少了后续 PnP 可用的
对应关系，注册覆盖率为 13/46。因此该版本合规且局部几何质量较高，但仍需改进增量
注册策略以恢复完整场景覆盖率。

## 6. 开发检查

提交前运行：

```bash
python -m pytest -q tests/test_reconstruction.py
python -m py_compile geometry.py reconstruction.py
git diff --check
```

生成的 `outputs/`、本地 Conda 环境和参考仓库不应提交到 Git。
