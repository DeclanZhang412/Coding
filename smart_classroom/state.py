"""Streamlit 会话状态管理。

页面每次刷新都会重新执行脚本，因此仿真状态必须放在
`st.session_state` 中。本模块把状态初始化、参数变化重置、单步推进
集中管理，避免 UI 代码直接操作大量状态字段。
"""

from __future__ import annotations

from typing import Any, MutableMapping

import pandas as pd

from .control import (
    choose_benchmark_action,
    choose_mpc_action,
    evaluate_action,
)
from .models import SimulationConfig
from .physics import simulate_one_minute


HISTORY_COLUMNS = [
    "时间步",
    "累计时间(分钟)",
    "室内温度",
    "室外温度",
    "目标温度",
    "舒适区上限",
    "舒适区下限",
    "CO2浓度",
    "空调状态",
    "风速",
    "新风档位",
    "空调功率",
    "新风功率",
    "总功率",
    "窗户开启比例",
    "有效开口面积",
    "换气率ACH",
    "通风量m3h",
    "累计能耗",
    "单步能耗",
    "人员热负荷",
    "围护结构热负荷",
    "通风热负荷",
    "空调制冷量",
    "净热负荷",
    "温变速率",
    "基准室内温度",
    "基准CO2浓度",
    "基准累计能耗",
    "节能比例",
]


