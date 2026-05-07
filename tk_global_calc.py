import streamlit as st
import pandas as pd
import io
import math
import requests
import numpy as np
import json

# ==================== 网页基础设置 ====================
st.set_page_config(page_title="TK 卖家全能工具箱 5.3", layout="wide", page_icon="🚀")

# ==================== 状态保持与重置 ====================
DEFAULTS = {
    "cny_cost": 30.0,
    "weight_g": 100.0,
    "other_fixed_cny": 2.0,
    "affiliate_p": 0.0,
    "target_margin": 25.0,
    "discount": 5.0,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==================== 通用清洗函数 ====================
def safe_float(x, default=0.0):
    if pd.isna(x):
        return default
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    s = str(x).strip()
    if s in ["", "--", "-", "nan", "None", "null"]:
        return default
    s = (
        s.replace("₫", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("฿", "")
        .replace("₱", "")
        .replace("RM", "")
        .replace(",", "")
        .replace(" ", "")
    )
    try:
        return float(s)
    except Exception:
        return default


def safe_percent(x, default=0.0):
    if pd.isna(x):
        return default
    if isinstance(x, (int, float, np.integer, np.floating)):
        val = float(x)
        # 有些表会把 6.23% 写成 0.0623，这里自动转成 6.23
        return val * 100 if 0 < val <= 1 else val
    s = str(x).strip().replace("%", "").replace(",", "")
    if s in ["", "--", "-", "nan", "None", "null"]:
        return default
    try:
        return float(s)
    except Exception:
        return default

# ==================== 实时汇率抓取引擎 ====================
@st.cache_data(ttl=43200)
def get_realtime_rates():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/CNY"
        response = requests.get(url, timeout=5)
        data = response.json()
        return data["rates"]
    except Exception:
        return None

live_rates = get_realtime_rates()

# ==================== 国家费率与物流底表配置 ====================
COUNTRY_CONFIG = {
    "泰国 (THB)": {
        "rate": live_rates["THB"] if live_rates else 4.85,
        "comm": 5.56,
        "trans": 3.21,
        "srv": 4.63,
        "tax": 13.46,
        "sym": "฿",
        "base_w": 50,
        "base_p": 10.0,
        "add_w": 10,
        "add_p": 1.0,
    },
    "越南 (VND)": {
        "rate": live_rates["VND"] if live_rates else 3450.0,
        "comm": 6.87,
        "trans": 5.0,
        "srv": 3.0,
        "tax": 8.0,
        "sym": "₫",
        "base_w": 10,
        "base_p": 10900.0,
        "add_w": 10,
        "add_p": 900.0,
    },
    "菲律宾 (PHP)": {
        "rate": live_rates["PHP"] if live_rates else 7.85,
        "comm": 5.60,
        "trans": 2.24,
        "srv": 11.5,
        "tax": 0.0,
        "sym": "₱",
        "base_w": 10,
        "base_p": 10.50,
        "add_w": 10,
        "add_p": 4.50,
    },
    "马来西亚 (MYR)": {
        "rate": live_rates["MYR"] if live_rates else 0.65,
        "comm": 11.32,
        "trans": 3.78,
        "srv": 0.0,
        "tax": 10.0,
        "sym": "RM",
        "base_w": 10,
        "base_p": 0.15,
        "add_w": 10,
        "add_p": 0.15,
    },
}

# ==================== 跨境运费计算函数 ====================
def calc_shipping(weight_g, cfg):
    if weight_g <= cfg["base_w"]:
        return cfg["base_p"]
    extra_units = math.ceil((weight_g - cfg["base_w"]) / cfg["add_w"])
    return cfg["base_p"] + extra_units * cfg["add_p"]

# ==================== 商品数据诊断：读取、清洗、规则 ====================
def find_tk_header_row(raw_df):
    keywords = ["商品 ID", "商品名称", "商品曝光次数", "去重商品点击次数", "GMV"]
    for idx in range(len(raw_df)):
        row_text = " ".join([str(x) for x in raw_df.iloc[idx].tolist()])
        hit_count = sum(1 for k in keywords if k in row_text)
        if hit_count >= 2:
            return idx
    return 0


def normalize_columns(df):
    df.columns = [str(c).strip().replace("\n", "") for c in df.columns]

    col_alias = {
        "商品 ID": "product_id",
        "商品ID": "product_id",
        "ID": "product_id",
        "商品名称": "product_name",
        "商品": "product_name",
        "商品曝光次数": "impressions",
        "获得的曝光次数": "earned_impressions",
        "去重商品曝光次数": "unique_impressions",
        "商品点击次数": "clicks",
        "去重商品点击次数": "clicks",
        "曝光到点击转化率": "ctr",
        "点击率": "ctr",
        "买家数": "buyers",
        "点击到成交转化率": "cvr",
        "成交转化率": "cvr",
        "成交件数": "orders",
        "订单数": "orders",
        "GMV (₫)": "gmv",
        "GMV": "gmv",
        "GMV(₫)": "gmv",
    }

    rename_dict = {}
    for col in df.columns:
        clean_col = str(col).strip()
        if clean_col in col_alias:
            rename_dict[col] = col_alias[clean_col]
        elif "GMV" in clean_col:
            rename_dict[col] = "gmv"
    return df.rename(columns=rename_dict)


def load_tk_product_table(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        raw_df = pd.read_csv(uploaded_file, header=None, dtype=str)
        header_row = find_tk_header_row(raw_df)
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, header=header_row, dtype=str)
    else:
        raw_df = pd.read_excel(uploaded_file, header=None, dtype=str)
        header_row = find_tk_header_row(raw_df)
        uploaded_file.seek(0)
        df = pd.read_excel(uploaded_file, header=header_row, dtype=str)

    df = df.dropna(how="all")
    df = normalize_columns(df)

    required = ["product_id", "product_name", "unique_impressions", "clicks", "buyers", "orders", "gmv"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"表格缺少必要字段：{missing}。请确认上传的是 TK 后台导出的商品数据表。")

    # 缺少百分比字段时自动补列
    if "ctr" not in df.columns:
        df["ctr"] = 0
    if "cvr" not in df.columns:
        df["cvr"] = 0
    if "impressions" not in df.columns:
        df["impressions"] = df["unique_impressions"]
    if "earned_impressions" not in df.columns:
        df["earned_impressions"] = 0

    # 统一数值字段
    for c in ["impressions", "earned_impressions", "unique_impressions", "clicks", "buyers", "orders", "gmv"]:
        df[c] = df[c].apply(safe_float)
    df["ctr"] = df["ctr"].apply(safe_percent)
    df["cvr"] = df["cvr"].apply(safe_percent)

    # 以后台字段为参考，同时重新计算，避免百分比字段为空或格式异常
    df["ctr"] = np.where(df["unique_impressions"] > 0, df["clicks"] / df["unique_impressions"] * 100, df["ctr"])
    df["cvr"] = np.where(df["clicks"] > 0, df["buyers"] / df["clicks"] * 100, df["cvr"])

    df["product_id"] = df["product_id"].astype(str).str.replace(".0", "", regex=False).str.strip()
    df["product_name"] = df["product_name"].astype(str).str.strip()

    # 去掉空商品名、汇总行
    df = df[(df["product_name"] != "") & (df["product_name"].str.lower() != "nan")]
    return df


def diagnose_product(row, high_impression_threshold=500, min_click_threshold=30):
    impressions = row["unique_impressions"]
    clicks = row["clicks"]
    ctr = row["ctr"]
    buyers = row["buyers"]
    cvr = row["cvr"]
    orders = row["orders"]
    gmv = row["gmv"]

    tags = []
    problems = []
    suggestions = []
    actions = []
    priority_score = 1

    if impressions >= high_impression_threshold and ctr < 2:
        tags.append("曝光高点击低")
        problems.append("平台已经给了曝光，但用户看到后点击意愿低，主图、标题、首图卖点或价格展示吸引力不足。")
        suggestions.append("优先重做主图和标题：主图突出使用场景、套装内容、适配型号和本地语言卖点；同时检查同款竞品到手价。")
        actions.append("换主图/改标题/查竞品价格")
        priority_score = max(priority_score, 3)

    if clicks >= min_click_threshold and buyers == 0:
        tags.append("点击高但无成交")
        problems.append("商品能吸引用户进入详情页，但没有成交，问题大概率在详情页、价格、优惠、评价或物流信任。")
        suggestions.append("先不要直接下架，优先优化详情页前 3 张图、设置首单券或限时折扣、补充实拍图/适配说明，并尝试破零评价。")
        actions.append("优化详情页/上券/破零评价")
        priority_score = max(priority_score, 3)

    if ctr >= 5 and clicks >= min_click_threshold and 0 < cvr < 2:
        tags.append("点击不错转化弱")
        problems.append("主图标题有吸引力，但成交承接偏弱，说明详情页说服力或价格竞争力不足。")
        suggestions.append("重点检查竞品券后价、运费、评价数量、详情页前几屏；可用小额优惠券和达人内容补成交。")
        actions.append("查价格/补优惠/做达人测试")
        priority_score = max(priority_score, 3)

    if ctr >= 5 and clicks >= 20 and buyers == 0:
        tags.append("强兴趣无转化")
        problems.append("用户兴趣明显，但商品没有完成成交闭环。")
        suggestions.append("优先处理价格和信任：价格靠近竞品中位价，增加优惠券、买家保障、发货时效说明和评价素材。")
        actions.append("降到手价/增强信任")
        priority_score = max(priority_score, 3)

    if cvr >= 5 and buyers >= 1 and impressions < high_impression_threshold:
        tags.append("转化好但曝光低")
        problems.append("商品已经有成交能力，但平台曝光不足。")
        suggestions.append("适合加推：做短视频、达人、商城活动或商品卡优化；保持价格和库存稳定，争取平台继续放量。")
        actions.append("加推短视频/达人/活动")
        priority_score = max(priority_score, 2)

    if buyers >= 2 and cvr >= 3:
        tags.append("有成交可放量")
        problems.append("商品已经验证有成交能力，可以作为重点款继续维护。")
        suggestions.append("稳定库存，减少频繁改价，报名活动，找达人测品，必要时小预算投流验证。")
        actions.append("重点维护/放量测试")
        priority_score = max(priority_score, 3 if gmv > 0 else 2)

    if impressions < 200 and clicks < 5 and buyers == 0:
        tags.append("低曝光低点击")
        problems.append("商品没有获得有效流量，也没有明显用户兴趣。")
        suggestions.append("低优先级观察；若是新品，先优化类目、关键词和首图；若上架较久，建议暂停投入或重新上架测试。")
        actions.append("低优先级观察/重上测试")

    if gmv > 0 and buyers >= 1:
        tags.append("已有GMV贡献")
        suggestions.append("加入每日监控池，持续观察曝光、点击率、转化率、库存和退款差评。")
        actions.append("加入重点监控")
        priority_score = max(priority_score, 2)

    if not tags:
        tags.append("正常观察")
        problems.append("当前数据暂未暴露明显问题，需要继续积累样本。")
        suggestions.append("继续观察 3-7 天，重点看曝光、点击率、买家数和 GMV 是否稳定。")
        actions.append("继续观察")

    priority = "高" if priority_score >= 3 else "中" if priority_score == 2 else "低"
    return pd.Series(
        {
            "处理优先级": priority,
            "问题标签": " / ".join(dict.fromkeys(tags)),
            "问题判断": "；".join(dict.fromkeys(problems)),
            "调整建议": "；".join(dict.fromkeys(suggestions)),
            "建议动作": " / ".join(dict.fromkeys(actions)),
        }
    )


def make_store_summary(result):
    total_products = len(result)
    total_impressions = result["unique_impressions"].sum()
    total_clicks = result["clicks"].sum()
    total_buyers = result["buyers"].sum()
    total_gmv = result["gmv"].sum()
    ctr = total_clicks / total_impressions * 100 if total_impressions > 0 else 0
    cvr = total_buyers / total_clicks * 100 if total_clicks > 0 else 0

    high_count = (result["处理优先级"] == "高").sum()
    click_no_order = ((result["clicks"] >= 30) & (result["buyers"] == 0)).sum()
    high_imp_low_ctr = ((result["unique_impressions"] >= 500) & (result["ctr"] < 2)).sum()
    scalable = ((result["buyers"] >= 2) & (result["cvr"] >= 3)).sum()

    lines = []
    lines.append(f"本期共分析 {total_products} 个商品，总曝光 {total_impressions:,.0f}，总点击 {total_clicks:,.0f}，整体点击率 {ctr:.2f}%，整体点击到成交转化率 {cvr:.2f}%，GMV {total_gmv:,.0f}。")
    if click_no_order > 0:
        lines.append(f"当前最明显的问题是“点击后不成交”：有 {click_no_order} 个商品点击达到 30 次以上但买家数为 0，建议优先检查价格、详情页、优惠券、评价和物流信任。")
    if high_imp_low_ctr > 0:
        lines.append(f"有 {high_imp_low_ctr} 个商品属于“曝光高点击低”，说明平台给了展示机会但用户不愿点击，建议优先换主图、优化标题和首图卖点。")
    if scalable > 0:
        lines.append(f"有 {scalable} 个商品已经具备成交能力，适合加入重点款池，稳定库存后通过达人、短视频、商城活动或小预算投流继续放量。")
    if high_count == 0:
        lines.append("本期暂无非常突出的高优先级问题商品，可以继续观察数据，重点维护已有成交商品。")
    return "\n\n".join(lines)



def compact_table_for_ai(df, columns, limit=15):
    """把 DataFrame 压缩成适合发送给 AI 的 JSON 文本，避免把整张大表传给模型。"""
    if df is None or len(df) == 0:
        return []
    available = [c for c in columns if c in df.columns]
    if not available:
        return []
    temp = df[available].head(limit).copy()
    for col in temp.columns:
        if pd.api.types.is_numeric_dtype(temp[col]):
            temp[col] = temp[col].round(2)
    return temp.to_dict(orient="records")


def build_ai_report_context(result=None, df28=None, zombie_df=None, trend_df=None, top_n=15):
    """生成 AI 运营报告所需的结构化摘要。"""
    context = {
        "说明": "这是 TikTok Shop 东南亚小店商品数据诊断结果，请基于数据生成运营报告，不要编造表格中没有的数据。",
        "近7天诊断": {},
        "近28天僵尸品": {},
        "趋势对比": {},
    }

    if result is not None and len(result) > 0:
        total_products = int(len(result))
        total_impressions = float(result["unique_impressions"].sum())
        total_clicks = float(result["clicks"].sum())
        total_buyers = float(result["buyers"].sum())
        total_orders = float(result["orders"].sum())
        total_gmv = float(result["gmv"].sum())
        avg_ctr = total_clicks / total_impressions * 100 if total_impressions > 0 else 0
        avg_cvr = total_buyers / total_clicks * 100 if total_clicks > 0 else 0

        context["近7天诊断"] = {
            "商品数": total_products,
            "总曝光": round(total_impressions, 2),
            "总点击": round(total_clicks, 2),
            "整体点击率%": round(avg_ctr, 2),
            "买家数": round(total_buyers, 2),
            "成交件数": round(total_orders, 2),
            "整体成交转化率%": round(avg_cvr, 2),
            "GMV": round(total_gmv, 2),
            "高优先级商品数": int((result["处理优先级"] == "高").sum()),
            "点击高但无成交商品数": int(((result["clicks"] >= 30) & (result["buyers"] == 0)).sum()),
            "曝光高点击低商品数": int(((result["unique_impressions"] >= 500) & (result["ctr"] < 2)).sum()),
            "有成交可放量商品数": int(((result["buyers"] >= 2) & (result["cvr"] >= 3)).sum()),
            "优先处理商品明细": compact_table_for_ai(
                result,
                [
                    "product_id", "product_name", "unique_impressions", "clicks", "ctr",
                    "buyers", "cvr", "orders", "gmv", "处理优先级", "问题标签", "建议动作", "调整建议"
                ],
                limit=top_n,
            ),
        }

    if df28 is not None and len(df28) > 0:
        context["近28天整体"] = {
            "商品数": int(len(df28)),
            "总曝光": round(float(df28["unique_impressions"].sum()), 2),
            "总点击": round(float(df28["clicks"].sum()), 2),
            "买家数": round(float(df28["buyers"].sum()), 2),
            "成交件数": round(float(df28["orders"].sum()), 2),
            "GMV": round(float(df28["gmv"].sum()), 2),
        }

    if zombie_df is not None:
        context["近28天僵尸品"] = {
            "疑似僵尸产品数": int(len(zombie_df)),
            "重度僵尸": int((zombie_df["僵尸等级"] == "重度僵尸").sum()) if len(zombie_df) else 0,
            "中度僵尸": int((zombie_df["僵尸等级"] == "中度僵尸").sum()) if len(zombie_df) else 0,
            "轻度僵尸": int((zombie_df["僵尸等级"] == "轻度僵尸").sum()) if len(zombie_df) else 0,
            "僵尸产品样例": compact_table_for_ai(
                zombie_df,
                ["商品ID", "商品名称", "28天曝光", "28天点击", "28天买家", "28天成交件数", "28天GMV", "僵尸等级", "僵尸原因", "处理建议"],
                limit=top_n,
            ),
        }

    if trend_df is not None and len(trend_df) > 0:
        trend_sorted_down = trend_df.sort_values(by="曝光趋势变化%", ascending=True).head(top_n)
        trend_sorted_up = trend_df.sort_values(by="曝光趋势变化%", ascending=False).head(top_n)
        context["趋势对比"] = {
            "近期下滑明显商品": compact_table_for_ai(
                trend_sorted_down,
                ["product_id", "product_name", "7天曝光", "28天曝光", "7天日均曝光", "28天日均曝光", "曝光趋势变化%", "趋势判断", "7天GMV", "28天GMV"],
                limit=top_n,
            ),
            "近期上升明显商品": compact_table_for_ai(
                trend_sorted_up,
                ["product_id", "product_name", "7天曝光", "28天曝光", "7天日均曝光", "28天日均曝光", "曝光趋势变化%", "趋势判断", "7天GMV", "28天GMV"],
                limit=top_n,
            ),
        }

    return json.dumps(context, ensure_ascii=False, indent=2)


def build_ai_report_prompt(report_context, report_style="标准运营报告"):
    return f"""
你是一名 TikTok Shop 东南亚跨境小店资深运营分析师。请基于下面的结构化商品数据诊断结果，生成一份中文运营报告。

写作要求：
1. 不要编造数据，只能使用输入中出现的数据和合理运营推断。
2. 重点判断：流量问题、点击问题、转化问题、僵尸品问题、可放量商品机会。
3. 输出要能直接给运营执行，避免空话。
4. 报告风格：{report_style}。
5. 请按以下结构输出：
   - 一、本期整体结论
   - 二、核心问题拆解
   - 三、优先处理商品/商品池
   - 四、僵尸产品处理建议
   - 五、未来 7 天执行计划
   - 六、需要持续监控的指标

数据如下：
{report_context}
""".strip()


def call_ai_report(provider, base_url, api_key, model, prompt, temperature=0.3, timeout=120):
    """调用 AI 节点生成报告。支持 DeepSeek API、Ollama 原生、OpenAI 兼容接口、Gemini API。"""
    provider = provider.strip()
    base_url = (base_url or "").strip().rstrip("/")
    api_key = (api_key or "").strip()
    model = (model or "").strip()

    if not model:
        raise ValueError("请填写模型名称。")

    if provider == "Ollama 原生接口":
        if not base_url:
            base_url = "http://127.0.0.1:11434"
        url = f"{base_url}/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": temperature},
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "").strip()

    if provider == "DeepSeek API":
        if not api_key:
            raise ValueError("DeepSeek API 需要填写 API Key。")
        if not base_url:
            base_url = "https://api.deepseek.com"
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是 TikTok Shop 东南亚跨境小店运营数据分析师。请只基于用户提供的数据摘要做运营诊断，不编造数据。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }
        # DeepSeek V4 系列支持 thinking 开关。运营报告默认关闭深度思考以节省成本和提速；
        # 如需更强推理，可在模型名称后添加 |thinking，例如 deepseek-v4-flash|thinking。
        if "|thinking" in model:
            payload["model"] = model.replace("|thinking", "")
            payload["thinking"] = {"type": "enabled"}
        elif model in ["deepseek-v4-flash", "deepseek-v4-pro"]:
            payload["thinking"] = {"type": "disabled"}
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"].get("content", "").strip()

    if provider == "OpenAI 兼容接口":
        if not base_url:
            base_url = "http://127.0.0.1:11434/v1"
        url = f"{base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    if provider == "Gemini API":
        if not api_key:
            raise ValueError("Gemini API 需要填写 API Key。")
        if not base_url:
            base_url = "https://generativelanguage.googleapis.com/v1beta"
        url = f"{base_url}/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return "AI 没有返回内容，请检查模型名称或 API Key。"
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join([p.get("text", "") for p in parts]).strip()

    raise ValueError("暂不支持的 AI 节点类型。")

