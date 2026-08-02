"""智能教室环境控制模拟器入口。

`app.py` 现在只负责串联 Streamlit 页面生命周期：

1. 配置页面；
2. 读取侧边栏参数；
3. 初始化或重置仿真状态；
4. 渲染页面；
5. 在运行状态下推进一分钟并触发下一次刷新。

物理模型、控制策略、状态更新和 UI 组件都已拆到 `smart_classroom`
子模块中，后续维护时可以按职责定位代码。
"""

from __future__ import annotations

import time

import streamlit as st

from smart_classroom.sidebar import render_sidebar
from smart_classroom.state import (
    ensure_simulation_state,
    reset_simulation,
    update_physics_and_control,
)
from smart_classroom.views import (
    configure_page,
    render_analysis_area,
    render_comparison,
    render_intro,
    render_logs_and_export,
    render_runtime_summary,
    render_status_cards,
)


SPEED_MAP = {
    "慢": 1.5,
    "中": 0.7,
    "快": 0.15,
}


def main() -> None:
    """运行 Streamlit 应用。

    Streamlit 会在每次交互后从头执行本函数，因此所有需要跨刷新保存的
    数据都必须存入 `st.session_state`，不能依赖普通局部变量。
    """

    configure_page()
    render_intro()

    config, sim_speed, performance_mode, reset_requested = render_sidebar()
    ensure_simulation_state(st.session_state, config)

    if reset_requested:
        reset_simulation(st.session_state, config)
        st.session_state["_refresh_tick"] = 0
        st.rerun()

    st.session_state.running = st.toggle(
        "激活 MPC 实时推演",
        value=st.session_state.running,
    )

    # 开启后先补一行初始结果，避免图表区域空白。
    if st.session_state.running and st.session_state.history.empty:
        update_physics_and_control(st.session_state, config)

    render_runtime_summary(st.session_state, config)
    render_status_cards(st.session_state, config)
    render_analysis_area(st.session_state, config, performance_mode)
    render_comparison(st.session_state, config)
    render_logs_and_export(st.session_state)

    # Streamlit 没有传统后台循环；这里通过 sleep + rerun 模拟实时推进。
    if st.session_state.running:
        refresh_tick = int(st.session_state.get("_refresh_tick", 0)) + 1
        st.session_state["_refresh_tick"] = refresh_tick

        update_every = 2 if performance_mode == "性能优先" else 1
        if refresh_tick % update_every == 0:
            update_physics_and_control(st.session_state, config)

        sleep_seconds = SPEED_MAP[sim_speed] * (
            2.0 if performance_mode == "性能优先" else 1.0
        )
        time.sleep(sleep_seconds)
        st.rerun()


if __name__ == "__main__":
    main()
