import streamlit as st
import pandas as pd
import io

# ==================== 网页基础设置 ====================
# 设置网页为宽屏模式，更适合看大表格
st.set_page_config(page_title="TK 店铺数据处理工具", layout="wide")

st.title("📊 TK 店铺数据智能筛选工具")
st.markdown("---")

# ==================== 数据清洗函数 ====================
def clean_currency(x):
    if isinstance(x, str):
        return float(x.replace('.', '').replace('₫', '').replace(',', '').strip())
    return float(x)

def clean_percent(x):
    if isinstance(x, str) and '%' in x:
        return float(x.strip('%'))
    return pd.to_numeric(x, errors='coerce')

# ==================== 顶部：上传与参数筛选区 ====================
st.header("1. 上传与设置条件")

# 文件上传
uploaded_file = st.file_uploader("请上传 TK 店铺导出的表格 (.xlsx 或 .csv)", type=['xlsx', 'csv'])

if uploaded_file is not None:
    try:
        # 核心修复：强制把 'ID' 列作为纯文本（字符串）读取，防止变成科学计数法
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, skiprows=2, dtype={'ID': str})
        else:
            df = pd.read_excel(uploaded_file, skiprows=2, dtype={'ID': str})
            
        # 自动清洗数据格式
        for col in df.columns:
            if 'GMV' in col:
                df[col] = df[col].apply(clean_currency)
            elif '率' in col:
                df[col] = df[col].apply(clean_percent)
            elif df[col].dtype == 'object' and col not in ['ID', '商品', '状态']:
                df[col] = pd.to_numeric(df[col], errors='ignore')
                
        # 筛选条件选择
        st.subheader("添加筛选条件")
        selected_columns = st.multiselect(
            "请选择你需要用来筛选的表头（可多选）:", 
            options=df.columns.tolist()
        )
        
        # 动态生成筛选输入框 (带联动锁定功能)
        filters = {}
        if selected_columns:
            for col in selected_columns:
                st.markdown(f"**🔹 {col}**") 
                
                # 如果是数字类型的列
                if df[col].dtype in ['float64', 'int64']:
                    # 将一行分成三列，并排显示三个输入框
                    col1, col2, col3 = st.columns(3)
                    
                    # 确定步长：百分比类每次加减0.1，其他每次加减1
                    step_val = 0.1 if "率" in col else 1.0
                    
                    with col1:
                        # value=None 表示输入框初始为空
                        eq_val = st.number_input(f"等于 ({col})", value=None, step=step_val, key=f"eq_{col}")
                    
                    # 核心逻辑：如果“等于”框里有值（不是None），就锁定另外两个框
                    is_locked = (eq_val is not None)
                    
                    with col2:
                        min_val = st.number_input(f"最小值 大于等于 ({col})", value=None, step=step_val, disabled=is_locked, key=f"min_{col}")
                    with col3:
                        max_val = st.number_input(f"最大值 小于等于 ({col})", value=None, step=step_val, disabled=is_locked, key=f"max_{col}")
                    
                    filters[col] = ('numeric', eq_val, min_val, max_val)
                    
                else:
                    # 文本类（如状态 Active/Inactive），依旧用下拉多选框
                    unique_vals = df[col].dropna().unique().tolist()
                    selected_vals = st.multiselect(f"选择 {col} 状态", unique_vals, default=unique_vals, key=f"cat_{col}")
                    filters[col] = ('categorical', selected_vals)

        # ==================== 执行筛选逻辑 ====================
        filtered_df = df.copy()
        for col, condition in filters.items():
            if condition[0] == 'numeric':
                eq_val, min_val, max_val = condition[1], condition[2], condition[3]
                
                if eq_val is not None:
                    # 如果填了“等于”，只匹配等于这个值的行
                    filtered_df = filtered_df[filtered_df[col] == eq_val]
                else:
                    # 如果没填“等于”，则判断是否填了最大最小值
                    if min_val is not None:
                        filtered_df = filtered_df[filtered_df[col] >= min_val]
                    if max_val is not None:
                        filtered_df = filtered_df[filtered_df[col] <= max_val]
                        
            elif condition[0] == 'categorical':
                filtered_df = filtered_df[filtered_df[col].isin(condition[1])]

        st.markdown("---")
        
        # ==================== 底部：结果展示与导出区 ====================
        st.header("2. 筛选结果")
        st.success(f"🎉 筛选完毕！原始数据 {len(df)} 条，当前符合条件的有 **{len(filtered_df)}** 条。")
        
        # 实时看结果
        st.dataframe(filtered_df, use_container_width=True)
        
        # ==================== 导出功能 (Excel 生成核心) ====================
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            filtered_df.to_excel(writer, index=False, sheet_name='筛选结果')
            
        st.download_button(
            label="📥 下载筛选后的表格 (Excel)",
            data=excel_buffer.getvalue(),
            file_name="TK_筛选结果.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"读取或处理文件时出错，请确认表格格式是否正确。错误信息: {e}")