def compare_periods(df_short, df_long, short_days=7, long_days=28):
    base_cols = ["product_id", "product_name", "unique_impressions", "clicks", "buyers", "orders", "gmv"]
    left = df_short[base_cols].copy().rename(
        columns={
            "unique_impressions": f"{short_days}天曝光",
            "clicks": f"{short_days}天点击",
            "buyers": f"{short_days}天买家",
            "orders": f"{short_days}天成交件数",
            "gmv": f"{short_days}天GMV",
        }
    )
    right = df_long[base_cols].copy().rename(
        columns={
            "product_name": f"{long_days}天商品名称",
            "unique_impressions": f"{long_days}天曝光",
            "clicks": f"{long_days}天点击",
            "buyers": f"{long_days}天买家",
            "orders": f"{long_days}天成交件数",
            "gmv": f"{long_days}天GMV",
        }
    )
    merged = pd.merge(left, right, on="product_id", how="left")
    merged[f"{short_days}天日均曝光"] = merged[f"{short_days}天曝光"] / short_days
    merged[f"{long_days}天日均曝光"] = merged[f"{long_days}天曝光"] / long_days
    merged["曝光趋势变化%"] = np.where(
        merged[f"{long_days}天日均曝光"] > 0,
        (merged[f"{short_days}天日均曝光"] / merged[f"{long_days}天日均曝光"] - 1) * 100,
        0,
    )
    merged["趋势判断"] = np.where(
        merged["曝光趋势变化%"] >= 30,
        "近期明显上升",
        np.where(merged["曝光趋势变化%"] <= -30, "近期明显下滑", "趋势相对稳定"),
    )
    return merged



