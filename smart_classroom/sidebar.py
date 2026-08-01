"""侧边栏输入。

这个模块只负责收集用户输入并生成 `SimulationConfig`，不直接推进仿真。
"""

from __future__ import annotations

import streamlit as st

from .models import SimulationConfig
from .physics import build_config


def render_sidebar() -> tuple[SimulationConfig, str, bool]:
    """渲染侧边栏，并返回仿真配置、刷新速度和重置按钮状态。"""

    st.sidebar.header("物理与结构参数")

    outdoor_temp = st.sidebar.slider(
        "1. 室外温度 (°C)", -10.0, 40.0, 32.0, 0.5
    )
    init_temp = st.sidebar.slider(
        "2. 室内初始温度 (°C)", 15.0, 35.0, 28.0, 0.5
    )
    init_co2 = st.sidebar.slider(
        "3. CO₂ 初始浓度 (ppm)", 350, 2500, 600, 50
    )
    classroom_people = st.sidebar.number_input(
        "4. 教室人数 (人)", 0, 100, 45, 1
    )
    classroom_area = st.sidebar.number_input(
        "5. 教室面积 (㎡)", 20, 200, 80, 5
    )
    classroom_height = st.sidebar.slider(
        "6. 教室层高 (m)", 2.5, 4.5, 3.0, 0.1
    )
    window_openable = st.sidebar.checkbox("7. 窗户是否可开启", True)

    st.sidebar.markdown("---")
    st.sidebar.subheader("控制目标")

    target_temp = st.sidebar.slider(
        "8. 空调设定点温度 (°C)", 16.0, 30.0, 24.0, 0.5
    )
    comfort_band = st.sidebar.slider(
        "9. 舒适区跨度 (±°C)", 0.5, 2.0, 1.0, 0.5
    )
    co2_target = st.sidebar.slider(
        "10. CO₂ 控制目标 (ppm)", 800, 1400, 1000, 50
    )

    # 警戒值必须高于目标值，否则“目标”和“警戒”的语义会冲突。
    co2_warning_min = int(co2_target + 100)
    co2_warning_default = max(1500, co2_warning_min)
    co2_warning = st.sidebar.slider(
        "11. CO₂ 警戒值 (ppm)",
        co2_warning_min,
        2500,
        co2_warning_default,
        50,
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("模型校准参数")

    thermal_mass_factor = st.sidebar.slider(
        "12. 等效热质量系数",
        min_value=5.0,
        max_value=50.0,
        value=15.0,
        step=1.0,
        help="越大表示墙体、家具等热惯性越强，温度变化越慢。",
    )
    wall_u_factor = st.sidebar.slider(
        "13. 围护结构换热系数 (kW/K·㎡)",
        min_value=0.0005,
        max_value=0.0060,
        value=0.0020,
        step=0.0005,
        format="%.4f",
    )
    person_sensible_heat_kw = st.sidebar.slider(
        "14. 单人显热 (kW/人)",
        min_value=0.05,
        max_value=0.15,
        value=0.08,
        step=0.01,
    )
    co2_generation_m3h_per_person = st.sidebar.slider(
        "15. 单人 CO₂ 产生率 (m³/h·人)",
        min_value=0.010,
        max_value=0.030,
        value=0.018,
        step=0.001,
        format="%.3f",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("MPC 参数")

    prediction_horizon = st.sidebar.slider(
        "16. 预测时界 (分钟)", 10, 60, 30, 5
    )
    discount_factor = st.sidebar.slider(
        "17. 时间折扣因子", 0.90, 1.00, 0.98, 0.01
    )
    sim_speed = st.sidebar.select_slider(
        "18. 模拟刷新速度",
        options=["慢", "中", "快"],
        value="中",
    )

    reset_requested = st.sidebar.button(
        "重置模拟体系",
        width="stretch",
    )

    config = build_config(
        outdoor_temp=float(outdoor_temp),
        init_temp=float(init_temp),
        init_co2=float(init_co2),
        classroom_people=int(classroom_people),
        classroom_area=int(classroom_area),
        classroom_height=float(classroom_height),
        window_openable=bool(window_openable),
        target_temp=float(target_temp),
        comfort_band=float(comfort_band),
        co2_target=int(co2_target),
        co2_warning=int(co2_warning),
        thermal_mass_factor=float(thermal_mass_factor),
        wall_u_factor=float(wall_u_factor),
        person_sensible_heat_kw=float(person_sensible_heat_kw),
        co2_generation_m3h_per_person=float(co2_generation_m3h_per_person),
        prediction_horizon=int(prediction_horizon),
        discount_factor=float(discount_factor),
    )

    return config, str(sim_speed), reset_requested

