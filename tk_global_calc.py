import streamlit as st
import pandas as pd
import io
import math
import requests

# ==================== 网页基础设置 ====================
st.set_page_config(page_title="TK 卖家全能工具箱 4.0", layout="wide", page_icon="🚀")

# ==================== 实时汇率抓取引擎 ====================
@st.cache_data(ttl=43200) # 缓存12小时，防止API频繁调用被封IP
def get_realtime_rates():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/CNY"
        response = requests.get(url, timeout=5)
        data = response.json()
        return data['rates']
    except Exception as e:
        return None

live_rates = get_realtime_rates()

# ==================== 国家费率与物流底表配置 ====================
COUNTRY_CONFIG = {
    "泰国 (THB)": {
        "rate": live_rates['THB'] if live_rates else 4.85, 
        "comm": 5.56, "trans": 3.21, "srv": 4.63, "tax": 13.46, "sym": "฿", 
        "base_w": 50, "base_p": 10.0, "add_w": 10, "add_p": 1.0
    },
    "越南 (VND)": {
        "rate": live_rates['VND'] if live_rates else 3450.0, 
        "comm": 6.87, "trans": 5.0, "srv": 3.0, "tax": 8.0, "sym": "₫", 
        "base_w": 10, "base_p": 10900.0, "add_w": 10, "add_p": 900.0
    },
    "菲律宾 (PHP)": {
        "rate": live_rates['PHP'] if live_rates else 7.85, 
        "comm": 5.60, "trans": 2.24, "srv": 11.5, "tax": 0.0, "sym": "₱", 
        "base_w": 10, "base_p": 10.50, "add_w": 10, "add_p": 4.50
    },
    "马来西亚 (MYR)": {
        "rate": live_rates['MYR'] if live_rates else 0.65, 
        "comm": 11.32, "trans": 3.78, "srv": 0.0, "tax": 10.0, "sym": "RM", 
        "base_w": 10, "base_p": 0.15, "add_w": 10, "add_p": 0.15
    }
}

# ==================== 跨境运费计算函数 ====================
def calc_shipping(weight_g, cfg):
    if weight_g <= cfg['base_w']:
        return cfg['base_p']
    else:
        extra_units = math.ceil((weight_g - cfg['base_w']) / cfg['add_w'])
        return cfg['base_p'] + extra_units * cfg['add_p']

# ==================== 侧边栏导航 ====================
st.sidebar.title("🛠️ TK 卖家工具箱")
app_mode = st.sidebar.radio("选择使用的工具", [
    "💰 1. 利润反推 (精准运费版)", 
    "🎯 2. 正向定价 (精准运费版)",
    "📊 3. 店铺数据筛选 (智能表格)",
    "💱 4. 全球实时汇率换算"
])

# 仅在核算利润和定价时，显示国家选择和汇率微调
if app_mode in ["💰 1. 利润反推 (精准运费版)", "🎯 2. 正向定价 (精准运费版)"]:
    st.sidebar.divider()
    target_country = st.sidebar.selectbox("🌍 选择当前核算国家", list(COUNTRY_CONFIG.keys()))
    config = COUNTRY_CONFIG[target_country]
    
    if live_rates:
        st.sidebar.success("✅ 实时汇率已更新")
    else:
        st.sidebar.warning("⚠️ 网络异常，当前使用系统默认保底汇率")
        
    curr_rate = st.sidebar.number_input(f"自定义汇率 (1 CNY = ? {config['sym']})", value=float(config['rate']), format="%.4f")