def find_zombie_products(df28, max_impressions=100, max_clicks=3, max_buyers=0, max_orders=0, max_gmv=0.0):
    """
    僵尸产品筛选逻辑：用于近 28 天数据。
    默认规则偏保守：28 天曝光极低、点击极低、无买家、无成交、无 GMV。
    """
    z = df28.copy()
    z["28天曝光"] = z["unique_impressions"]
    z["28天点击"] = z["clicks"]
    z["28天买家"] = z["buyers"]
    z["28天成交件数"] = z["orders"]
    z["28天GMV"] = z["gmv"]
    z["28天日均曝光"] = z["28天曝光"] / 28
    z["28天日均点击"] = z["28天点击"] / 28

    cond = (
        (z["28天曝光"] <= max_impressions)
        & (z["28天点击"] <= max_clicks)
        & (z["28天买家"] <= max_buyers)
        & (z["28天成交件数"] <= max_orders)
        & (z["28天GMV"] <= max_gmv)
    )
    z = z[cond].copy()

    def zombie_level(row):
        if row["28天曝光"] <= 30 and row["28天点击"] == 0:
            return "重度僵尸"
        if row["28天曝光"] <= 60 and row["28天点击"] <= 1:
            return "中度僵尸"
        return "轻度僵尸"

    def zombie_reason(row):
        reasons = []
        if row["28天曝光"] <= max_impressions:
            reasons.append(f"28天曝光仅 {row['28天曝光']:.0f}")
        if row["28天点击"] <= max_clicks:
            reasons.append(f"28天点击仅 {row['28天点击']:.0f}")
        if row["28天买家"] <= 0:
            reasons.append("无买家")
        if row["28天成交件数"] <= 0:
            reasons.append("无成交")
        if row["28天GMV"] <= 0:
            reasons.append("无GMV")
        return "；".join(reasons)

    def zombie_action(row):
        level = row["僵尸等级"]
        if level == "重度僵尸":
            return "建议优先下架或重新上架测试；重新做标题关键词、主图、类目和价格，不建议继续占用精力。"
        if level == "中度僵尸":
            return "建议进入待优化池：先检查是否放错类目、关键词弱、主图无卖点；优化后观察 7 天，仍无曝光则下架。"
        return "建议低优先级观察：可先小幅优化标题/主图/价格，若下一周期仍无增长再下架或合并到组合款。"

    if len(z) == 0:
        z["僵尸等级"] = []
        z["僵尸原因"] = []
        z["处理建议"] = []
    else:
        z["僵尸等级"] = z.apply(zombie_level, axis=1)
        z["僵尸原因"] = z.apply(zombie_reason, axis=1)
        z["处理建议"] = z.apply(zombie_action, axis=1)

    level_order = {"重度僵尸": 3, "中度僵尸": 2, "轻度僵尸": 1}
    z["僵尸排序"] = z["僵尸等级"].map(level_order).fillna(0)
    z = z.sort_values(by=["僵尸排序", "28天曝光", "28天点击"], ascending=[False, True, True])
    show_cols = [
        "product_id",
        "product_name",
        "28天曝光",
        "28天日均曝光",
        "28天点击",
        "28天日均点击",
        "28天买家",
        "28天成交件数",
        "28天GMV",
        "僵尸等级",
        "僵尸原因",
        "处理建议",
    ]
    return z[show_cols].rename(
        columns={
            "product_id": "商品ID",
            "product_name": "商品名称",
        }
    )