def reset_simulation(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """将 MPC 与 Benchmark 两套沙盒同时重置。"""

    session_state["history"] = pd.DataFrame(columns=HISTORY_COLUMNS)
    session_state["current_step"] = 0

    # MPC 沙盒状态。
    session_state["current_temp"] = float(config.init_temp)
    session_state["current_co2"] = float(config.init_co2)
    session_state["total_energy"] = 0.0

    # 传统基准沙盒状态。两套沙盒必须独立推进，不能共享温度/CO₂。
    session_state["bench_temp"] = float(config.init_temp)
    session_state["bench_co2"] = float(config.init_co2)
    session_state["benchmark_energy"] = 0.0

    session_state["running"] = False
    session_state["logs"] = [
        (
            "数字孪生系统 v5.0 初始化："
            f"体积 {config.classroom_volume:.1f} m³，"
            f"有效热容 {config.heat_capacity_kwh_per_k:.2f} kWh/K，"
            f"预测时界 {config.prediction_horizon} 分钟。"
        )
    ]
    session_state["last_decision_pool"] = {}
    session_state["last_result"] = None
    session_state["last_benchmark_result"] = None
    session_state["override_reason"] = ""
    session_state["scenario_signature"] = config.scenario_signature


def ensure_simulation_state(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """确保会话状态存在，并在场景变化时自动重置。"""

    if "history" not in session_state:
        reset_simulation(session_state, config)
        return

    if session_state.get("scenario_signature") != config.scenario_signature:
        reset_simulation(session_state, config)


def update_physics_and_control(
    session_state: MutableMapping[str, Any],
    config: SimulationConfig,
) -> None:
    """完成一次 MPC 决策、双沙盒仿真和状态持久化。"""

    step = session_state["current_step"] + 1

    best_action, pool, override_reason = choose_mpc_action(
        session_state["current_temp"],
        session_state["current_co2"],
        config,
    )
    mpc_result = simulate_one_minute(
        session_state["current_temp"],
        session_state["current_co2"],
        best_action,
        config,
    )

    benchmark_action = choose_benchmark_action(
        session_state["bench_temp"],
        session_state["bench_co2"],
        config,
        session_state["current_step"],
    )
    benchmark_result = simulate_one_minute(
        session_state["bench_temp"],
        session_state["bench_co2"],
        benchmark_action,
        config,
    )

    step_energy = mpc_result.total_electric_kw * config.dt_hours
    next_total_energy = session_state["total_energy"] + step_energy

    benchmark_step_energy = (
        benchmark_result.total_electric_kw * config.dt_hours
    )
    next_benchmark_energy = (
        session_state["benchmark_energy"] + benchmark_step_energy
    )

    energy_saved = (
        (next_benchmark_energy - next_total_energy)
        / next_benchmark_energy
        * 100.0
        if next_benchmark_energy > 0
        else 0.0
    )

    # 日志与右侧面板展示的是“真正执行动作”的预测结果。
    executed_evaluation = evaluate_action(
        session_state["current_temp"],
        session_state["current_co2"],
        best_action,
        config,
    )

    session_state["current_step"] = step
    session_state["current_temp"] = mpc_result.next_temp
    session_state["current_co2"] = mpc_result.next_co2
    session_state["total_energy"] = next_total_energy

    session_state["bench_temp"] = benchmark_result.next_temp
    session_state["bench_co2"] = benchmark_result.next_co2
    session_state["benchmark_energy"] = next_benchmark_energy

    session_state["last_result"] = mpc_result
    session_state["last_benchmark_result"] = benchmark_result
    session_state["override_reason"] = override_reason
    session_state["last_decision_pool"] = {
        "pool": pool,
        "best": best_action,
        "evaluation": executed_evaluation,
    }

    new_row: dict[str, object] = {
        "时间步": step,
        "累计时间(分钟)": step,
        "室内温度": round(mpc_result.next_temp, 3),
        "室外温度": config.outdoor_temp,
        "目标温度": config.target_temp,
        "舒适区上限": config.t_max,
        "舒适区下限": config.t_min,
        "CO2浓度": round(mpc_result.next_co2, 1),
        "空调状态": best_action.ac_mode,
        "风速": best_action.ac_level,
        "新风档位": best_action.fresh_level,
        "空调功率": round(mpc_result.ac_electric_kw, 3),
        "新风功率": round(mpc_result.fresh_electric_kw, 3),
        "总功率": round(mpc_result.total_electric_kw, 3),
        "窗户开启比例": round(best_action.window_ratio * 100.0, 1),
        "有效开口面积": round(mpc_result.window_area_m2, 2),
        "换气率ACH": round(mpc_result.ach, 2),
        "通风量m3h": round(mpc_result.ventilation_flow_m3h, 1),
        "累计能耗": round(next_total_energy, 4),
        "单步能耗": round(step_energy, 5),
        "人员热负荷": round(mpc_result.people_heat_kw, 3),
        "围护结构热负荷": round(mpc_result.envelope_heat_kw, 3),
        "通风热负荷": round(mpc_result.ventilation_heat_kw, 3),
        "空调制冷量": round(mpc_result.ac_cooling_kw, 3),
        "净热负荷": round(mpc_result.net_heat_kw, 3),
        "温变速率": round(mpc_result.temp_change_c_per_min, 4),
        "基准室内温度": round(benchmark_result.next_temp, 3),
        "基准CO2浓度": round(benchmark_result.next_co2, 1),
        "基准累计能耗": round(next_benchmark_energy, 4),
        "节能比例": round(energy_saved, 1),
    }

    new_row_df = pd.DataFrame([new_row])
    if session_state["history"].empty:
        session_state["history"] = new_row_df
    else:
        session_state["history"] = pd.concat(
            [
                session_state["history"],
                new_row_df,
            ],
            ignore_index=True,
        )

    action_log = (
        f"空调[{best_action.ac_mode}/{best_action.ac_level}]，"
        f"窗户[{best_action.window_ratio * 100:.0f}%]，"
        f"新风[{best_action.fresh_level}]"
    )
    override_text = f"；安全覆盖：{override_reason}" if override_reason else ""

    session_state["logs"].insert(
        0,
        (
            f"[第 {step} 分钟] 执行 {action_log}；"
            f"{config.prediction_horizon} 分钟预测终态："
            f"{executed_evaluation['pred_temp']:.2f}°C / "
            f"{executed_evaluation['pred_co2']:.0f} ppm"
            f"{override_text}"
        ),
    )
    session_state["logs"] = session_state["logs"][:200]

