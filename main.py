def main():
    print("Hello from myapp!")
    # app.py
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Streamlit Demo",
    page_icon="🚀",
    layout="wide",
)

st.title("🚀")
st.write("通过 Python 快速构建交互式 Web 页面。")

name = st.text_input("请输入姓名")
score = st.slider("请选择分数", 0, 100, 80)

if st.button("生成结果"):
    st.success(f"{name or '用户'} 的分数是 {score}")

chart_data = pd.DataFrame({
    "阶段": ["需求", "原型", "测试", "发布"],
    "进度": [100, 80, 50, 20],
})
st.bar_chart(chart_data.set_index("阶段"))