def to_excel_bytes(sheets: dict):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()

# ==================== 侧边栏导航 ====================
st.sidebar.title("🛠️ TK 卖家工具箱")
app_mode = st.sidebar.radio(
    "选择使用的工具",
    [
        "💰 1. 利润反推 (精准运费版)",
        "🎯 2. 正向定价 (精准运费版)",
        "📊 3. 店铺数据筛选 (智能表格)",
        "🔎 4. 商品数据诊断 (7天/28天)",
        "💱 5. 全球实时汇率换算",
    ],
)

st.sidebar.divider()
if st.sidebar.button("🔄 一键恢复默认数值", use_container_width=True):
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    st.rerun()

if app_mode in ["💰 1. 利润反推 (精准运费版)", "🎯 2. 正向定价 (精准运费版)"]:
    st.sidebar.divider()
    target_country = st.sidebar.selectbox("🌍 选择当前核算国家", list(COUNTRY_CONFIG.keys()))
    config = COUNTRY_CONFIG[target_country]

    if live_rates:
        st.sidebar.success("✅ 实时汇率已更新")
    else:
        st.sidebar.warning("⚠️ 网络异常，当前使用系统默认保底汇率")

    curr_rate = st.sidebar.number_input(f"自定义汇率 (1 CNY = ? {config['sym']})", value=float(config["rate"]), format="%.4f")

