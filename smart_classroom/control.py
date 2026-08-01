"""控制器与绩效统计。

本模块包含两套控制器：

1. MPC 近似控制器：枚举候选动作，预测未来代价并选最优；
2. 传统基准控制器：使用简单阈值规则，作为对照沙盒。
"""

from __future__ import annotations

import pandas as pd

from .models import (
    Action,
    ActionEvaluation,
    ComplianceMetrics,
    DecisionCandidate,
    FreshLevel,
    SimulationConfig,
)
from .physics import (
    AC_LEVEL_SCORE,
    FRESH_ACH,
    FRESH_LEVEL_SCORE,
    simulate_one_minute,
)


FRESH_LEVELS: tuple[FreshLevel, ...] = ("关闭", "低", "中", "高")


def build_candidate_actions(config: SimulationConfig) -> list[Action]:
    """构造 MPC 的候选动作空间。

    动作空间既要覆盖常见设备组合，也不能太大，否则 Streamlit 每次
    自动刷新都会变慢。这里保留了“关闭、制冷、制热、分级新风、
    少量开窗”的核心组合。
    """

    actions: list[Action] = []

    for fresh in FRESH_LEVELS:
        actions.append(Action("关闭", "无", 0.0, fresh))

    if config.window_openable:
        actions.extend(
            [
                Action("关闭", "无", 0.2, "关闭"),
                Action("关闭", "无", 0.2, "低"),
                Action("关闭", "无", 0.5, "关闭"),
                Action("关闭", "无", 1.0, "关闭"),
            ]
        )

    for level in ("低", "中", "高"):
        for fresh in FRESH_LEVELS:
            actions.append(Action("制冷", level, 0.0, fresh))
        if config.window_openable:
            actions.append(Action("制冷", level, 0.2, "关闭"))

    for level in ("低", "中", "高"):
        actions.append(Action("制热", level, 0.0, "关闭"))
        actions.append(Action("制热", level, 0.0, "低"))

    return actions


def temperature_violation(temp: float, config: SimulationConfig) -> float:
    """返回温度偏离舒适区的绝对值。"""

    if temp > config.t_max:
        return temp - config.t_max
    if temp < config.t_min:
        return config.t_min - temp
    return 0.0


def co2_cost(co2: float, config: SimulationConfig) -> float:
    """分级 CO₂ 惩罚。

    CO₂ 控制采用“目标线 + 警戒线”的语义：
    目标线附近允许轻微波动，超过警戒线后快速增加惩罚。
    """

    if co2 <= config.co2_target:
        return 0.0
    if co2 <= config.co2_warning:
        normalized = (
            (co2 - config.co2_target)
            / max(1.0, config.co2_warning - config.co2_target)
        )
        return normalized ** 2

    severe = (co2 - config.co2_warning) / 100.0
    return 3.0 + severe ** 2


def action_constraint_penalty(
    action: Action,
    config: SimulationConfig,
) -> float:
    """计算工程约束惩罚。

    这些惩罚不是物理定律，而是工程常识：例如空调制冷时大开窗会造成
    显著能量浪费，在候选动作排序时应被强烈压低。
    """

    penalty = 0.0

    if action.ac_mode != "关闭" and action.window_ratio > 0.0:
        penalty += 18.0 * action.window_ratio

    if config.outdoor_temp > config.t_max + 2.0 and action.window_ratio > 0.2:
        penalty += (
            (config.outdoor_temp - config.t_max)
            * action.window_ratio
            * 12.0
        )

    if config.outdoor_temp < config.t_min - 2.0 and action.window_ratio > 0.2:
        penalty += (
            (config.t_min - config.outdoor_temp)
            * action.window_ratio
            * 12.0
        )

    return penalty


def equipment_stage_penalty(action: Action) -> float:
    """对高档位设备施加轻量惩罚。

    当两个候选动作都能满足环境约束时，低档位动作更节能、噪声更小、
    设备磨损也更低，因此应获得更低代价。
    """

    return (
        0.35 * AC_LEVEL_SCORE[action.ac_level]
        + 0.25 * FRESH_LEVEL_SCORE[action.fresh_level]
    )


