import streamlit as st
import pandas as pd
import io

# ==================== 网页基础设置 (全局只能出现一次) ====================
st.set_page_config(page_title="TK 卖家全能工具箱", layout="wide")

# --- 侧边栏导航与国家配置 ---
st.sidebar.title("🛠️ TK 卖家工具箱")
app_mode = st.sidebar.radio("选择使用的工具", [
    "💰 1. 利润反推 (查漏补缺)", 
    "🎯 2. 正向定价 (上架指导)",
    "📊 3. 店铺数据筛选 (智能表格)"
])

COUNTRY_CONFIG = {
    "泰国 (THB)": {"rate": 4.85, "comm": 5.56, "trans": 3.21, "srv": 4.63, "tax": 13.46, "fixed_cny": 2.06, "sym": "฿"},
    "越南 (VND)": {"rate": 3450, "comm": 6.87, "trans": 5.0, "srv": 3.0, "tax": 8.0, "fixed_cny": 5.0, "sym": "₫"},
    "菲律宾 (PHP)": {"rate": 7.85, "comm": 5.60, "trans": 2.24, "srv": 11.5, "tax": 0.0, "fixed_cny": 4.0, "sym": "₱"},
    "马来西亚 (MYR)": {"rate": 0.65, "comm": 11.32, "trans": 3.78, "srv": 0.0, "tax": 10.0, "fixed_cny": 2.6, "sym": "RM"}
}

# 只有当用户不在筛选工具时，才显示汇率和国家选择
if app_mode != "📊 3. 店铺数据筛选 (智能表格)":
    st.sidebar.divider()
    target_country = st.sidebar.selectbox("🌍 选择当前核算国家", list(COUNTRY_CONFIG.keys()))
    config = COUNTRY_CONFIG[target_country]
    curr_rate = st.sidebar.number_input(f"自定义汇率 (1 CNY = ? {config['sym']})", value=config['rate'], format="%.4f")


# ==========================================
# 模块 1：利润反推 (查漏补缺)
# ==========================================
if app_mode == "💰 1. 利润反推 (查漏补缺)":
    st.title("💰 竞品售价反推利润模拟器")
    
    col1, col2 = st.columns(2)
    with col1:
        cny_cost = st.number_input("产品拿货成本 (CNY)", value=30.0, step=1.0)
        pricing_mode = st.radio("👉 选择对手售价输入模式", ["按外币输入", "按人民币逆推"], horizontal=True)
        
        if pricing_mode == "按外币输入":
            default_local = 180000.0 if "VND" in target_country else 200.0
            local_price = st.number_input(f"竞品前台售价 ({config['sym']})", value=default_local, step=10.0)
        else:
            cny_target_price = st.number_input("相当于人民币售价 (CNY)", value=50.0, step=1.0)
            local_price = cny_target_price * curr_rate
            st.info(f"🔄 折合当地售价: **{local_price:,.2f} {config['sym']}**")
            
        affiliate_p = st.number_input("达人佣金比例 (%)", value=0.0, step=1.0)

    total_percent_rate = (config['comm'] + config['trans'] + config['srv'] + config['tax'] + affiliate_p + 1.0) / 100
    total_fees_local = local_price * total_percent_rate + (config['fixed_cny'] * curr_rate)
    total_fees_cny = total_fees_local / curr_rate if curr_rate > 0 else 0
    net_profit_cny = (local_price / curr_rate) - cny_cost - total_fees_cny if curr_rate > 0 else 0
    profit_margin = (net_profit_cny / (local_price / curr_rate)) * 100 if local_price > 0 else 0

    st.divider()
    res1, res2, res3 = st.columns(3)
    res1.metric("单均净利润 (CNY)", f"¥ {net_profit_cny:,.2f}")
    res2.metric("实际净利率", f"{profit_margin:.2f} %")
    res3.metric("平台总扣费 (CNY)", f"¥ {total_fees_cny:,.2f}")