# ==========================================
# 模块 1：利润反推 (精准运费版)
# ==========================================
if app_mode == "💰 1. 利润反推 (精准运费版)":
    st.title("💰 竞品售价反推利润模拟器")
    
    st.subheader("📦 1. 成本与规格")
    row1_col1, row1_col2, row1_col3 = st.columns(3)
    with row1_col1:
        cny_cost = st.number_input("产品拿货成本 (CNY)", value=30.0, step=1.0)
    with row1_col2:
        weight_g = st.number_input("包裹实际重量 (克/g)", value=100.0, step=10.0)
    with row1_col3:
        other_fixed_cny = st.number_input("打包耗材等杂费 (CNY)", value=2.0, step=0.5)

    ship_local = calc_shipping(weight_g, config)
    ship_cny = ship_local / curr_rate if curr_rate > 0 else 0
    st.info(f"🚚 根据官方底表，该重量预估跨境运费为: **{ship_local:,.2f} {config['sym']}** (折合 ¥ {ship_cny:,.2f})")

    st.divider()
    st.subheader("💵 2. 定价与佣金")
    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        pricing_mode = st.radio("👉 选择对手售价输入模式", ["按外币输入", "按人民币逆推"], horizontal=True)
        if pricing_mode == "按外币输入":
            default_local = 180000.0 if "VND" in target_country else 200.0
            local_price = st.number_input(f"竞品前台售价 ({config['sym']})", value=default_local, step=10.0)
        else:
            cny_target_price = st.number_input("相当于人民币售价 (CNY)", value=50.0, step=1.0)
            local_price = cny_target_price * curr_rate
            st.success(f"🔄 折合当地售价: **{local_price:,.2f} {config['sym']}**")
    with row2_col2:
        affiliate_p = st.number_input("达人带货佣金比例 (%)", value=0.0, step=1.0)

    total_percent_rate = (config['comm'] + config['trans'] + config['srv'] + config['tax'] + affiliate_p + 1.0) / 100
    total_fixed_local = ship_local + (other_fixed_cny * curr_rate)
    total_fees_local = local_price * total_percent_rate + total_fixed_local
    
    total_fees_cny = total_fees_local / curr_rate if curr_rate > 0 else 0
    net_profit_cny = (local_price / curr_rate) - cny_cost - total_fees_cny if curr_rate > 0 else 0
    profit_margin = (net_profit_cny / (local_price / curr_rate)) * 100 if local_price > 0 else 0

    st.divider()
    res1, res2, res3 = st.columns(3)
    res1.metric("单均净利润 (CNY)", f"¥ {net_profit_cny:,.2f}")
    res2.metric("实际净利率", f"{profit_margin:.2f} %")
    res3.metric("平台及物流总扣费 (CNY)", f"¥ {total_fees_cny:,.2f}")

    st.subheader("📝 资金流向明细拆解")
    if curr_rate > 0:
        breakdown = {
            "明细项": ["产品成本", "官方跨境运费", "打包耗材杂费", "平台佣金", "交易手续费", "营销/活动费", "税金", "达人佣金", "提现手续费(1%)", "最终净利润"],
            "金额 (CNY)": [
                round(cny_cost, 2), round(ship_cny, 2), round(other_fixed_cny, 2),
                round((local_price * config['comm']/100) / curr_rate, 2),
                round((local_price * config['trans']/100) / curr_rate, 2),
                round((local_price * config['srv']/100) / curr_rate, 2),
                round((local_price * config['tax']/100) / curr_rate, 2),
                round((local_price * affiliate_p/100) / curr_rate, 2),
                round((local_price * 0.01) / curr_rate, 2), round(net_profit_cny, 2)
            ]
        }
        st.table(breakdown)

# ==========================================
# 模块 2：正向定价 (精准运费版)
# ==========================================
elif app_mode == "🎯 2. 正向定价 (精准运费版)":
    st.title("🎯 商品上架正向定价计算器")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        cost = st.number_input("1. 产品拿货成本 (CNY)", value=30.0, step=1.0)
        weight_g = st.number_input("2. 包裹实际重量 (克/g)", value=100.0, step=10.0)
        other_fixed_cny = st.number_input("3. 打包耗材等杂费 (CNY)", value=2.0, step=0.5)
    with col2:
        target_margin = st.number_input("4. 目标净利润率 (%)", value=25.0, step=1.0)
        discount = st.number_input("5. 前台拟设折扣 (如 5折 填 5)", value=5.0, step=0.5)
    with col3:
        affiliate = st.number_input("6. 计划给达人的佣金 (%)", value=0.0, step=1.0)
        
    st.info(f"**当前国家 ({target_country}) 平台费率预设：** 佣金 {config['comm']}% | 手续费 {config['trans']}% | 服务费 {config['srv']}% | 税金 {config['tax']}%")
    
    ship_local = calc_shipping(weight_g, config)
    ship_cny = ship_local / curr_rate if curr_rate > 0 else 0
    total_fixed_cost_cny = other_fixed_cny + ship_cny
    
    total_fee_percent = (config['comm'] + config['trans'] + config['srv'] + config['tax'] + affiliate + 1.0) / 100
    denominator = 1 - (target_margin / 100) - total_fee_percent
    
    st.divider()
    if denominator <= 0:
        st.error("🚨 警告：目标利润率与平台抽成加起来已超过 100%，定价公式崩溃！")
    else:
        req_price_cny = (cost + total_fixed_cost_cny) / denominator
        req_price_local = req_price_cny * curr_rate
        original_price_local = req_price_local / (discount / 10)
        net_profit_cny = req_price_cny * (target_margin / 100)
        
        st.subheader("✅ 最终 ERP / 后台填报建议数据")
        r1, r2, r3 = st.columns(3)
        r1.metric(f"ERP 前台划线原价", f"{original_price_local:,.2f} {config['sym']}")
        r2.metric(f"买家实际支付折后价", f"{req_price_local:,.2f} {config['sym']}")
        r3.metric(f"你这单将稳赚净利", f"¥ {net_profit_cny:,.2f}")
        
        st.caption(f"*(提示：当前折后售价中已自动包含预估 {ship_local:,.2f} {config['sym']} 的官方运费)*")

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