def ventilation_thermal_penalty(
    action: Action,
    result,
    pred_co2: float,
    config: SimulationConfig,
) -> float:
    """惩罚“空调与过量新风互相抵消”的动作。

    高温室外制冷时大量新风会把热量带进教室；低温室外制热时大量新风
    会把冷量带进教室。CO₂ 未达到警戒值时，不应为了追求更低 CO₂
    而过度牺牲热舒适和能耗。
    """

    if pred_co2 >= config.co2_warning:
        return 0.0

    outdoor_violation = temperature_violation(config.outdoor_temp, config)
    if outdoor_violation <= 0.0:
        return 0.0

    fresh_score = FRESH_LEVEL_SCORE[action.fresh_level]
    if fresh_score == 0:
        return 0.0

    ventilation_heat_conflicts_with_ac = (
        action.ac_mode == "制冷"
        and result.ventilation_heat_kw > 0
    ) or (
        action.ac_mode == "制热"
        and result.ventilation_heat_kw < 0
    )
    penalty_factor = 0.75 if ventilation_heat_conflicts_with_ac else 0.25

    return penalty_factor * abs(result.ventilation_heat_kw) * fresh_score


def stronger_fresh_level(
    left: FreshLevel,
    right: FreshLevel,
) -> FreshLevel:
    """返回两个新风档位中更强的一档。"""

    return (
        left
        if FRESH_LEVEL_SCORE[left] >= FRESH_LEVEL_SCORE[right]
        else right
    )


def co2_required_fresh_level(
    co2: float,
    config: SimulationConfig,
) -> FreshLevel:
    """根据当前 CO₂ 水平给出安全所需的最低新风档位。"""

    if co2 >= config.co2_warning - 25.0:
        return "高"
    if co2 >= config.co2_warning - 100.0:
        return "中"
    if co2 >= config.co2_target:
        return "低"
    return "关闭"


def co2_safety_reason(co2: float, config: SimulationConfig) -> str:
    """生成 CO₂ 安全覆盖说明。"""

    if co2 >= config.co2_warning:
        return "CO₂ 达到警戒值，触发高档机械新风安全覆盖。"
    if co2 >= config.co2_warning - 25.0:
        return "CO₂ 接近警戒值，提前触发高档机械新风。"
    if co2 >= config.co2_warning - 100.0:
        return "CO₂ 接近警戒区间，提前触发中档机械新风。"
    if co2 >= config.co2_target:
        return "CO₂ 高于控制目标，保持低档新风缓慢稀释。"
    return ""


def action_with_required_fresh(
    action: Action,
    required_fresh: FreshLevel,
) -> Action:
    """在保留原动作的基础上提高新风档位。

    如果空调正在运行，强制关闭窗户，避免机械空调和开窗同时发生。
    """

    fresh_level = stronger_fresh_level(action.fresh_level, required_fresh)
    window_ratio = 0.0 if action.ac_mode != "关闭" else action.window_ratio

    return Action(
        action.ac_mode,
        action.ac_level,
        window_ratio,
        fresh_level,
    )


def prediction_fallback_action(
    temp: float,
    co2: float,
    config: SimulationConfig,
) -> Action:
    """预测时界内第 2 分钟及之后的后备动作。

    真正运行时，MPC 每分钟都会重新求解。因此评估某个“当前动作”时，
    不能把它机械地固定 30 分钟；这里用一套保守规则估计后续滚动求解
    大概率会做出的动作。
    """

    if config.classroom_people == 0:
        ac_mode = "关闭"
        ac_level = "无"
    elif temp > config.t_max + 0.8:
        ac_mode = "制冷"
        ac_level = "高"
    elif temp > config.t_max:
        ac_mode = "制冷"
        ac_level = "中"
    elif temp < config.t_min - 0.8:
        ac_mode = "制热"
        ac_level = "高"
    elif temp < config.t_min:
        ac_mode = "制热"
        ac_level = "中"
    else:
        ac_mode = "关闭"
        ac_level = "无"

    fresh_level = co2_required_fresh_level(co2, config)

    window_ratio = 0.0
    outdoor_comfortable = config.t_min <= config.outdoor_temp <= config.t_max
    if (
        config.window_openable
        and ac_mode == "关闭"
        and co2 > config.co2_target
        and outdoor_comfortable
    ):
        window_ratio = 0.5
        fresh_level = "关闭"

    return Action(ac_mode, ac_level, window_ratio, fresh_level)