# =======================================================
# 模块 1：利润反推
# =======================================================
if app_mode == "💰 1. 利润反推 (精准运费版)":
    st.title("💰 竞品售价反推利润模拟器")

    st.subheader("📦 1. 成本与规格")
    row1_col1, row1_col2, row1_col3 = st.columns(3)
    with row1_col1:
        st.session_state.cny_cost = st.number_input("产品拿货成本 (CNY)", value=float(st.session_state.cny_cost), step=1.0, key="m1_cny")
    with row1_col2:
        st.session_state.weight_g = st.number_input("包裹实际重量 (克/g)", value=float(st.session_state.weight_g), step=10.0, key="m1_weight")
    with row1_col3:
        st.session_state.other_fixed_cny = st.number_input("打包耗材等杂费 (CNY)", value=float(st.session_state.other_fixed_cny), step=0.5, key="m1_fixed")

    ship_local = calc_shipping(st.session_state.weight_g, config)
    ship_cny = ship_local / curr_rate if curr_rate > 0 else 0
    st.info(f"🚚 根据官方底表，该重量预估跨境运费为: **{ship_local:,.2f} {config['sym']}** (折合 ￥ {ship_cny:,.2f})")

    st.divider()
    st.subheader("💵 2. 定价与佣金")
    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        pricing_mode = st.radio("👉 选择对手售价输入模式", ["按外币输入", "按人民币逆推"], horizontal=True)
        if pricing_mode == "按外币输入":
            default_local = 180000.0 if "VND" in target_country else 200.0
            local_price = st.number_input(f"竞品前台售价 ({config['sym']})", value=default_local, step=10.0, key="m1_price_local")
        else:
            cny_target_price = st.number_input("相当于人民币售价 (CNY)", value=50.0, step=1.0, key="m1_price_cny")
            local_price = cny_target_price * curr_rate
            st.success(f"🔄 折合当地售价: **{local_price:,.2f} {config['sym']}**")
    with row2_col2:
        st.session_state.affiliate_p = st.number_input("达人带货佣金比例 (%)", value=float(st.session_state.affiliate_p), step=1.0, key="m1_aff")

    total_percent_rate = (config["comm"] + config["trans"] + config["srv"] + config["tax"] + st.session_state.affiliate_p + 1.0) / 100
    total_fixed_local = ship_local + (st.session_state.other_fixed_cny * curr_rate)
    total_fees_local = local_price * total_percent_rate + total_fixed_local

    total_fees_cny = total_fees_local / curr_rate if curr_rate > 0 else 0
    net_profit_cny = (local_price / curr_rate) - st.session_state.cny_cost - total_fees_cny if curr_rate > 0 else 0
    profit_margin = (net_profit_cny / (local_price / curr_rate)) * 100 if local_price > 0 else 0

    st.divider()
    res1, res2, res3 = st.columns(3)
    res1.metric("单均净利润 (CNY)", f"￥ {net_profit_cny:,.2f}")
    res2.metric("实际净利率", f"{profit_margin:.2f} %")
    res3.metric("平台及物流总扣费 (CNY)", f"￥ {total_fees_cny:,.2f}")

    st.subheader("🎯 投流数据指标 (GMV Max/广告投放参考)")
    ad1, ad2 = st.columns(2)
    if net_profit_cny > 0:
        breakeven_roi = (local_price / curr_rate) / net_profit_cny
        ad1.metric("⚖️ 保本 ROI (ROAS)", f"{breakeven_roi:.2f}", "GMV Max 广告设置须高于此数值", delta_color="normal")
        ad2.metric("💸 最高可承受 CPA (单均广告费)", f"￥ {net_profit_cny:,.2f}", f"约合 {(net_profit_cny * curr_rate):,.2f} {config['sym']}", delta_color="off")
    else:
        ad1.metric("⚖️ 保本 ROI (ROAS)", "当前为亏本状态", "建议优化成本结构", delta_color="inverse")
        ad2.metric("💸 最高可承受 CPA", "0.00", "无法承担任何广告投放", delta_color="inverse")

    st.subheader("🧾 资金流向明细拆解")
    if curr_rate > 0:
        breakdown = {
            "明细项": ["产品成本", "官方跨境运费", "打包耗材杂费", "平台佣金", "交易手续费", "营销/活动费", "税金", "达人佣金", "提现手续费(1%)", "最终净利润"],
            "金额 (CNY)": [
                round(st.session_state.cny_cost, 2),
                round(ship_cny, 2),
                round(st.session_state.other_fixed_cny, 2),
                round((local_price * config["comm"] / 100) / curr_rate, 2),
                round((local_price * config["trans"] / 100) / curr_rate, 2),
                round((local_price * config["srv"] / 100) / curr_rate, 2),
                round((local_price * config["tax"] / 100) / curr_rate, 2),
                round((local_price * st.session_state.affiliate_p / 100) / curr_rate, 2),
                round((local_price * 0.01) / curr_rate, 2),
                round(net_profit_cny, 2),
            ],
        }
        st.table(breakdown)

# =======================================================
# 模块 2：正向定价
# =======================================================
elif app_mode == "🎯 2. 正向定价 (精准运费版)":
    st.title("🎯 商品上架正向定价计算器")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.session_state.cny_cost = st.number_input("1. 产品拿货成本 (CNY)", value=float(st.session_state.cny_cost), step=1.0, key="m2_cny")
        st.session_state.weight_g = st.number_input("2. 包裹实际重量 (克/g)", value=float(st.session_state.weight_g), step=10.0, key="m2_weight")
        st.session_state.other_fixed_cny = st.number_input("3. 打包耗材等杂费 (CNY)", value=float(st.session_state.other_fixed_cny), step=0.5, key="m2_fixed")
    with col2:
        st.session_state.target_margin = st.number_input("4. 目标净利润率 (%)", value=float(st.session_state.target_margin), step=1.0, key="m2_margin")
        st.session_state.discount = st.number_input("5. 前台拟设折扣 (如 5折 填 5)", value=float(st.session_state.discount), step=0.5, key="m2_disc")
    with col3:
        st.session_state.affiliate_p = st.number_input("6. 计划给达人的佣金 (%)", value=float(st.session_state.affiliate_p), step=1.0, key="m2_aff")

    st.info(f"**当前国家 ({target_country}) 平台费率预设:** 佣金 {config['comm']}% | 手续费 {config['trans']}% | 服务费 {config['srv']}% | 税金 {config['tax']}%")

    ship_local = calc_shipping(st.session_state.weight_g, config)
    ship_cny = ship_local / curr_rate if curr_rate > 0 else 0
    total_fixed_cost_cny = st.session_state.other_fixed_cny + ship_cny

    total_fee_percent = (config["comm"] + config["trans"] + config["srv"] + config["tax"] + st.session_state.affiliate_p + 1.0) / 100
    denominator = 1 - (st.session_state.target_margin / 100) - total_fee_percent

    st.divider()
    if denominator <= 0:
        st.error("🚨 警告：目标利润率与平台抽成加起来已超过 100%，定价公式崩溃！")
    else:
        req_price_cny = (st.session_state.cny_cost + total_fixed_cost_cny) / denominator
        req_price_local = req_price_cny * curr_rate
        original_price_local = req_price_local / (st.session_state.discount / 10)
        original_price_cny = req_price_cny / (st.session_state.discount / 10)
        net_profit_cny = req_price_cny * (st.session_state.target_margin / 100)

        st.subheader("✅ 最终 ERP / 后台填报建议数据")
        r1, r2, r3 = st.columns(3)
        r1.metric("ERP 前台划线原价", f"{original_price_local:,.2f} {config['sym']}", f"约合 ￥ {original_price_cny:,.2f}", delta_color="off")
        r2.metric("买家实际支付折后价", f"{req_price_local:,.2f} {config['sym']}", f"约合 ￥ {req_price_cny:,.2f}", delta_color="off")
        r3.metric("单笔净利润预估", f"￥ {net_profit_cny:,.2f}")
        st.caption(f"(*提示：当前折后售价中已自动包含预估 {ship_local:,.2f} {config['sym']} 的官方运费*)")

        st.subheader("🎯 投流数据指标 (GMV Max/广告投放参考)")
        ad1, ad2 = st.columns(2)
        breakeven_roi = req_price_cny / net_profit_cny if net_profit_cny > 0 else 0
        ad1.metric("⚖️ 保本 ROI (ROAS)", f"{breakeven_roi:.2f}", "GMV Max 广告设置须高于此数值", delta_color="normal")
        ad2.metric("💸 最高可承受 CPA (单均广告费)", f"￥ {net_profit_cny:,.2f}", f"约合 {(net_profit_cny * curr_rate):,.2f} {config['sym']}", delta_color="off")