# ==========================================
# 模块 2：正向定价 (上架指导)
# ==========================================
elif app_mode == "🎯 2. 正向定价 (上架指导)":
    st.title("🎯 商品上架正向定价计算器")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        cost = st.number_input("1. 产品成本 (CNY)", value=30.0, step=1.0)
        fixed_cost = st.number_input("2. 固定杂费/运费损耗 (CNY)", value=config['fixed_cny'], step=1.0)
    with col2:
        target_margin = st.number_input("3. 目标净利润率 (%)", value=25.0, step=1.0)
        discount = st.number_input("4. 前台拟设折扣 (例如 5折 填 5)", value=5.0, step=0.5)
    with col3:
        affiliate = st.number_input("5. 计划给达人的佣金 (%)", value=0.0, step=1.0)
        
    st.info(f"**当前国家 ({target_country}) 平台固定费率预设：** 佣金 {config['comm']}% | 手续费 {config['trans']}% | 服务费 {config['srv']}% | 税金 {config['tax']}%")
    
    total_fee_percent = (config['comm'] + config['trans'] + config['srv'] + config['tax'] + affiliate + 1.0) / 100
    denominator = 1 - (target_margin / 100) - total_fee_percent
    
    st.divider()
    if denominator <= 0:
        st.error("🚨 警告：你的目标利润率与平台抽成加起来已经超过 100%，售价将无限大！请调低目标利润率或减少达人佣金。")
    else:
        req_price_cny = (cost + fixed_cost) / denominator
        req_price_local = req_price_cny * curr_rate
        original_price_local = req_price_local / (discount / 10)
        net_profit_cny = req_price_cny * (target_margin / 100)
        
        st.subheader("✅ 上架填报建议数据")
        r1, r2, r3 = st.columns(3)
        r1.metric(f"ERP 前台划线原价", f"{original_price_local:,.2f} {config['sym']}")
        r2.metric(f"买家实际支付折后价", f"{req_price_local:,.2f} {config['sym']}")
        r3.metric(f"你这单将稳赚净利", f"¥ {net_profit_cny:,.2f}")

# ==========================================
# 模块 3：店铺数据筛选 (智能表格)
# ==========================================
elif app_mode == "📊 3. 店铺数据筛选 (智能表格)":
    st.title("📊 TK 店铺数据智能筛选工具")
    st.markdown("---")

    def clean_currency(x):
        if isinstance(x, str):
            return float(x.replace('.', '').replace('₫', '').replace(',', '').strip())
        return float(x)

    def clean_percent(x):
        if isinstance(x, str) and '%' in x:
            return float(x.strip('%'))
        return pd.to_numeric(x, errors='coerce')

    st.header("1. 上传与设置条件")
    uploaded_file = st.file_uploader("请上传 TK 店铺导出的表格 (.xlsx 或 .csv)", type=['xlsx', 'csv'])

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file, skiprows=2, dtype={'ID': str})
            else:
                df = pd.read_excel(uploaded_file, skiprows=2, dtype={'ID': str})
                
            for col in df.columns:
                if 'GMV' in col:
                    df[col] = df[col].apply(clean_currency)
                elif '率' in col:
                    df[col] = df[col].apply(clean_percent)
                elif df[col].dtype == 'object' and col not in ['ID', '商品', '状态']:
                    df[col] = pd.to_numeric(df[col], errors='ignore')
                    
            st.subheader("添加筛选条件")
            selected_columns = st.multiselect(
                "请选择你需要用来筛选的表头（可多选）:", 
                options=df.columns.tolist()
            )
            
            filters = {}
            if selected_columns:
                for col in selected_columns:
                    st.markdown(f"**🔹 {col}**") 
                    if df[col].dtype in ['float64', 'int64']:
                        col1, col2, col3 = st.columns(3)
                        step_val = 0.1 if "率" in col else 1.0
                        
                        with col1:
                            eq_val = st.number_input(f"等于 ({col})", value=None, step=step_val, key=f"eq_{col}")
                        
                        is_locked = (eq_val is not None)
                        
                        with col2:
                            min_val = st.number_input(f"最小值 大于等于 ({col})", value=None, step=step_val, disabled=is_locked, key=f"min_{col}")
                        with col3:
                            max_val = st.number_input(f"最大值 小于等于 ({col})", value=None, step=step_val, disabled=is_locked, key=f"max_{col}")
                        
                        filters[col] = ('numeric', eq_val, min_val, max_val)
                        
                    else:
                        unique_vals = df[col].dropna().unique().tolist()
                        selected_vals = st.multiselect(f"选择 {col} 状态", unique_vals, default=unique_vals, key=f"cat_{col}")
                        filters[col] = ('categorical', selected_vals)

            filtered_df = df.copy()
            for col, condition in filters.items():
                if condition[0] == 'numeric':
                    eq_val, min_val, max_val = condition[1], condition[2], condition[3]
                    if eq_val is not None:
                        filtered_df = filtered_df[filtered_df[col] == eq_val]
                    else:
                        if min_val is not None:
                            filtered_df = filtered_df[filtered_df[col] >= min_val]
                        if max_val is not None:
                            filtered_df = filtered_df[filtered_df[col] <= max_val]
                elif condition[0] == 'categorical':
                    filtered_df = filtered_df[filtered_df[col].isin(condition[1])]

            st.markdown("---")
            st.header("2. 筛选结果")
            st.success(f"🎉 筛选完毕！原始数据 {len(df)} 条，当前符合条件的有 **{len(filtered_df)}** 条。")
            st.dataframe(filtered_df, use_container_width=True)
            
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
