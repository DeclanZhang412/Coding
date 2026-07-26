"""Streamlit 页面展示组件。

本模块只负责“把状态画出来”，不直接修改物理状态。这样 UI 布局和
控制算法可以独立调整，避免页面代码再次膨胀。
"""

from __future__ import annotations

from typing import Any, MutableMapping, cast

import pandas as pd
import streamlit as st

from .control import calculate_compliance_metrics
from .models import Action, DecisionState, PhysicalResult, SimulationConfig


def configure_page() -> None:
    """配置 Streamlit 页面基础信息。"""

    st.set_page_config(
        page_title="智能教室环境控制模拟器 v5.0",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def render_intro() -> None:
    """渲染页面标题和系统简介。"""

    st.title("🏫 智能教室环境控制模拟器 v5.0")
    st.markdown(
        """
基于**多步滚动预测控制（MPC）**、**独立双沙盒基准对照**、
**热平衡诊断**与**分级机械新风控制**的教室数字孪生系统。
"""
    )


def render_runtime_summary(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染仿真时间、教室尺度和控制目标概览。"""

    elapsed_minutes = int(session_state["current_step"])
    hours = elapsed_minutes // 60
    mins = elapsed_minutes % 60
    runtime_str = (
        f"{hours} 小时 {mins} 分钟"
        if hours > 0
        else f"{mins} 分钟"
    )

    st.info(
        f"⏳ **仿真时间**：{runtime_str} | "
        f"🧱 **教室体积**：{config.classroom_volume:.1f} m³ | "
        f"🔥 **有效热容**：{config.heat_capacity_kwh_per_k:.2f} kWh/K | "
        f"🎯 **舒适区**：{config.t_min:.1f}–{config.t_max:.1f}°C | "
        f"🍃 **CO₂目标/警戒**："
        f"{config.co2_target}/{config.co2_warning} ppm | "
        f"🔮 **预测时界**：{config.prediction_horizon} 分钟"
    )


def render_status_cards(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染顶部实时状态卡片。"""

    history = session_state["history"]
    has_history = not history.empty
    last = history.iloc[-1] if has_history else pd.Series(dtype=object)

    st.subheader("📊 建筑设备动态看板")
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        current_temp = session_state["current_temp"]
        if current_temp > config.t_max:
            temp_desc = f"高于上限 {current_temp - config.t_max:.2f}°C"
            temp_color = "inverse"
        elif current_temp < config.t_min:
            temp_desc = f"低于下限 {config.t_min - current_temp:.2f}°C"
            temp_color = "inverse"
        else:
            temp_desc = "处于舒适区"
            temp_color = "normal"

        st.metric(
            "🌡️ 室内温度",
            f"{current_temp:.2f} °C",
            temp_desc,
            delta_color=temp_color,
        )

    with col2:
        current_co2 = session_state["current_co2"]
        if current_co2 <= config.co2_target:
            co2_desc = "空气质量达标"
            co2_color = "normal"
        elif current_co2 < config.co2_warning:
            co2_desc = f"超目标 {current_co2 - config.co2_target:.0f} ppm"
            co2_color = "inverse"
        else:
            co2_desc = f"超过警戒 {current_co2 - config.co2_warning:.0f} ppm"
            co2_color = "inverse"

        st.metric(
            "🍃 CO₂ 浓度",
            f"{current_co2:.1f} ppm",
            co2_desc,
            delta_color=co2_color,
        )

    with col3:
        if has_history:
            ac_text = (
                "Standby"
                if last["空调状态"] == "关闭"
                else f"{last['空调状态']}（{last['风速']}）"
            )
        else:
            ac_text = "Standby"
        st.metric("❄️ 空调状态", ac_text)

    with col4:
        fresh_text = (
            f"{last['新风档位']}档"
            if has_history and last["新风档位"] != "关闭"
            else "关闭"
        )
        fresh_delta = (
            f"{last['换气率ACH']:.2f} ACH / "
            f"{last['通风量m3h']:.0f} m³/h"
            if has_history
            else "等待初始化"
        )
        st.metric("🌪️ 新风状态", fresh_text, fresh_delta)

    with col5:
        window_text = (
            f"{last['窗户开启比例']:.1f}%"
            if has_history
            else "0.0%"
        )
        window_delta = (
            f"有效面积 {last['有效开口面积']:.2f} ㎡"
            if has_history
            else "有效面积 0 ㎡"
        )
        st.metric("🪟 窗户开度", window_text, window_delta)

    with col6:
        compliance = calculate_compliance_metrics(history, config)
        if has_history:
            quality_ok = (
                compliance["mpc_temp"] >= 80.0
                and compliance["mpc_co2_safe"] >= 95.0
            )
            if quality_ok:
                energy_delta = f"较基准节能 {last['节能比例']:.1f}%"
                energy_color = "normal"
            else:
                energy_delta = (
                    f"环境约束未满足；节能 {last['节能比例']:.1f}% 仅供参考"
                )
                energy_color = "inverse"
        else:
            energy_delta = "双沙盒计算中"
            energy_color = "normal"

        st.metric(
            "⚡ MPC 累计电耗",
            f"{session_state['total_energy']:.3f} kWh",
            energy_delta,
            delta_color=energy_color,
        )


def render_history_charts(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染历史曲线。

    图表保持和历史列名绑定，状态写入模块只要保持列名不变，
    页面展示就不需要知道物理模型内部细节。
    """

    history = session_state["history"]

    st.subheader("📈 双系统沙盒对比与历史曲线")
    if history.empty:
        st.info("暂无数据，请开启模拟。")
        return

    chart_df = history.copy().set_index("累计时间(分钟)")

    st.markdown("**1. 温度与舒适区演化 (°C)**")
    st.line_chart(
        chart_df[
            [
                "室内温度",
                "基准室内温度",
                "室外温度",
                "目标温度",
                "舒适区上限",
                "舒适区下限",
            ]
        ]
    )

    st.markdown("**2. CO₂ 与空气质量阈值 (ppm)**")
    chart_df["CO₂目标线"] = float(config.co2_target)
    chart_df["CO₂警戒线"] = float(config.co2_warning)
    st.line_chart(
        chart_df[
            [
                "CO2浓度",
                "基准CO2浓度",
                "CO₂目标线",
                "CO₂警戒线",
            ]
        ]
    )

    st.markdown("**3. MPC 实时设备功率 (kW)**")
    st.line_chart(chart_df[["总功率", "空调功率", "新风功率"]])

    st.markdown("**4. 实时净热负荷与温变速率**")
    st.line_chart(
        chart_df[
            [
                "人员热负荷",
                "围护结构热负荷",
                "通风热负荷",
                "空调制冷量",
                "净热负荷",
            ]
        ]
    )


def render_decision_panel(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染 MPC 可解释决策面板。"""

    history = session_state["history"]
    st.subheader("🤖 MPC 预测控制决策内核")

    if (
        history.empty
        or not session_state["last_decision_pool"]
        or session_state["last_result"] is None
    ):
        st.write("等待预测决策数据生成……")
        return

    decision = cast(DecisionState, session_state["last_decision_pool"])
    best: Action = decision["best"]
    evaluation = decision["evaluation"]
    result = cast(PhysicalResult, session_state["last_result"])

    st.markdown("**🧠 当前执行动作**")
    st.success(
        f"""
- 空调：**{best.ac_mode} / {best.ac_level}**
- 机械新风：**{best.fresh_level}**
- 窗户开度：**{best.window_ratio * 100:.0f}%**
- 预测 {config.prediction_horizon} 分钟后：  
  **{evaluation['pred_temp']:.2f}°C / {evaluation['pred_co2']:.0f} ppm**
"""
    )

    if session_state["override_reason"]:
        st.warning(f"🛡️ **硬约束覆盖：**{session_state['override_reason']}")

    if config.outdoor_temp > config.t_max + 2.0 and best.window_ratio > 0.0:
        st.warning(
            f"室外温度 {config.outdoor_temp:.1f}°C 高于舒适区，"
            f"当前窗户开度为 {best.window_ratio * 100:.0f}%。"
        )

    st.markdown("**🔥 实时热量收支**")
    heat_table = pd.DataFrame(
        {
            "热量项目": [
                "人员显热",
                "围护结构传热",
                "通风显热",
                "空调制冷",
                "空调制热",
                "净热负荷",
            ],
            "功率 (kW)": [
                result.people_heat_kw,
                result.envelope_heat_kw,
                result.ventilation_heat_kw,
                -result.ac_cooling_kw,
                result.ac_heating_kw,
                result.net_heat_kw,
            ],
        }
    )
    st.dataframe(heat_table, width="stretch", hide_index=True)

    temp_trend_text = (
        "升温"
        if result.temp_change_c_per_min > 0
        else "降温"
        if result.temp_change_c_per_min < 0
        else "稳定"
    )
    st.caption(
        f"当前净热负荷：{result.net_heat_kw:+.2f} kW；"
        f"预计每分钟{temp_trend_text} "
        f"{abs(result.temp_change_c_per_min):.4f}°C。"
    )

    st.markdown("**⚡ 实时功率分拆**")
    power_table = pd.DataFrame(
        {
            "设备组件": [
                "空调系统",
                "新风机组",
                "控制器与传感器",
                "系统总功率",
            ],
            "当前电功率 (kW)": [
                result.ac_electric_kw,
                result.fresh_electric_kw,
                result.base_electric_kw,
                result.total_electric_kw,
            ],
        }
    )
    st.dataframe(power_table, width="stretch", hide_index=True)

    st.markdown(f"**📊 {config.prediction_horizon} 分钟候选动作累计代价 Top 5**")
    for index, item in enumerate(decision["pool"][:5], start=1):
        action: Action = item["action"]
        st.caption(
            f"{index}. "
            f"AC={action.ac_mode}/{action.ac_level}｜"
            f"新风={action.fresh_level}｜"
            f"窗={action.window_ratio * 100:.0f}%｜"
            f"代价={item['cost']:.1f}｜"
            f"终态={item['pred_temp']:.2f}°C / "
            f"{item['pred_co2']:.0f}ppm"
        )


def render_analysis_area(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染图表与决策解释的双栏区域。"""

    st.markdown("---")
    col_chart, col_decide = st.columns([2, 1])

    with col_chart:
        render_history_charts(session_state, config)

    with col_decide:
        render_decision_panel(session_state, config)


def render_comparison(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染 MPC 与传统基准的综合绩效表。"""

    history = session_state["history"]
    compliance = calculate_compliance_metrics(history, config)

    st.markdown("---")
    st.subheader("🏁 MPC 与传统基准综合绩效比较")

    comparison_df = pd.DataFrame(
        {
            "指标": [
                "累计能耗 (kWh)",
                "温度舒适达标率 (%)",
                f"CO₂ ≤ {config.co2_target} ppm 达标率 (%)",
                f"CO₂ ≤ {config.co2_warning} ppm 安全率 (%)",
                "当前室温 (°C)",
                "当前 CO₂ (ppm)",
            ],
            "MPC": [
                round(session_state["total_energy"], 3),
                round(compliance["mpc_temp"], 1),
                round(compliance["mpc_co2"], 1),
                round(compliance["mpc_co2_safe"], 1),
                round(session_state["current_temp"], 2),
                round(session_state["current_co2"], 1),
            ],
            "传统基准": [
                round(session_state["benchmark_energy"], 3),
                round(compliance["bench_temp"], 1),
                round(compliance["bench_co2"], 1),
                round(compliance["bench_co2_safe"], 1),
                round(session_state["bench_temp"], 2),
                round(session_state["bench_co2"], 1),
            ],
        }
    )
    st.dataframe(comparison_df, width="stretch", hide_index=True)

    if history.empty:
        return

    mpc_quality_ok = (
        compliance["mpc_temp"] >= 80.0
        and compliance["mpc_co2_safe"] >= 95.0
    )
    if mpc_quality_ok:
        st.success("MPC 已达到预设环境质量要求，节能率可以作为有效比较指标。")
    else:
        st.warning(
            "当前 MPC 尚未同时满足 80% 温度舒适达标率和 95% CO₂ 安全率；"
            "节能结果只可作为辅助数据，不应单独用于宣称系统更优。"
        )


def render_logs_and_export(session_state: MutableMapping[str, Any]) -> None:
    """渲染运行日志和 CSV 导出按钮。"""

    history = session_state["history"]

    st.markdown("---")
    st.subheader("📝 系统运行日志")

    log_container = st.container(height=180)
    with log_container:
        for log in session_state["logs"]:
            st.text(log)

    if history.empty:
        return

    csv_data = history.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="⬇️ 导出完整仿真数据 CSV",
        data=csv_data,
        file_name="smart_classroom_digital_twin_v5.csv",
        mime="text/csv",
    )