# ==========================================
# 模块 4：全球实时汇率换算器 (新增)
# ==========================================
elif app_mode == "💱 4. 全球实时汇率换算":
    st.title("💱 全球实时汇率换算引擎")
    st.markdown("对接全球金融 API，支持 **150+ 种货币** 任意双向盲转。数据每 12 小时自动更新。")

    if not live_rates:
        st.error("🚨 无法获取实时汇率，请检查服务器网络连接或 API 接口状态！")
    else:
        # 定义跨境电商高频使用的“置顶货币”
        top_currencies = {
            "CNY - 人民币 (中国)": "CNY",
            "USD - 美元 (美国)": "USD",
            "THB - 泰铢 (泰国)": "THB",
            "VND - 越南盾 (越南)": "VND",
            "PHP - 比索 (菲律宾)": "PHP",
            "MYR - 林吉特 (马来)": "MYR",
            "SGD - 新加坡元 (新加坡)": "SGD",
            "IDR - 印尼盾 (印尼)": "IDR",
            "EUR - 欧元 (欧洲)": "EUR",
            "GBP - 英镑 (英国)": "GBP",
            "JPY - 日元 (日本)": "JPY"
        }
        
        # 整理下拉列表：高频货币放最上面，其余的放下面
        all_codes = list(live_rates.keys())
        currency_map = top_currencies.copy()
        
        for code in all_codes:
            if code not in currency_map.values():
                currency_map[f"{code}"] = code
                
        currency_options = list(currency_map.keys())

        st.divider()
        
        # 布局：左边输入，中间箭头，右边目标
        col1, col2, col3 = st.columns([2, 1, 2])
        
        with col1:
            from_curr_label = st.selectbox("1. 我持有 (From)", currency_options, index=0) # 默认选中 CNY
            amount = st.number_input("输入换算金额", value=100.0, step=10.0, format="%.2f")
            
        with col2:
            st.markdown("<h1 style='text-align: center; margin-top: 25px;'>🔄</h1>", unsafe_allow_html=True)
            
        with col3:
            to_curr_label = st.selectbox("2. 兑换为 (To)", currency_options, index=2) # 默认选中 THB
            
        # 提取真实的三字母代码
        from_code = currency_map[from_curr_label]
        to_code = currency_map[to_curr_label]
        
        # 计算逻辑：因为 API 是以 CNY 为基准 (1 CNY = x 外币)
        # 步骤 1：把输入的货币先折算回人民币基准
        if from_code == "CNY":
            amount_in_cny = amount
        else:
            amount_in_cny = amount / live_rates[from_code]
            
        # 步骤 2：把人民币转换为目标货币
        result = amount_in_cny * live_rates[to_code]
        
        st.divider()
        
        # 巨幕显示换算结果
        st.markdown(f"""
        <div style='text-align: center; padding: 20px; background-color: #f0f2f6; border-radius: 10px; color: #31333F;'>
            <h3>换算结果</h3>
            <h1 style='color: #FF4B4B;'>{amount:,.2f} {from_code} = {result:,.4f} {to_code}</h1>
        </div>
        """, unsafe_allow_html=True)
        
        # 显示实时汇率参考牌价
        st.caption(f"**实时汇率参考：** 1 {from_code} = {(live_rates[to_code]/live_rates[from_code]):.6f} {to_code} &nbsp;&nbsp;|&nbsp;&nbsp; 1 {to_code} = {(live_rates[from_code]/live_rates[to_code]):.6f} {from_code}")
