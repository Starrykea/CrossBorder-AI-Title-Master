import streamlit as st


def calculate_dropshipping_price(cost_val, cost_unit, weight_g, dims, profit_val, profit_unit, ship_rate, comm_rate,
                                 risk_buffer, handling_fee_cny, extra_weight_g):
    cny_to_usd_safe = 7.1  # 汇率安全垫

    # 1. 成本与利润转换
    cost_usd = cost_val / cny_to_usd_safe if cost_unit == "CNY" else cost_val
    profit_usd = profit_val / cny_to_usd_safe if profit_unit == "CNY" else profit_val
    handling_usd = handling_fee_cny / 7.2  # 代发费通常固定为人民币

    # 2. 计费重量逻辑（包含货代包装冗余）
    total_weight = weight_g + extra_weight_g
    l, w, h = dims
    # 考虑包装后的体积略微膨胀 (+1cm)
    v_weight = ((l + 1) * (w + 1) * (h + 1)) / 6000 * 1000
    billable_weight = max(total_weight, v_weight)

    # 3. 运费计算
    shipping_usd = (billable_weight / 1000) * ship_rate

    # 4. 定价公式 (考虑美客多佣金与损耗)
    # 分母 = 1 - 佣金 - 风险损耗
    denominator = 1 - comm_rate - risk_buffer

    # 初始试算
    price_trial = (cost_usd + shipping_usd + profit_usd + handling_usd) / denominator

    # 5. 低价固定费判定 (299 MXN / 17.5 USD 门槛)
    if price_trial < 17.5:
        final_price_usd = (cost_usd + shipping_usd + profit_usd + handling_usd + 1.8) / denominator
        has_fixed_fee = True
    else:
        final_price_usd = price_trial
        has_fixed_fee = False

    return final_price_usd, billable_weight, shipping_usd, has_fixed_fee, handling_usd


# --- UI 界面 ---
st.set_page_config(page_title="东莞代发专用定价器", layout="wide")
st.title("🚀 美客多 CBT 定价器 (东莞代发版)")
st.caption("适用场景：厂家直发东莞货代仓库，虚拟仓出货模式")

with st.sidebar:
    st.header("📦 代发成本配置")
    h_fee = st.number_input("货代贴标处理费 (RMB/单)", value=3.0)
    e_weight = st.number_input("额外包材重量 (g)", value=50.0, help="气泡袋、纸箱等重量")
    s_rate = st.number_input("国际运费单价 (USD/KG)", value=16.0)

    st.divider()
    st.header("🛡️ 风险控制")
    risk = st.slider("风险损耗 (汇率/退货) %", 1, 10, 5) / 100
    comm = st.slider("平台佣金 %", 10.0, 25.0, 19.0) / 100

col1, col2 = st.columns(2)

with col1:
    st.subheader("💰 货源与利润")
    c_unit = st.radio("货源币种", ["CNY", "USD"], horizontal=True)
    c_val = st.number_input("厂家拿货价", value=6.83)

    p_unit = st.radio("期望纯利币种", ["CNY", "USD"], horizontal=True)
    p_val = st.number_input("我想赚多少", value=20.0)

    st.subheader("📏 产品规格")
    w_g = st.number_input("货源净重 (g)", value=200.0)
    l = st.number_input("长 (cm)", value=10.0)
    w = st.number_input("宽 (cm)", value=10.0)
    h = st.number_input("高 (cm)", value=10.0)

# --- 执行计算 ---
res_usd, b_weight, s_usd, fee_flag, h_usd = calculate_dropshipping_price(
    c_val, c_unit, w_g, (l, w, h), p_val, p_unit, s_rate, comm, risk, h_fee, e_weight
)

with col2:
    st.subheader("📊 最终定价分析")
    res_mxn = res_usd * 17.2  # 参考汇率

    # 核心显示
    st.metric("建议标价 (USD)", f"${res_usd:.2f}")
    st.metric("买家端价格 (MXN)", f"{int(res_mxn)} MXN")

    # 预警逻辑
    if fee_flag:
        st.error("⚠️ 触发低价处罚：由于标价低于 $17.5，已被额外扣除 $1.8 手续费！")
        st.info("💡 建议：尝试成套销售 (Pack) 提高单价。")
    else:
        st.success("✅ 利润优化：标价高于 $17.5，已免除 $1.8 固定费。")

    # 成本拆解
    with st.expander("查看成本明细 (USD)"):
        st.write(f"1. 厂家货值: ${c_val / 7.1 if c_unit == 'CNY' else c_val:.2f}")
        st.write(f"2. 国际运费: ${s_usd:.2f} (计费重:{b_weight:.0f}g)")
        st.write(f"3. 代发贴标费: ${h_usd:.2f}")
        st.write(f"4. 平台佣金: ${res_usd * comm:.2f}")
        st.write(f"5. 风险冗余: ${res_usd * risk:.2f}")
        if fee_flag:
            st.write("6. 低价固定费: $1.80")