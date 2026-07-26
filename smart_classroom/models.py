"""数据结构与类型定义。

本模块只描述“数据长什么样”，不包含具体控制策略或 UI 渲染。
这样做的好处是：物理模型、控制器、页面展示都能共享同一套类型，
后续扩展字段时不容易出现名字不一致的问题。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


AcMode = Literal["关闭", "制冷", "制热"]
DeviceLevel = Literal["无", "低", "中", "高"]
FreshLevel = Literal["关闭", "低", "中", "高"]


@dataclass(frozen=True)
class Action:
    """控制器单步动作。

    每个动作代表下一分钟要执行的设备组合。MPC 会枚举这些动作，
    再通过预测模型选择综合代价最低的一项。
    """

    ac_mode: AcMode
    ac_level: DeviceLevel
    window_ratio: float
    fresh_level: FreshLevel


@dataclass(frozen=True)
class SimulationConfig:
    """一次仿真场景的完整配置。

    前半部分来自侧边栏输入，后半部分是由输入推导出来的物理量。
    使用不可变 dataclass 可以避免某个函数悄悄改掉全局参数，
    让每一步仿真的来源更清楚。
    """

    outdoor_temp: float
    init_temp: float
    init_co2: float
    classroom_people: int
    classroom_area: int
    classroom_height: float
    window_openable: bool

    target_temp: float
    comfort_band: float
    co2_target: int
    co2_warning: int

    thermal_mass_factor: float
    wall_u_factor: float
    person_sensible_heat_kw: float
    co2_generation_m3h_per_person: float

    prediction_horizon: int
    discount_factor: float

    classroom_volume: float
    max_window_area: float
    heat_capacity_kwh_per_k: float
    wall_heat_coeff_kw_per_k: float
    t_min: float
    t_max: float
    dt_hours: float = 1.0 / 60.0
    compliance_temp_tolerance_c: float = 0.1

    @property
    def scenario_signature(self) -> tuple[object, ...]:
        """用于判断“场景参数是否发生变化”的签名。

        Streamlit 每次交互都会重跑脚本。如果用户改变面积、人数、
        目标温度等关键参数，旧历史数据已经不属于同一个物理场景，
        必须自动重置，避免图表和累计能耗混在一起。
        """

        return (
            self.outdoor_temp,
            self.init_temp,
            self.init_co2,
            self.classroom_people,
            self.classroom_area,
            self.classroom_height,
            self.window_openable,
            self.target_temp,
            self.comfort_band,
            self.co2_target,
            self.co2_warning,
            self.thermal_mass_factor,
            self.wall_u_factor,
            self.person_sensible_heat_kw,
            self.co2_generation_m3h_per_person,
            self.prediction_horizon,
            self.discount_factor,
        )


@dataclass
class PhysicalResult:
    """物理模型单步计算结果。

    字段既包含下一步状态，也包含可解释的中间量。页面右侧的热量收支
    和功率分拆面板直接使用这些中间量，便于检查控制动作是否合理。
    """

    next_temp: float
    next_co2: float
    ach: float
    ventilation_flow_m3h: float
    window_area_m2: float

    ac_cooling_kw: float
    ac_heating_kw: float
    ac_electric_kw: float
    fresh_electric_kw: float
    base_electric_kw: float
    total_electric_kw: float

    people_heat_kw: float
    envelope_heat_kw: float
    ventilation_heat_kw: float
    net_heat_kw: float
    temp_change_c_per_min: float


class ActionEvaluation(TypedDict):
    """MPC 单个候选动作的预测评估结果。"""

    cost: float
    pred_temp: float
    pred_co2: float
    temp_violation_minutes: int
    co2_violation_minutes: int


class DecisionCandidate(ActionEvaluation):
    """候选动作与它对应的预测结果。"""

    action: Action


class DecisionState(TypedDict):
    """最近一次 MPC 决策的 UI 展示数据。"""

    pool: list[DecisionCandidate]
    best: Action
    evaluation: ActionEvaluation


class ComplianceMetrics(TypedDict):
    """MPC 与传统基准的环境质量统计指标。"""

    mpc_temp: float
    mpc_co2: float
    mpc_co2_safe: float
    bench_temp: float
    bench_co2: float
    bench_co2_safe: float

