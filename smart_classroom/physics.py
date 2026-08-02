"""智能教室的一分钟物理模型。

这里不做任何“控制决策”，只回答一个问题：
在当前温度、CO₂ 浓度和设备动作给定时，下一分钟会发生什么。
"""

from __future__ import annotations

import streamlit as st

from .models import Action, DeviceLevel, FreshLevel, PhysicalResult, SimulationConfig


# 空气和设备的基础参数集中放在这里，便于后续校准。
AIR_DENSITY = 1.20                 # kg/m³
AIR_CP = 1.005                     # kJ/(kg·K)
OUTDOOR_CO2 = 420.0                # ppm
BASE_ACH = 0.20                    # 建筑自然渗透换气
BASE_ELECTRIC_KW = 0.010           # 控制器与传感器功耗
AC_COP = 3.0                       # 空调能效比


AC_EXCHANGE_KW: dict[DeviceLevel, float] = {
    "无": 0.0,
    "低": 2.5,
    "中": 5.5,
    "高": 8.5,
}
AC_LEVEL_SCORE: dict[DeviceLevel, int] = {
    "无": 0,
    "低": 1,
    "中": 2,
    "高": 3,
}


# 机械新风使用“换气率 + 电功率”两套参数。
FRESH_ACH: dict[FreshLevel, float] = {
    "关闭": 0.0,
    "低": 2.5,
    "中": 4.5,
    "高": 6.5,
}
FRESH_POWER_KW: dict[FreshLevel, float] = {
    "关闭": 0.00,
    "低": 0.15,
    "中": 0.30,
    "高": 0.50,
}
FRESH_LEVEL_SCORE: dict[FreshLevel, int] = {
    "关闭": 0,
    "低": 1,
    "中": 2,
    "高": 3,
}


@st.cache_data
def build_config(
    *,
    outdoor_temp: float,
    init_temp: float,
    init_co2: float,
    classroom_people: int,
    classroom_area: int,
    classroom_height: float,
    window_openable: bool,
    target_temp: float,
    comfort_band: float,
    co2_target: int,
    co2_warning: int,
    thermal_mass_factor: float,
    wall_u_factor: float,
    person_sensible_heat_kw: float,
    co2_generation_m3h_per_person: float,
    prediction_horizon: int,
    discount_factor: float,
) -> SimulationConfig:
    """根据侧边栏输入生成完整的仿真配置。

    派生量在这里统一计算，避免多个模块各算一遍产生不一致。
    """

    classroom_volume = classroom_area * classroom_height
    max_window_area = classroom_area * 0.15
    heat_capacity_kwh_per_k = (
        classroom_volume
        * AIR_DENSITY
        * AIR_CP
        * thermal_mass_factor
        / 3600.0
    )
    wall_heat_coeff_kw_per_k = wall_u_factor * classroom_area

    return SimulationConfig(
        outdoor_temp=outdoor_temp,
        init_temp=init_temp,
        init_co2=init_co2,
        classroom_people=classroom_people,
        classroom_area=classroom_area,
        classroom_height=classroom_height,
        window_openable=window_openable,
        target_temp=target_temp,
        comfort_band=comfort_band,
        co2_target=co2_target,
        co2_warning=co2_warning,
        thermal_mass_factor=thermal_mass_factor,
        wall_u_factor=wall_u_factor,
        person_sensible_heat_kw=person_sensible_heat_kw,
        co2_generation_m3h_per_person=co2_generation_m3h_per_person,
        prediction_horizon=prediction_horizon,
        discount_factor=discount_factor,
        classroom_volume=classroom_volume,
        max_window_area=max_window_area,
        heat_capacity_kwh_per_k=heat_capacity_kwh_per_k,
        wall_heat_coeff_kw_per_k=wall_heat_coeff_kw_per_k,
        t_min=target_temp - comfort_band,
        t_max=target_temp + comfort_band,
    )