def max_fresh_score_for_current_co2(
    co2: float,
    config: SimulationConfig,
) -> int:
    """限制第一步新风档位，避免 CO₂ 刚超目标就直接高档运行。"""

    co2_span = max(1.0, config.co2_warning - config.co2_target)

    if co2 < config.co2_target + 0.35 * co2_span:
        return FRESH_LEVEL_SCORE["低"]
    if co2 < config.co2_target + 0.75 * co2_span:
        return FRESH_LEVEL_SCORE["中"]
    return FRESH_LEVEL_SCORE["高"]


def evaluate_action(
    initial_temp: float,
    initial_co2: float,
    action: Action,
    config: SimulationConfig,
) -> ActionEvaluation:
    """评估当前候选动作在预测时界内的累计代价。"""

    pred_temp = initial_temp
    pred_co2 = initial_co2
    accumulated_cost = 0.0
    temp_violation_minutes = 0
    co2_violation_minutes = 0

    for minute in range(config.prediction_horizon):
        planned_action = (
            action
            if minute == 0
            else prediction_fallback_action(pred_temp, pred_co2, config)
        )
        result = simulate_one_minute(
            pred_temp,
            pred_co2,
            planned_action,
            config,
        )
        pred_temp = result.next_temp
        pred_co2 = result.next_co2

        t_violation = temperature_violation(pred_temp, config)
        c_cost = co2_cost(pred_co2, config)

        cost_temp = 30.0 * (t_violation ** 2)
        cost_air = 14.0 * c_cost
        cost_energy = 1.8 * result.total_electric_kw
        cost_stage = equipment_stage_penalty(planned_action)
        cost_ventilation_thermal = ventilation_thermal_penalty(
            planned_action,
            result,
            pred_co2,
            config,
        )

        severe_temp_penalty = 0.0
        if pred_temp >= 30.0:
            severe_temp_penalty += 120.0 * ((pred_temp - 30.0) ** 2 + 1.0)
        elif pred_temp <= 18.0:
            severe_temp_penalty += 120.0 * ((18.0 - pred_temp) ** 2 + 1.0)

        constraint_penalty = action_constraint_penalty(planned_action, config)
        discount = config.discount_factor ** minute

        accumulated_cost += discount * (
            cost_temp
            + cost_air
            + cost_energy
            + cost_stage
            + cost_ventilation_thermal
            + severe_temp_penalty
            + constraint_penalty
        )

        if t_violation > 0:
            temp_violation_minutes += 1
        if pred_co2 > config.co2_target:
            co2_violation_minutes += 1

    return {
        "cost": accumulated_cost,
        "pred_temp": pred_temp,
        "pred_co2": pred_co2,
        "temp_violation_minutes": temp_violation_minutes,
        "co2_violation_minutes": co2_violation_minutes,
    }


def apply_safety_override(
    temp: float,
    co2: float,
    selected: Action,
    config: SimulationConfig,
) -> tuple[Action, str]:
    """在 MPC 软优化之外增加硬约束。

    软优化可能因为能耗权重而延迟通风或空调动作；硬约束负责兜底，
    避免出现极端高温、低温或 CO₂ 越过警戒线仍不处理的情况。
    """

    required_fresh = co2_required_fresh_level(co2, config)
    co2_reason = co2_safety_reason(co2, config)

    if temp >= 30.0:
        action = Action(
            "制冷",
            "高",
            0.0,
            stronger_fresh_level("低", required_fresh),
        )
        return action, "室温达到 30°C 以上，触发强制高档制冷安全覆盖。"

    if temp > config.t_max + 1.0 and selected.ac_mode != "制冷":
        action = Action(
            "制冷",
            "中",
            0.0,
            stronger_fresh_level("关闭", required_fresh),
        )
        reason = "室温显著高于舒适区，触发最低中档制冷约束。"
        if co2_reason:
            reason += f"；{co2_reason}"
        return action, reason

    if temp <= 18.0:
        action = Action(
            "制热",
            "高",
            0.0,
            stronger_fresh_level("低", required_fresh),
        )
        reason = "室温达到 18°C 以下，触发强制高档制热安全覆盖。"
        if co2_reason:
            reason += f"；{co2_reason}"
        return action, reason

    if temp < config.t_min - 1.0 and selected.ac_mode != "制热":
        action = Action(
            "制热",
            "中",
            0.0,
            stronger_fresh_level("低", required_fresh),
        )
        reason = "室温显著低于舒适区，触发最低中档制热约束。"
        if co2_reason:
            reason += f"；{co2_reason}"
        return action, reason

    upgraded = action_with_required_fresh(selected, required_fresh)
    if upgraded != selected and co2_reason:
        return upgraded, co2_reason

    return selected, ""


