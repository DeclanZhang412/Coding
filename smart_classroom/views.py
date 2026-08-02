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
        page_title="智能教室控制台",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(
        """
        <style>
            :root {
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            body, .stApp, .main, .block-container {
                background-color: #070b16 !important;
                color: #e2e8f0 !important;
            }
            .block-container {
                padding: 1rem 1.2rem !important;
            }
            .stSidebar {
                background-color: #0c1428 !important;
                color: #e2e8f0 !important;
            }
            .css-1v0mbdj.e1fqkh3o3, .css-1v0mbdj.e1fqkh3o6, .css-1v0mbdj.e1fqkh3o7 {
                background-color: #0c1428 !important;
            }
            .hero-card {
                background: rgba(14, 20, 38, 0.96);
                color: #f8fafc;
                padding: 1.35rem 1.45rem;
                border-radius: 22px;
                margin-bottom: 1rem;
                border: 1px solid rgba(148,163,184,0.14);
            }
            .hero-title {
                font-size: 1.72rem;
                font-weight: 700;
                margin-bottom: 0.35rem;
            }
            .hero-subtitle {
                font-size: 1rem;
                color: rgba(226, 232, 240, 0.82);
                line-height: 1.7;
            }
            .stMetric {
                margin-bottom: 0.5rem;
            }
            .status-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.65rem;
            }
            .stAlert, .stDataFrame, .stExpander {
                border-radius: 20px;
                background: rgba(13, 19, 34, 0.98) !important;
                color: #e2e8f0 !important;
                border: 1px solid rgba(148,163,184,0.10) !important;
            }
            .stTabs [data-baseweb="tab-list"] {
                gap: 0.35rem;
                background: rgba(13, 19, 34, 0.95);
                padding: 0.3rem;
                border-radius: 999px;
                border: 1px solid rgba(148,163,184,0.10);
                box-shadow: inset 0 1px 2px rgba(255,255,255,0.03);
            }
            .stTabs [data-baseweb="tab"] {
                border-radius: 999px;
                padding: 0.4rem 0.95rem;
                background: rgba(148,163,184,0.07);
                color: #f8fafc;
            }
            .stTabs [data-baseweb="tab"][aria-selected="true"] {
                background: rgba(56,189,248,0.18);
                color: #f8fafc;
            }
            .stAlert, .stDataFrame, .stExpander {
                border-radius: 20px;
                background: rgba(13, 19, 34, 0.98) !important;
                color: #e2e8f0 !important;
                border: 1px solid rgba(148,163,184,0.10) !important;
                box-shadow: 0 20px 55px rgba(0,0,0,0.17);
                backdrop-filter: blur(10px);
            }
            .stDataFrame table {
                background: rgba(15,23,42,0.95) !important;
                color: #e2e8f0 !important;
            }
            .stButton > button {
                background-color: rgba(56,189,248,0.18) !important;
                color: #f8fafc !important;
                border: 1px solid rgba(56,189,248,0.30) !important;
                border-radius: 999px !important;
                padding: 0.55rem 1.1rem !important;
                box-shadow: 0 18px 45px rgba(56,189,248,0.08);
            }
            .stButton > button:hover {
                background-color: rgba(56,189,248,0.24) !important;
            }
            .inactive-prompt {
                background: rgba(10, 14, 26, 0.98);
                border: 1px solid rgba(148,163,184,0.10);
                border-radius: 20px;
                padding: 1.2rem;
                color: #e2e8f0;
                margin: 0.75rem 0;
                box-shadow: 0 20px 55px rgba(0,0,0,0.18);
                backdrop-filter: blur(10px);
            }
            .inactive-prompt-title {
                font-size: 1.05rem;
                font-weight: 700;
                margin-bottom: 0.65rem;
            }
            .inactive-prompt-text {
                color: #cbd5e1;
                line-height: 1.65;
                margin-bottom: 1rem;
            }
            .pulse-arrow {
                display: block;
                margin: 0 auto;
                width: 32px;
                height: 32px;
                color: #38bdf8;
                font-size: 1.7rem;
            }
            .css-1d391kg {
                background-color: #111827 !important;
            }
            .css-1iq3q6v {
                background-color: #111827 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_intro() -> None:
    """渲染页面标题和系统简介。"""

    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-title">智能教室控制台</div>
            <div class="hero-subtitle">
                以实时控制与预测决策为核心，支撑教室环境的动态调节与性能评估。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
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

    cols = st.columns(3)
    with cols[0]:
        st.metric("仿真时间", runtime_str)
        st.metric("教室体积", f"{config.classroom_volume:.1f} m³")
    with cols[1]:
        st.metric("有效热容", f"{config.heat_capacity_kwh_per_k:.2f} kWh/K")
        st.metric("舒适区", f"{config.t_min:.1f}–{config.t_max:.1f}°C")
    with cols[2]:
        st.metric("CO₂ 目标/警戒", f"{config.co2_target}/{config.co2_warning} ppm")
        st.metric("预测时界", f"{config.prediction_horizon} 分钟")


def render_status_cards(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染顶部实时状态卡片。"""

    history = session_state["history"]
    has_history = not history.empty
    last = history.iloc[-1] if has_history else pd.Series(dtype=object)

    st.subheader("运行概览")

    cards: list[str] = []

    def status_card(
        title: str,
        value: str,
        note: str | None = None,
        note_type: str = 'positive',
    ) -> None:
        note_class = 'status-card-note '
        note_class += 'warning' if note_type == 'warning' else 'positive'
        card_html = f"""
            <div class='status-card'>
                <div class='status-card-title'>{title}</div>
                <div class='status-card-value'>{value}</div>
        """
        if note:
            card_html += f"<div class='{note_class}'>{note}</div>"
        card_html += "</div>"
        cards.append(card_html)

    current_temp = session_state["current_temp"]
    if current_temp > 25.5:
        temp_desc = "过热"
        temp_type = 'warning'
    elif current_temp > 25.0:
        temp_desc = "微超"
        temp_type = 'warning'
    elif current_temp > config.t_max:
        temp_desc = f"高于上限 {current_temp - config.t_max:.2f}°C"
        temp_type = 'warning'
    elif current_temp < config.t_min:
        temp_desc = f"低于下限 {config.t_min - current_temp:.2f}°C"
        temp_type = 'warning'
    else:
        temp_desc = "处于舒适区"
        temp_type = 'positive'

    status_card(
        "室内温度",
        f"{current_temp:.2f} °C",
        temp_desc,
        temp_type,
    )

    current_co2 = session_state["current_co2"]
    if current_co2 <= config.co2_target:
        co2_desc = "空气质量达标"
        co2_type = 'positive'
    elif current_co2 < config.co2_warning:
        co2_desc = f"超目标 {current_co2 - config.co2_target:.0f} ppm"
        co2_type = 'warning'
    else:
        co2_desc = f"超过警戒 {current_co2 - config.co2_warning:.0f} ppm"
        co2_type = 'warning'

    status_card(
        "CO₂ 浓度",
        f"{current_co2:.1f} ppm",
        co2_desc,
        co2_type,
    )

    if has_history:
        ac_text = (
            "待机"
            if last["空调状态"] == "关闭"
            else f"{last['空调状态']} / {last['风速']}"
        )
    else:
        ac_text = "待机"

    status_card("空调状态", ac_text)

    fresh_text = (
        f"{last['新风档位']} 档"
        if has_history and last["新风档位"] != "关闭"
        else "关闭"
    )
    fresh_delta = (
        f"{last['换气率ACH']:.2f} ACH / {last['通风量m3h']:.0f} m³/h"
        if has_history
        else "等待初始化"
    )
    status_card("新风状态", fresh_text, fresh_delta)

    window_text = (
        f"{last['窗户开启比例']:.1f}%"
        if has_history
        else "0.0%"
    )
    window_delta = (
        f"窗户有效面积 {last['有效开口面积']:.2f} ㎡"
        if has_history
        else "有效面积 0 ㎡"
    )
    status_card("窗户开度", window_text, window_delta)

    compliance = session_state.get("compliance_metrics")
    if compliance is None:
        compliance = calculate_compliance_metrics(history, config)
    if has_history:
        energy_saving = float(last.get("节能比例", 0.0))
        quality_ok = (
            compliance["mpc_temp"] >= 80.0
            and compliance["mpc_co2_safe"] >= 95.0
        )
        if quality_ok and energy_saving >= 30.0:
            energy_delta = f"较基准节能 {energy_saving:.1f}%，已达 30% 目标"
            energy_type = 'positive'
        elif energy_saving >= 30.0:
            energy_delta = f"较基准节能 {energy_saving:.1f}%，能耗目标达成"
            energy_type = 'positive'
        else:
            energy_delta = (
                f"较基准仅节能 {energy_saving:.1f}%，未达 30% 目标"
            )
            energy_type = 'warning'
    else:
        energy_delta = "双沙盒计算中"
        energy_type = 'positive'

    status_card(
        "MPC 累计电耗",
        f"{session_state['total_energy']:.3f} kWh",
        energy_delta,
        energy_type,
    )

    st.markdown("<div class='status-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def render_history_charts(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染历史曲线。

    图表保持和历史列名绑定，状态写入模块只要保持列名不变，
    页面展示就不需要知道物理模型内部细节。
    """

    history = session_state["history"]

    st.subheader("运行趋势")
    if history.empty:
        st.info("暂无数据，请开启模拟。")
        return

    chart_df = history.tail(60).copy().set_index("累计时间(分钟)")

    st.markdown("**1. 温度与舒适区演化 (°C)**")
    temp_df = chart_df[["室内温度", "室外温度", "目标温度", "基准室内温度"]].copy()
    if (
        temp_df["基准室内温度"].sub(temp_df["室内温度"]).abs().max()
        < 0.25
    ):
        temp_df = temp_df.drop(columns=["基准室内温度"])
    st.line_chart(temp_df)

    st.markdown("**2. CO₂ 与空气质量阈值 (ppm)**")
    chart_df["CO₂目标线"] = float(config.co2_target)
    chart_df["CO₂警戒线"] = float(config.co2_warning)
    st.line_chart(chart_df[["CO2浓度", "CO₂目标线", "CO₂警戒线"]])

    with st.expander("更多趋势（隐藏以提升滚动流畅度）", expanded=False):
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
    st.subheader("控制决策")

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

    summary_text = (
        f"AI 正在评估 {min(len(decision['pool']), 5)} 种方案，已选择最优："
        f"{best.ac_mode} {best.ac_level}，新风 {best.fresh_level}，"
        f"窗户 {best.window_ratio * 100:.0f}%。"
    )
    st.success(summary_text)
    st.markdown(
        f"**当前执行动作**：{best.ac_mode} / {best.ac_level}；"
        f"新风 {best.fresh_level}；窗户 {best.window_ratio * 100:.0f}%。"
    )
    st.info(
        f"预测 {config.prediction_horizon} 分钟后：{evaluation['pred_temp']:.2f}°C / "
        f"{evaluation['pred_co2']:.0f} ppm"
    )

    if session_state["override_reason"]:
        st.warning(f"硬约束覆盖：{session_state['override_reason']}")

    if config.outdoor_temp > config.t_max + 2.0 and best.window_ratio > 0.0:
        st.warning(
            f"室外温度 {config.outdoor_temp:.1f}°C 高于舒适区，"
            f"当前窗户开度为 {best.window_ratio * 100:.0f}%。"
        )

    st.markdown("**实时热量收支**")
    heat_metrics = [
        ("人员显热", result.people_heat_kw),
        ("围护结构传热", result.envelope_heat_kw),
        ("通风显热", result.ventilation_heat_kw),
        ("空调制冷", -result.ac_cooling_kw),
        ("空调制热", result.ac_heating_kw),
        ("净热负荷", result.net_heat_kw),
    ]
    for label, value in heat_metrics:
        bar_color = "#E85D5D" if value >= 0 else "#5D8AE8"
        progress = min(max(abs(value) / 12.0, 0.04), 1.0)
        st.markdown(
            f"<div style='margin-bottom:0.85rem;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"color:#e2e8f0;font-size:0.95rem;margin-bottom:0.30rem;'>"
            f"<span>{label}</span><span>{value:+.2f} kW</span></div>"
            f"<div style='background:#111827;border-radius:999px;height:14px;overflow:hidden;'>"
            f"<div style='width:{progress * 100:.0f}%;background:{bar_color};height:14px;"
            f"border-radius:999px;box-shadow:0 0 12px {bar_color};'></div>"
            f"</div></div>"
            , unsafe_allow_html=True)

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

    st.markdown("**实时功率分拆**")
    power_metrics = [
        ("空调系统", result.ac_electric_kw, "#5D8AE8"),
        ("新风机组", result.fresh_electric_kw, "#38BDF8"),
        ("控制器与传感器", result.base_electric_kw, "#64748B"),
        ("系统总功率", result.total_electric_kw, "#FACC15"),
    ]
    total_power = max(result.total_electric_kw, 1.0)
    for label, value, color in power_metrics:
        progress = min(max(value / total_power, 0.04), 1.0)
        st.markdown(
            f"<div style='margin-bottom:0.85rem;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"color:#e2e8f0;font-size:0.95rem;margin-bottom:0.30rem;'>"
            f"<span>{label}</span><span>{value:.2f} kW</span></div>"
            f"<div style='background:#111827;border-radius:999px;height:14px;overflow:hidden;'>"
            f"<div style='width:{progress * 100:.0f}%;background:{color};height:14px;"
            f"border-radius:999px;box-shadow:0 0 12px {color};'></div>"
            f"</div></div>"
            , unsafe_allow_html=True)

    st.markdown(
        f"AI 正在评估 {min(len(decision['pool']), 5)} 种方案，已选择最优：{best.ac_mode} {best.ac_level}，"
        f"新风 {best.fresh_level}，窗户 {best.window_ratio * 100:.0f}%。"
    )


def render_inactive_prompt() -> None:
    st.markdown(
        """
        <div class='inactive-prompt'>
            <div class='inactive-prompt-title'>未激活实时推演</div>
            <div class='inactive-prompt-text'>
                点击上方开关开始实时推演，系统将自动展示温度、CO₂、工况和能耗趋势。<br>
                若暂不启用，页面会保留当前模型设置，不会自动修改参数。
            </div>
            <div class='pulse-arrow'>⌄</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_analysis_area(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染图表与决策解释的双栏区域。"""

    st.markdown("---")
    if not session_state.get("running", False) and session_state["history"].empty:
        render_inactive_prompt()

    chart_tab, decision_tab = st.tabs(["运行趋势", "控制决策"])

    with chart_tab:
        render_history_charts(session_state, config)

    with decision_tab:
        render_decision_panel(session_state, config)


def render_comparison(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """渲染 MPC 与固定定时开空调基准的综合绩效表。"""

    history = session_state["history"]
    compliance = session_state.get("compliance_metrics")
    if compliance is None:
        compliance = calculate_compliance_metrics(history, config)

    st.markdown("---")
    with st.expander("MPC 与固定定时开空调基准比较", expanded=False):
        st.subheader("MPC 与固定定时开空调基准比较")

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
                "固定定时开空调（8:00-18:00全开，不管有没有人）": [
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

        energy_saving = (
            (session_state["benchmark_energy"] - session_state["total_energy"])
            / max(session_state["benchmark_energy"], 1e-6)
            * 100.0
        )
        comfort_gain = compliance["mpc_temp"] - compliance["bench_temp"]
        summary_lines = []
        if energy_saving >= 30.0:
            summary_lines.append("能耗节省 ≥ 30%")
        else:
            summary_lines.append("能耗节省 < 30%，建议优化策略")
        if comfort_gain >= 20.0:
            summary_lines.append("温度舒适度提升 ≥ 20%")
        else:
            summary_lines.append("温度舒适度提升 < 20%，需进一步优化")

        st.info(
            f"MPC 对比基准：{energy_saving:.1f}% 节能；"
            f"温度舒适率提升 {comfort_gain:.1f} 个百分点。"
        )
        if energy_saving >= 30.0 and comfort_gain >= 20.0:
            st.success("MPC 已达到能耗与舒适度双重目标。")
        else:
            st.warning("当前 MPC 结果未同时满足 30% 能耗节省与 20% 舒适度提升。")


def render_logs_and_export(session_state: MutableMapping[str, Any]) -> None:
    """渲染运行日志和 CSV 导出按钮。"""

    history = session_state["history"]

    st.markdown("---")
    with st.expander("系统运行日志与导出", expanded=False):
        st.subheader("系统运行日志")

        display_logs = session_state["logs"][:20]
        if display_logs:
            st.code("\n".join(display_logs), language=None)

        if history.empty:
            return

        csv_data = history.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="导出完整仿真数据 CSV",
            data=csv_data,
            file_name="smart_classroom_digital_twin_v5.csv",
            mime="text/csv",
        )