# ==========================================
# 模块 3：店铺数据筛选
# ==========================================
elif app_mode == "📊 3. 店铺数据筛选 (智能表格)":
    st.title("📊 TK 店铺数据智能筛选工具")
    st.markdown("---")

    def clean_currency_for_filter(x):
        return safe_float(x)

    def clean_percent_for_filter(x):
        return safe_percent(x)

    st.header("1. 上传与设置条件")
    uploaded_file = st.file_uploader("请上传 TK 店铺导出的表格 (.xlsx 或 .csv)", type=["xlsx", "csv"])

    if uploaded_file is not None:
        try:
            if uploaded_file.name.lower().endswith(".csv"):
                df = pd.read_csv(uploaded_file, skiprows=2, dtype={"ID": str})
            else:
                df = pd.read_excel(uploaded_file, skiprows=2, dtype={"ID": str})

            for col in df.columns:
                if "GMV" in str(col):
                    df[col] = df[col].apply(clean_currency_for_filter)
                elif "率" in str(col):
                    df[col] = df[col].apply(clean_percent_for_filter)
                elif df[col].dtype == "object" and col not in ["ID", "商品", "状态", "商品名称"]:
                    converted = pd.to_numeric(df[col], errors="coerce")
                    if converted.notna().sum() > 0:
                        df[col] = converted

            st.subheader("添加筛选条件")
            selected_columns = st.multiselect("请选择你需要用来筛选的表头（可多选）:", options=df.columns.tolist())

            filters = {}
            if selected_columns:
                for col in selected_columns:
                    st.markdown(f"**🔹 {col}**")
                    if pd.api.types.is_numeric_dtype(df[col]):
                        col1, col2, col3 = st.columns(3)
                        step_val = 0.1 if "率" in str(col) else 1.0
                        with col1:
                            eq_text = st.text_input(f"等于 ({col})", value="", key=f"eq_{col}")
                        is_locked = eq_text.strip() != ""
                        with col2:
                            min_text = st.text_input(f"最小值 大于等于 ({col})", value="", disabled=is_locked, key=f"min_{col}")
                        with col3:
                            max_text = st.text_input(f"最大值 小于等于 ({col})", value="", disabled=is_locked, key=f"max_{col}")
                        filters[col] = ("numeric", eq_text, min_text, max_text)
                    else:
                        unique_vals = df[col].dropna().astype(str).unique().tolist()
                        selected_vals = st.multiselect(f"选择 {col} 状态", unique_vals, default=unique_vals, key=f"cat_{col}")
                        filters[col] = ("categorical", selected_vals)

            filtered_df = df.copy()
            for col, condition in filters.items():
                if condition[0] == "numeric":
                    eq_text, min_text, max_text = condition[1], condition[2], condition[3]
                    if str(eq_text).strip() != "":
                        filtered_df = filtered_df[filtered_df[col] == safe_float(eq_text)]
                    else:
                        if str(min_text).strip() != "":
                            filtered_df = filtered_df[filtered_df[col] >= safe_float(min_text)]
                        if str(max_text).strip() != "":
                            filtered_df = filtered_df[filtered_df[col] <= safe_float(max_text)]
                elif condition[0] == "categorical":
                    filtered_df = filtered_df[filtered_df[col].astype(str).isin(condition[1])]

            st.markdown("---")
            st.header("2. 筛选结果")
            st.success(f"🎉 筛选完毕！原始数据 {len(df)} 条，当前符合条件的有 **{len(filtered_df)}** 条。")
            st.dataframe(filtered_df, use_container_width=True)

            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                filtered_df.to_excel(writer, index=False, sheet_name="筛选结果")

            st.download_button(
                label="📥 下载筛选后的表格 (Excel)",
                data=excel_buffer.getvalue(),
                file_name="TK_筛选结果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:
            st.error(f"读取或处理文件时出错，请确认表格格式是否正确。错误信息: {e}")

# ==========================================
# 模块 4：商品数据诊断
# ==========================================
elif app_mode == "🔎 4. 商品数据诊断 (7天/28天)":
    st.title("🔎 TK 商品数据诊断：问题识别、僵尸品筛选与调整建议")
    st.caption("上传 TikTok Shop 后台导出的商品数据表，系统会自动识别曝光、点击、买家、成交、GMV 等字段，并给出商品级运营建议。上传近 28 天表时，会额外筛选曝光极低、无成交的僵尸产品。")

    with st.expander("📌 支持的数据表格式说明", expanded=False):
        st.write("支持 TikTok Shop 后台导出的商品数据表，表头包含：商品 ID、商品名称、商品曝光次数、去重商品曝光次数、去重商品点击次数、曝光到点击转化率、买家数、点击到成交转化率、成交件数、GMV。")
        st.write("可以只上传近 7 天数据做运营诊断；也可以只上传近 28 天数据做僵尸产品筛选；同时上传 7 天和 28 天数据时，会额外分析近期趋势变化。")

    st.subheader("① 上传数据表")
    col_a, col_b = st.columns(2)
    with col_a:
        file_7d = st.file_uploader("上传近 7 天商品数据表（可选，用于问题诊断）", type=["xlsx", "xls", "csv"], key="diagnose_7d")
    with col_b:
        file_28d = st.file_uploader("上传近 28 天商品数据表（可选，用于趋势对比 + 僵尸品筛选）", type=["xlsx", "xls", "csv"], key="diagnose_28d")

    st.subheader("② 诊断规则参数")
    p1, p2, p3 = st.columns(3)
    with p1:
        high_impression_threshold = st.number_input("高曝光判断阈值", min_value=50, value=500, step=50)
    with p2:
        min_click_threshold = st.number_input("高点击判断阈值", min_value=5, value=30, step=5)
    with p3:
        top_n = st.number_input("优先展示商品数", min_value=5, value=10, step=5)

    with st.expander("🧟 僵尸产品筛选规则（仅近 28 天表生效）", expanded=True):
        st.caption("默认定义：近 28 天曝光极低、点击极低、无买家、无成交、无 GMV 的商品。你可以根据店铺规模调整阈值。")
        z1, z2, z3 = st.columns(3)
        with z1:
            zombie_max_impressions = st.number_input("28天曝光 ≤", min_value=0, value=100, step=10, help="建议小店用 50-100，商品多的店可以放宽到 150-200。")
        with z2:
            zombie_max_clicks = st.number_input("28天点击 ≤", min_value=0, value=3, step=1)
        with z3:
            zombie_max_gmv = st.number_input("28天GMV ≤", min_value=0.0, value=0.0, step=1000.0, help="通常保持 0，表示无销售额才判定为僵尸品。")

    with st.expander("🤖 AI 运营报告节点设置", expanded=False):
        st.caption("可接入 DeepSeek API、本地 Ollama、OpenAI 兼容接口，或 Gemini API。AI 只接收汇总后的诊断数据和重点商品，不会上传整张原始表。")
        ai_enabled = st.checkbox("启用 AI 生成运营报告", value=False)
        ai_col1, ai_col2, ai_col3 = st.columns(3)
        with ai_col1:
            ai_provider = st.selectbox("AI 节点类型", ["DeepSeek API", "Ollama 原生接口", "OpenAI 兼容接口", "Gemini API"])
        with ai_col2:
            default_base_url = (
                "https://api.deepseek.com" if ai_provider == "DeepSeek API"
                else "http://127.0.0.1:11434" if ai_provider == "Ollama 原生接口"
                else "http://127.0.0.1:11434/v1" if ai_provider == "OpenAI 兼容接口"
                else "https://generativelanguage.googleapis.com/v1beta"
            )
            ai_base_url = st.text_input("接口地址 Base URL", value=default_base_url)
        with ai_col3:
            default_model = (
                "deepseek-v4-flash" if ai_provider == "DeepSeek API"
                else "gemma3:4b" if ai_provider == "Ollama 原生接口"
                else "gemma3:4b" if ai_provider == "OpenAI 兼容接口"
                else "gemini-1.5-flash"
            )
            if ai_provider == "DeepSeek API":
                model_choice = st.selectbox(
                    "DeepSeek 模型",
                    [
                        "deepseek-v4-flash",
                        "deepseek-v4-pro",
                        "deepseek-v4-flash|thinking",
                        "deepseek-v4-pro|thinking",
                        "deepseek-chat",
                        "deepseek-reasoner",
                    ],
                    index=0,
                    help="|thinking 表示启用 DeepSeek V4 thinking 模式；deepseek-chat / deepseek-reasoner 是兼容旧模型名。"
                )
                ai_model = st.text_input("模型名称 / 可手动覆盖", value=model_choice)
            else:
                ai_model = st.text_input("模型名称", value=default_model)
        ai_api_key = st.text_input("API Key（Ollama 可留空；DeepSeek 必填）", value="", type="password")
        report_style = st.selectbox("报告风格", ["标准运营报告", "老板汇报版", "执行清单版", "问题诊断版"])
        ai_temperature = st.slider("AI 创造性 temperature", min_value=0.0, max_value=1.0, value=0.3, step=0.1)

    if file_7d is None and file_28d is None:
        st.info("请至少上传一个数据表。上传近 7 天表可做商品问题诊断；上传近 28 天表可筛选僵尸产品。")
    else:
        try:
            sheets = {}
            df7 = None
            df28 = None
            result = None
            zombie_df = None
            trend_df = None

            if file_7d is not None:
                df7 = load_tk_product_table(file_7d)
                diagnosis = df7.apply(
                    diagnose_product,
                    axis=1,
                    high_impression_threshold=high_impression_threshold,
                    min_click_threshold=min_click_threshold,
                )
                result = pd.concat([df7, diagnosis], axis=1)
                priority_map = {"高": 3, "中": 2, "低": 1}
                result["优先级排序"] = result["处理优先级"].map(priority_map).fillna(1)
                result = result.sort_values(by=["优先级排序", "unique_impressions", "clicks", "gmv"], ascending=[False, False, False, False])

                st.success(f"已成功读取近 7 天数据：{len(result)} 个商品。")

                st.subheader("③ 店铺商品表现总览（近 7 天）")
                total_impressions = result["unique_impressions"].sum()
                total_clicks = result["clicks"].sum()
                total_buyers = result["buyers"].sum()
                total_orders = result["orders"].sum()
                total_gmv = result["gmv"].sum()
                avg_ctr = total_clicks / total_impressions * 100 if total_impressions > 0 else 0
                avg_cvr = total_buyers / total_clicks * 100 if total_clicks > 0 else 0

                m1, m2, m3, m4, m5, m6 = st.columns(6)
                m1.metric("商品数", f"{len(result):,.0f}")
                m2.metric("总去重曝光", f"{total_impressions:,.0f}")
                m3.metric("总点击", f"{total_clicks:,.0f}")
                m4.metric("整体点击率", f"{avg_ctr:.2f}%")
                m5.metric("买家数", f"{total_buyers:,.0f}")
                m6.metric("整体成交转化率", f"{avg_cvr:.2f}%")
                st.metric("总 GMV", f"{total_gmv:,.0f}")

                st.subheader("④ 自动运营总结")
                st.info(make_store_summary(result))

                st.subheader("⑤ 主要问题分布")
                high_priority = result[result["处理优先级"] == "高"]
                no_sales_with_clicks = result[(result["clicks"] >= min_click_threshold) & (result["buyers"] == 0)]
                low_ctr = result[(result["unique_impressions"] >= high_impression_threshold) & (result["ctr"] < 2)]
                scalable = result[(result["buyers"] >= 2) & (result["cvr"] >= 3)]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("高优先级商品", len(high_priority))
                c2.metric("点击高但无成交", len(no_sales_with_clicks))
                c3.metric("曝光高点击低", len(low_ctr))
                c4.metric("有成交可放量", len(scalable))

                show_cols = [
                    "product_id",
                    "product_name",
                    "impressions",
                    "unique_impressions",
                    "clicks",
                    "ctr",
                    "buyers",
                    "cvr",
                    "orders",
                    "gmv",
                    "处理优先级",
                    "问题标签",
                    "建议动作",
                    "问题判断",
                    "调整建议",
                ]
                display_df = result[show_cols].copy().rename(
                    columns={
                        "product_id": "商品ID",
                        "product_name": "商品名称",
                        "impressions": "商品曝光",
                        "unique_impressions": "去重曝光",
                        "clicks": "去重点击",
                        "ctr": "点击率%",
                        "buyers": "买家数",
                        "cvr": "成交转化率%",
                        "orders": "成交件数",
                        "gmv": "GMV",
                    }
                )
                display_df["点击率%"] = display_df["点击率%"].round(2)
                display_df["成交转化率%"] = display_df["成交转化率%"].round(2)

                st.subheader("⑥ 商品诊断明细")
                st.dataframe(display_df, use_container_width=True, height=520)
                sheets["商品诊断结果"] = display_df

                st.subheader("⑦ 优先处理商品清单")
                for _, row in result.head(int(top_n)).iterrows():
                    title = f"{row['处理优先级']}优先级｜{str(row['product_name'])[:90]}"
                    with st.expander(title):
                        st.write(f"**商品ID：** {row['product_id']}")
                        st.write(f"**曝光：** {row['unique_impressions']:.0f} ｜ **点击：** {row['clicks']:.0f} ｜ **点击率：** {row['ctr']:.2f}%")
                        st.write(f"**买家数：** {row['buyers']:.0f} ｜ **成交转化率：** {row['cvr']:.2f}% ｜ **成交件数：** {row['orders']:.0f} ｜ **GMV：** {row['gmv']:,.0f}")
                        st.warning(f"问题标签：{row['问题标签']}")
                        st.write(f"**问题判断：** {row['问题判断']}")
                        st.success(f"**调整建议：** {row['调整建议']}")
                        st.write(f"**建议动作：** {row['建议动作']}")

            if file_28d is not None:
                df28 = load_tk_product_table(file_28d)
                st.success(f"已成功读取近 28 天数据：{len(df28)} 个商品。")

                zombie_df = find_zombie_products(
                    df28,
                    max_impressions=zombie_max_impressions,
                    max_clicks=zombie_max_clicks,
                    max_buyers=0,
                    max_orders=0,
                    max_gmv=zombie_max_gmv,
                )
                zombie_df["28天日均曝光"] = zombie_df["28天日均曝光"].round(2)
                zombie_df["28天日均点击"] = zombie_df["28天日均点击"].round(2)

                st.subheader("🧟 近 28 天僵尸产品筛选结果")
                zc1, zc2, zc3, zc4 = st.columns(4)
                zc1.metric("疑似僵尸产品", len(zombie_df))
                zc2.metric("重度僵尸", (zombie_df["僵尸等级"] == "重度僵尸").sum() if len(zombie_df) else 0)
                zc3.metric("中度僵尸", (zombie_df["僵尸等级"] == "中度僵尸").sum() if len(zombie_df) else 0)
                zc4.metric("轻度僵尸", (zombie_df["僵尸等级"] == "轻度僵尸").sum() if len(zombie_df) else 0)

                if len(zombie_df) == 0:
                    st.success("按当前阈值，近 28 天数据中没有筛出疑似僵尸产品。可以适当放宽曝光或点击阈值再观察。")
                else:
                    st.warning("这些商品 28 天内曝光/点击/成交都非常弱，建议集中处理，避免长期占用商品池和运营精力。")
                    st.dataframe(zombie_df, use_container_width=True, height=420)
                    sheets["28天僵尸产品"] = zombie_df

                    with st.expander("🧹 僵尸产品处理建议", expanded=False):
                        st.markdown("""
                        **建议处理顺序：**
                        1. **重度僵尸**：优先下架或重新上架测试，不建议继续投入达人/广告。
                        2. **中度僵尸**：先检查类目、标题关键词、主图、价格，优化后再观察 7 天。
                        3. **轻度僵尸**：低优先级维护，可做小幅优化或合并成组合款。

                        **不要直接删除所有低曝光商品：**如果商品刚上架、库存很深、利润高或是配件补充款，可以先放入观察池；如果已经连续多个 28 天周期无曝光、无点击、无成交，再考虑下架。
                        """)

                if df7 is not None:
                    trend_df = compare_periods(df7, df28, short_days=7, long_days=28)
                    trend_show = trend_df.copy()
                    trend_show["曝光趋势变化%"] = trend_show["曝光趋势变化%"].round(2)
                    trend_show = trend_show.rename(columns={"product_id": "商品ID", "product_name": "商品名称"})
                    st.subheader("⑧ 近 7 天 vs 近 28 天趋势对比")
                    st.dataframe(trend_show, use_container_width=True, height=420)
                    sheets["7天_vs_28天趋势"] = trend_show

            st.subheader("⑨ AI 运营报告文字总结")
            rule_context = build_ai_report_context(result=result, df28=df28, zombie_df=zombie_df, trend_df=trend_df, top_n=int(top_n))
            with st.expander("查看发送给 AI 的结构化摘要", expanded=False):
                st.code(rule_context, language="json")

            if ai_enabled:
                if st.button("🤖 生成 AI 运营报告", type="primary", use_container_width=True):
                    prompt = build_ai_report_prompt(rule_context, report_style=report_style)
                    try:
                        with st.spinner("AI 正在生成运营报告，请稍等..."):
                            ai_report = call_ai_report(
                                provider=ai_provider,
                                base_url=ai_base_url,
                                api_key=ai_api_key,
                                model=ai_model,
                                prompt=prompt,
                                temperature=ai_temperature,
                            )
                        if ai_report:
                            st.session_state["last_ai_operation_report"] = ai_report
                        else:
                            st.warning("AI 返回为空，请检查模型是否正常运行。")
                    except Exception as ai_e:
                        st.error(f"AI 运营报告生成失败：{ai_e}")
                        st.info("如果你使用 DeepSeek API，请确认 API Key 正确且飞牛 NAS 能访问 https://api.deepseek.com；如果使用本地 Ollama，请确认飞牛 NAS 能访问 Ollama 所在电脑的 IP 和端口，例如 http://192.168.1.xxx:11434。")

                if st.session_state.get("last_ai_operation_report"):
                    st.markdown(st.session_state["last_ai_operation_report"])
                    st.download_button(
                        label="📥 下载 AI 运营报告 TXT",
                        data=st.session_state["last_ai_operation_report"].encode("utf-8"),
                        file_name="TK商品AI运营报告.txt",
                        mime="text/plain",
                    )
            else:
                st.info("未启用 AI 节点。你可以在上方“AI 运营报告节点设置”中启用；当前仍可使用规则版自动总结和商品诊断。")

            st.subheader("⑩ 下载诊断结果")
            if sheets:
                st.download_button(
                    label="📥 下载商品诊断结果 Excel",
                    data=to_excel_bytes(sheets),
                    file_name="TK商品数据诊断结果_含僵尸品筛选_AI报告版.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        except Exception as e:
            st.error(f"诊断失败：{e}")
            st.info("请确认上传的是 TikTok Shop 后台导出的商品数据表，且表头包含商品 ID、商品名称、曝光、点击、买家数、成交件数、GMV 等字段。")

# ==========================================
# 模块 5：全球实时汇率换算器
# ==========================================
elif app_mode == "💱 5. 全球实时汇率换算":
    st.title("💱 全球实时汇率换算引擎")
    st.markdown("对接全球金融 API，支持 **150+ 种货币** 任意双向换算。数据每 12 小时自动更新。")

    if not live_rates:
        st.error("🚨 无法获取实时汇率，请检查服务器网络连接或 API 接口状态！")
    else:
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
            "JPY - 日元 (日本)": "JPY",
        }

        all_codes = list(live_rates.keys())
        currency_map = top_currencies.copy()
        for code in all_codes:
            if code not in currency_map.values():
                currency_map[f"{code}"] = code
        currency_options = list(currency_map.keys())

        if "from_curr" not in st.session_state:
            st.session_state.from_curr = currency_options[0]
        if "to_curr" not in st.session_state:
            st.session_state.to_curr = currency_options[2]

        def swap_currencies():
            st.session_state.from_curr, st.session_state.to_curr = st.session_state.to_curr, st.session_state.from_curr

        st.divider()
        col1, col2, col3 = st.columns([2, 1, 2])

        with col1:
            from_curr_label = st.selectbox("1. 我持有 (From)", currency_options, key="from_curr")
            amount = st.number_input("输入换算金额", value=100.0, step=10.0, format="%.2f")

        with col2:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            st.button("🔄 互换货币", on_click=swap_currencies, use_container_width=True)

        with col3:
            to_curr_label = st.selectbox("2. 我要换成 (To)", currency_options, key="to_curr")

        from_code = currency_map[from_curr_label]
        to_code = currency_map[to_curr_label]

        # live_rates 是以 CNY 为基准。先换成人民币，再换成目标币种。
        if from_code == "CNY":
            amount_cny = amount
        else:
            amount_cny = amount / live_rates[from_code]
        result_amount = amount_cny if to_code == "CNY" else amount_cny * live_rates[to_code]

        st.subheader("换算结果")
        st.metric("结果", f"{result_amount:,.4f} {to_code}", f"{amount:,.4f} {from_code}", delta_color="off")
        st.caption(f"参考汇率：1 {from_code} ≈ {result_amount / amount if amount else 0:,.6f} {to_code}")