def choose_mpc_action(
    temp: float,
    co2: float,
    config: SimulationConfig,
) -> tuple[Action, list[DecisionCandidate], str]:
    """遍历候选动作并选取预测时界累计代价最低者。"""

    pool: list[DecisionCandidate] = []

    for action in build_candidate_actions(config):
        if (
            FRESH_LEVEL_SCORE[action.fresh_level]
            > max_fresh_score_for_current_co2(co2, config)
        ):
            continue

        outdoor_extreme = (
            config.outdoor_temp > config.t_max + 2.0
            or config.outdoor_temp < config.t_min - 2.0
        )
        if (
            outdoor_extreme
            and action.ac_mode != "关闭"
            and action.window_ratio > 0.0
        ):
            continue

        if action.window_ratio > 0.2 and outdoor_extreme:
            continue

        evaluation = evaluate_action(temp, co2, action, config)
        candidate: DecisionCandidate = {
            "action": action,
            "cost": evaluation["cost"],
            "pred_temp": evaluation["pred_temp"],
            "pred_co2": evaluation["pred_co2"],
            "temp_violation_minutes": evaluation["temp_violation_minutes"],
            "co2_violation_minutes": evaluation["co2_violation_minutes"],
        }
        pool.append(candidate)

    if not pool:
        raise RuntimeError("没有可用的候选控制动作。")

    pool.sort(key=lambda item: item["cost"])
    selected = pool[0]["action"]
    final_action, override_reason = apply_safety_override(
        temp,
        co2,
        selected,
        config,
    )

    return final_action, pool, override_reason


def choose_benchmark_action(
    temp: float,
    co2: float,
    config: SimulationConfig,
    current_step: int,
) -> Action:
    """传统基准控制器。

    传统基准采用固定时段全开空调策略：模拟 8:00-18:00 全开空调，
    不考虑人数或智能优化；CO₂ 超目标时开窗作为简单安全策略。
    """

    minute_of_day = current_step % 1440
    within_schedule = 8 * 60 <= minute_of_day < 18 * 60

    if within_schedule:
        if temp >= config.target_temp:
            ac_mode = "制冷"
        else:
            ac_mode = "制热"
        ac_level = "高"
    else:
        ac_mode = "关闭"
        ac_level = "无"

    benchmark_window = (
        1.0
        if config.window_openable and co2 > config.co2_target
        else 0.0
    )

    return Action(
        ac_mode=ac_mode,
        ac_level=ac_level,
        window_ratio=benchmark_window,
        fresh_level="关闭",
    )


def calculate_compliance_metrics(
    history: pd.DataFrame,
    config: SimulationConfig,
) -> ComplianceMetrics:
    """计算 MPC 与基准系统的达标率。

    温度达标加入 0.1°C 传感器容差，避免 25.01°C 这类边界值被判为
    完全不舒适。CO₂ 同时统计“目标达标率”和“警戒安全率”。
    """

    if history.empty:
        return {
            "mpc_temp": 0.0,
            "mpc_co2": 0.0,
            "mpc_co2_safe": 0.0,
            "bench_temp": 0.0,
            "bench_co2": 0.0,
            "bench_co2_safe": 0.0,
        }

    temp_lower = config.t_min - config.compliance_temp_tolerance_c
    temp_upper = config.t_max + config.compliance_temp_tolerance_c

    return {
        "mpc_temp": float(
            history["室内温度"].between(temp_lower, temp_upper).mean() * 100
        ),
        "mpc_co2": float((history["CO2浓度"] <= config.co2_target).mean() * 100),
        "mpc_co2_safe": float(
            (history["CO2浓度"] <= config.co2_warning).mean() * 100
        ),
        "bench_temp": float(
            history["基准室内温度"].between(temp_lower, temp_upper).mean() * 100
        ),
        "bench_co2": float(
            (history["基准CO2浓度"] <= config.co2_target).mean() * 100
        ),
        "bench_co2_safe": float(
            (history["基准CO2浓度"] <= config.co2_warning).mean() * 100
        ),
    }