@st.cache_data
def calculate_ach(action: Action, config: SimulationConfig) -> float:
    """计算总换气率 ACH。

    总换气率 = 建筑自然渗透 + 开窗带来的自然通风 + 机械新风。
    这里把窗户开度线性映射到 0~6 ACH，适合做教学模拟；真实项目中
    还需要根据风压、温差、窗型和开口高度进一步校准。
    """

    window_ach = action.window_ratio * 6.0
    return BASE_ACH + window_ach + FRESH_ACH[action.fresh_level]


@st.cache_data
def simulate_one_minute(
    temp: float,
    co2: float,
    action: Action,
    config: SimulationConfig,
) -> PhysicalResult:
    """对给定状态和动作执行 1 分钟物理仿真。

    热平衡采用简化的一阶模型：

    Q_net = 人员显热 + 围护结构传热 + 通风显热 - 制冷量 + 制热量

    当室外温度高于室内时，围护结构和通风项为正，代表向室内加热；
    当室外温度低于室内时，这些项为负，代表帮助散热。
    """

    ach = calculate_ach(action, config)
    ventilation_flow_m3h = ach * config.classroom_volume
    window_area_m2 = action.window_ratio * config.max_window_area

    # CO₂ 使用质量守恒：人员产生源项，通风把室内浓度拉向室外浓度。
    co2_source_ppm_per_hour = (
        config.classroom_people
        * config.co2_generation_m3h_per_person
        * 1_000_000.0
        / config.classroom_volume
    )
    co2_removal_ppm_per_hour = ach * (co2 - OUTDOOR_CO2)
    next_co2 = max(
        OUTDOOR_CO2,
        co2
        + (
            co2_source_ppm_per_hour
            - co2_removal_ppm_per_hour
        )
        * config.dt_hours,
    )

    people_heat_kw = config.classroom_people * config.person_sensible_heat_kw
    envelope_heat_kw = config.wall_heat_coeff_kw_per_k * (
        config.outdoor_temp - temp
    )

    # m³/h -> kg/s 后乘以空气定压比热，得到 kW/K 的显热换热系数。
    ventilation_heat_coeff_kw_per_k = (
        AIR_DENSITY * AIR_CP * ventilation_flow_m3h / 3600.0
    )
    ventilation_heat_kw = ventilation_heat_coeff_kw_per_k * (
        config.outdoor_temp - temp
    )

    ac_exchange_kw = (
        AC_EXCHANGE_KW[action.ac_level]
        if action.ac_mode != "关闭"
        else 0.0
    )
    ac_cooling_kw = ac_exchange_kw if action.ac_mode == "制冷" else 0.0
    ac_heating_kw = ac_exchange_kw if action.ac_mode == "制热" else 0.0

    net_heat_kw = (
        people_heat_kw
        + envelope_heat_kw
        + ventilation_heat_kw
        - ac_cooling_kw
        + ac_heating_kw
    )
    temp_change_c_per_min = (
        net_heat_kw / config.heat_capacity_kwh_per_k
    ) * config.dt_hours
    next_temp = temp + temp_change_c_per_min

    # 电功率只统计设备消耗，不把热量交换量直接当成电功率。
    ac_electric_kw = (
        ac_exchange_kw / AC_COP
        if action.ac_mode != "关闭"
        else 0.0
    )
    fresh_electric_kw = FRESH_POWER_KW[action.fresh_level]
    total_electric_kw = (
        ac_electric_kw + fresh_electric_kw + BASE_ELECTRIC_KW
    )

    return PhysicalResult(
        next_temp=next_temp,
        next_co2=next_co2,
        ach=ach,
        ventilation_flow_m3h=ventilation_flow_m3h,
        window_area_m2=window_area_m2,
        ac_cooling_kw=ac_cooling_kw,
        ac_heating_kw=ac_heating_kw,
        ac_electric_kw=ac_electric_kw,
        fresh_electric_kw=fresh_electric_kw,
        base_electric_kw=BASE_ELECTRIC_KW,
        total_electric_kw=total_electric_kw,
        people_heat_kw=people_heat_kw,
        envelope_heat_kw=envelope_heat_kw,
        ventilation_heat_kw=ventilation_heat_kw,
        net_heat_kw=net_heat_kw,
        temp_change_c_per_min=temp_change_c_per_min,
    )

