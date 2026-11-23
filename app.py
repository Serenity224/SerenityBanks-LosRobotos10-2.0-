import json
import math
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

# ---------------------------------------------------------
# EXACT DECIMAL MONEY HELPERS
# ---------------------------------------------------------
def to_money(val) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def fmt_money(val) -> str:
    d = to_money(val)
    return f"-${abs(d):,.2f}" if d < 0 else f"${d:,.2f}"

# ---------------------------------------------------------
# DEFAULT ROB-3 CONFIGURATION & STATE INITIALIZATION
# ---------------------------------------------------------
def default_state() -> dict:
    return {
        "team_id": "LOS-ROBOTOS-10",
        "course": "AP Calculus",
        "pathway_id": "ROB-3",
        "business_name": "Robotics kit and repair studio",
        "selected_level": "Advanced",
        "teacher_approved_skills": [
            "Constrained Profit Optimization",
            "Accumulation via Definite Integrals",
        ],
        "snapshot_id": "snap-v1-init",
        "state_version": 1,
        "simulation_date": "2027-01-01",
        "base_period": "monthly",
        "working_days": 22,
        "currency": "USD",
        "random_seed": 2027,
        "mode": "Normal",
        "funding": {
            "owner_contribution": "12000.00",
            "equipment_assets": "4000.00",
            "pre_opening_expense": "0.00",
            "opening_inventory_value": "3000.00",
            "opening_cash": "5000.00",
            "retained_earnings": "0.00",
            "loan_debt": "0.00",
        },
        "assumptions": {
            "base_price": "120.00",
            "D0": 40,
            "staff_hours": 90.0,
            "hours_per_unit": 3.0,
            "opening_stock_units": 100,
            "component_unit_cost": "30.00",
            "defect_rate": 0.0,
        },
        "cost_lines": {
            "variable_per_attempted": {
                "components_COGS": "30.00",
                "assembly_labor": "20.00",
                "packaging": "10.00",
                "warranty_consumables": "5.00",
            },
            "fixed_monthly": {
                "workspace": "250.00",
                "equipment_maintenance": "150.00",
                "software": "100.00",
                "admin": "100.00",
            },
        },
        "offerings": [
            {
                "offering_id": "ROB-KIT-01",
                "name": "Introductory robot kit",
                "unit": "kit",
                "price": "120.00",
                "demand_rule": "q(p) = max(0, 80 - (1/3)p)",
                "capacity_rule": "floor(staff_hours / hours_per_unit)",
            }
        ],
        "current_cash": "5000.00",
        "current_stock_units": 100,
        "current_debt": "0.00",
        "executed_run_ids": [],
        "ledger": [],
        "campaigns": [],
        "decisions": [],
    }

# ---------------------------------------------------------
# DETERMINISTIC ROB-3 MONTHLY ENGINE
# ---------------------------------------------------------
def run_monthly_step(
    state: dict,
    run_id: str,
    sim_date: str,
    requested: int,
    restock_units: int = 0,
    own_marketing: Decimal = Decimal("0.00"),
    refund_amount: Decimal = Decimal("0.00"),
    loan_cash: Decimal = Decimal("0.00"),
    principal_repayment: Decimal = Decimal("0.00"),
    interest_expense: Decimal = Decimal("0.00"),
    additional_capex: Decimal = Decimal("0.00"),
    new_owner_cash: Decimal = Decimal("0.00"),
    capacity_override: int | None = None,
) -> tuple[dict, bool, str]:
    if run_id in state["executed_run_ids"]:
        return state, False, f"Duplicate run_id '{run_id}' rejected. No transactions added."

    if requested < 0 or restock_units < 0:
        return state, False, "Negative requested units or restock units are invalid."

    a = state["assumptions"]
    price = to_money(a["base_price"])
    comp_unit_cost = to_money(a["component_unit_cost"])
    defect_rate = float(a["defect_rate"])

    var_lines = state["cost_lines"]["variable_per_attempted"]
    var_per_unit = sum(to_money(v) for v in var_lines.values())
    non_comp_var_per_unit = var_per_unit - to_money(var_lines["components_COGS"])
    fixed_expense = sum(to_money(v) for v in state["cost_lines"]["fixed_monthly"].values())

    if capacity_override is not None:
        capacity = int(capacity_override)
    else:
        capacity = math.floor(float(a["staff_hours"]) / float(a["hours_per_unit"]))

    open_stock = int(state["current_stock_units"])
    available_stock = open_stock + int(restock_units)
    attempted = min(int(requested), capacity, available_stock)
    failed = math.floor(attempted * defect_rate)
    sold = attempted - failed
    lost_demand = max(0, int(requested) - attempted)

    gross_revenue = to_money(price * sold)
    net_revenue = to_money(gross_revenue - refund_amount)
    variable_expense = to_money(var_per_unit * attempted)
    operating_profit = to_money(
        net_revenue - variable_expense - fixed_expense - own_marketing
    )
    net_profit = to_money(operating_profit - interest_expense)

    open_cash = to_money(state["current_cash"])
    restock_cash_outflow = to_money(comp_unit_cost * int(restock_units))
    non_comp_cash_outflow = to_money(non_comp_var_per_unit * attempted)

    closing_cash = to_money(
        open_cash
        + net_revenue
        - non_comp_cash_outflow
        - restock_cash_outflow
        - fixed_expense
        - own_marketing
        - interest_expense
        - principal_repayment
        - additional_capex
        + new_owner_cash
        + loan_cash
    )

    closing_stock = available_stock - attempted
    closing_inventory_value = to_money(comp_unit_cost * closing_stock)
    closing_debt = to_money(to_money(state["current_debt"]) + loan_cash - principal_repayment)

    new_version = state["state_version"] + 1
    tx_base = f"TX-{run_id}"

    new_entries = [
        {
            "transaction_id": f"{tx_base}-REV",
            "run_id": run_id,
            "date": sim_date,
            "event_type": "sales_revenue",
            "category": "Revenue",
            "amount": str(net_revenue),
            "quantity": sold,
            "unit_price": str(price),
            "offering_id": "ROB-KIT-01",
            "campaign_id": "",
            "financing_type": "",
            "state_version": new_version,
        },
        {
            "transaction_id": f"{tx_base}-VAR",
            "run_id": run_id,
            "date": sim_date,
            "event_type": "variable_expense",
            "category": "COGS_and_Variable",
            "amount": str(variable_expense),
            "quantity": attempted,
            "unit_price": str(var_per_unit),
            "offering_id": "ROB-KIT-01",
            "campaign_id": "",
            "financing_type": "",
            "state_version": new_version,
        },
        {
            "transaction_id": f"{tx_base}-FIX",
            "run_id": run_id,
            "date": sim_date,
            "event_type": "fixed_expense",
            "category": "Operating_Fixed",
            "amount": str(fixed_expense),
            "quantity": 1,
            "unit_price": str(fixed_expense),
            "offering_id": "",
            "campaign_id": "",
            "financing_type": "",
            "state_version": new_version,
        },
    ]

    if own_marketing > 0:
        new_entries.append({
            "transaction_id": f"{tx_base}-MKT",
            "run_id": run_id,
            "date": sim_date,
            "event_type": "marketing_expense",
            "category": "Marketing",
            "amount": str(own_marketing),
            "quantity": 1,
            "unit_price": str(own_marketing),
            "offering_id": "",
            "campaign_id": f"CAMP-{run_id}",
            "financing_type": "",
            "state_version": new_version,
        })

    if restock_cash_outflow > 0:
        new_entries.append({
            "transaction_id": f"{tx_base}-STK",
            "run_id": run_id,
            "date": sim_date,
            "event_type": "inventory_restock",
            "category": "Inventory_Cash_Outflow",
            "amount": str(restock_cash_outflow),
            "quantity": int(restock_units),
            "unit_price": str(comp_unit_cost),
            "offering_id": "",
            "campaign_id": "",
            "financing_type": "",
            "state_version": new_version,
        })

    if loan_cash > 0 or principal_repayment > 0 or interest_expense > 0:
        new_entries.append({
            "transaction_id": f"{tx_base}-FIN",
            "run_id": run_id,
            "date": sim_date,
            "event_type": "financing_activity",
            "category": "Financing",
            "amount": str(loan_cash - principal_repayment - interest_expense),
            "quantity": 1,
            "unit_price": "0.00",
            "offering_id": "",
            "campaign_id": "",
            "financing_type": "Loan/Debt",
            "state_version": new_version,
        })

    summary_record = {
        "run_id": run_id,
        "date": sim_date,
        "mode": "Fixture-Test" if capacity_override is not None else "Normal",
        "requested": int(requested),
        "capacity": capacity,
        "attempted": attempted,
        "failed": failed,
        "sold": sold,
        "lost_demand": lost_demand,
        "revenue": str(net_revenue),
        "variable_expense": str(variable_expense),
        "fixed_expense": str(fixed_expense),
        "marketing_expense": str(own_marketing),
        "total_expense": str(to_money(variable_expense + fixed_expense + own_marketing)),
        "operating_profit": str(operating_profit),
        "net_profit": str(net_profit),
        "closing_cash": str(closing_cash),
        "closing_stock_units": closing_stock,
        "closing_inventory_value": str(closing_inventory_value),
        "state_version": new_version,
    }

    state["ledger"].extend(new_entries)
    state.setdefault("monthly_summaries", []).append(summary_record)
    state["executed_run_ids"].append(run_id)
    state["current_cash"] = str(closing_cash)
    state["current_stock_units"] = closing_stock
    state["current_debt"] = str(closing_debt)
    state["state_version"] = new_version
    state["simulation_date"] = sim_date
    state["snapshot_id"] = f"snap-v{new_version}-{run_id}"

    return state, True, f"Step '{run_id}' recorded (state_version -> v{new_version})."

# ---------------------------------------------------------
# AP CALCULUS OPTIMIZATION & INTEGRAL HELPERS
# ---------------------------------------------------------
def solve_constrained_profit(D0: float, p0: float, v: float, F: float, cap: float) -> dict:
    a = 2.0 * D0
    b = D0 / p0
    p_max = 2.0 * p0
    p_corner = (a - cap) / b if b > 0 else 0.0
    p_unconstrained = (a + b * v) / (2.0 * b)

    candidates = [0.0, p_max]
    if 0.0 <= p_corner <= p_max:
        candidates.append(p_corner)
    if p_corner <= p_unconstrained <= p_max:
        candidates.append(p_unconstrained)

    def profit_fn(p):
        q = max(0.0, a - b * p)
        s = min(cap, q)
        return (p - v) * s - F

    best_p = max(candidates, key=profit_fn)
    best_profit = profit_fn(best_p)

    return {
        "a": a,
        "b": b,
        "p_max": p_max,
        "p_corner": p_corner,
        "p_unconstrained": p_unconstrained,
        "unconstrained_profit": (p_unconstrained - v) * (a - b * p_unconstrained) - F,
        "optimal_p": best_p,
        "optimal_profit": best_profit,
    }

def compute_integral_fixture(r0: float, r1: float, c0: float, c1: float, t_start: float, t_end: float) -> dict:
    rev = r0 * (t_end - t_start) + 0.5 * r1 * (t_end**2 - t_start**2)
    cost = c0 * (t_end - t_start) + 0.5 * c1 * (t_end**2 - t_start**2)
    return {
        "accumulated_revenue": rev,
        "accumulated_cost": cost,
        "accumulated_profit": rev - cost,
    }

# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="Career Venture Lab | LOS-ROBOTOS-10", layout="wide")

    if "biz_state" not in st.session_state:
        st.session_state.biz_state = default_state()

    state = st.session_state.biz_state

    st.title("Career Venture Lab — Robotics Kit & Repair Studio")
    st.caption(
        f"**Team:** {state['team_id']} | **Pathway:** {state['pathway_id']} | "
        f"**Course:** {state['course']} ({state['selected_level']}) | "
        f"**Snapshot:** `{state['snapshot_id']}` (v{state['state_version']})"
    )

    if state["mode"] == "Fixture-Test":
        st.warning("FIXTURE-TEST MODE ACTIVE: Capacity overrides are enabled for ledger verification. Reset before Normal Mode simulation.")

    tabs = st.tabs([
        "1. Overview & Status",
        "2. Inputs & Funding",
        "3. Math Skills (AP Calculus)",
        "4. Simulation & Ledger",
        "5. Save / Load & Fixtures",
        "6. Stage 2-4 Roadmap",
    ])

    with tabs[0]:
        st.subheader("System Overview & Current Balances")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current Spendable Cash", fmt_money(state["current_cash"]))
        c2.metric("Component Stock", f"{state['current_stock_units']} sets")
        inv_val = to_money(state["assumptions"]["component_unit_cost"]) * state["current_stock_units"]
        c3.metric("Inventory Asset Value", fmt_money(inv_val))
        c4.metric("Current Debt", fmt_money(state["current_debt"]))

        st.markdown("### Active Business Rules (`ROB-3`)")
        st.info(
            "- **Capacity Formula:** `capacity = floor(staff_hours / hours_per_unit)`\n"
            "- **Fulfillment Formula:** `attempted = min(requested, capacity, opening_stock + restock)`, `failed = floor(attempted * defect_rate)`, `sold = attempted - failed`\n"
            "- **Inventory Accounting:** Component cost ($30/set) is paid in cash when restocked, and recognized as an expense when kits are attempted (including failed builds)."
        )

    with tabs[1]:
        st.subheader("Editable Business & Cost Inputs")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Operating Assumptions")
            new_price = st.number_input("Base Price ($/kit)", min_value=1.0, value=float(state["assumptions"]["base_price"]), step=5.0)
            new_d0 = st.number_input("Baseline Monthly Demand D0 (kits)", min_value=0, value=int(state["assumptions"]["D0"]), step=1)
            new_hours = st.number_input("Monthly Staff Hours", min_value=0.0, value=float(state["assumptions"]["staff_hours"]), step=5.0)
            new_hpu = st.number_input("Hours per Kit", min_value=0.1, value=float(state["assumptions"]["hours_per_unit"]), step=0.5)
            new_defect = st.slider("Defect Rate (0.0 to 1.0)", min_value=0.0, max_value=1.0, value=float(state["assumptions"]["defect_rate"]), step=0.05)

            if st.button("Save Operating Assumptions"):
                state["assumptions"]["base_price"] = str(to_money(new_price))
                state["assumptions"]["D0"] = int(new_d0)
                state["assumptions"]["staff_hours"] = float(new_hours)
                state["assumptions"]["hours_per_unit"] = float(new_hpu)
                state["assumptions"]["defect_rate"] = float(new_defect)
                st.success("Assumptions updated.")

        with col2:
            st.markdown("#### Cost Lines (Baseline ROB-3)")
            var_df = pd.DataFrame([
                {"Cost Line": k, "Amount ($/attempted kit)": float(v)}
                for k, v in state["cost_lines"]["variable_per_attempted"].items()
            ])
            st.dataframe(var_df, use_container_width=True, hide_index=True)

            fix_df = pd.DataFrame([
                {"Fixed Line": k, "Amount ($/month)": float(v)}
                for k, v in state["cost_lines"]["fixed_monthly"].items()
            ])
            st.dataframe(fix_df, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Math Skills & Challenge Level Panel — AP Calculus (Advanced)")
        st.markdown(
            "**Approved Skills:** Constrained Profit Optimization & Definite Integral Accumulation  \n"
            "**Continuous vs. Actual Notice:** Graphs below show continuous mathematical projections. Actual ledger transactions floor integer kit units."
        )

        D0 = float(state["assumptions"]["D0"])
        p0 = float(state["assumptions"]["base_price"])
        v = sum(float(x) for x in state["cost_lines"]["variable_per_attempted"].values())
        F = sum(float(x) for x in state["cost_lines"]["fixed_monthly"].values())
        cap = math.floor(float(state["assumptions"]["staff_hours"]) / float(state["assumptions"]["hours_per_unit"]))

        opt = solve_constrained_profit(D0, p0, v, F, cap)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Capacity Corner Price", f"${opt['p_corner']:.2f}")
        m2.metric("Unconstrained Critical Point", f"${opt['p_unconstrained']:.2f}")
        m3.metric("Constrained Optimal Price", f"${opt['optimal_p']:.2f}")
        m4.metric("Max Continuous Profit", f"${opt['optimal_profit']:,.2f}")

        st.latex(rf"q(p) = {opt['a']:.1f} - \frac{{1}}{{3}}p, \quad s(p) = \min({cap},\, \max(0, q(p))), \quad 0 \le p \le {opt['p_max']:.0f}")

        p_vals = np.linspace(0, opt["p_max"], 400)
        q_vals = np.maximum(0.0, opt["a"] - opt["b"] * p_vals)
        s_vals = np.minimum(cap, q_vals)
        profit_vals = (p_vals - v) * s_vals - F

        deriv_vals = np.where(
            p_vals < opt["p_corner"],
            cap,
            opt["a"] + opt["b"] * v - 2.0 * opt["b"] * p_vals,
        )

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
        ax1.plot(p_vals, profit_vals, label="Constrained Profit P(p)", color="#1f77b4", linewidth=2)
        ax1.axhline(0, color="black", linestyle="--", linewidth=0.8, label="Break-even ($0)")
        ax1.axvline(opt["p_corner"], color="#d95f02", linestyle=":", label=f"Capacity Corner (${opt['p_corner']:.2f})")
        ax1.scatter([opt["optimal_p"]], [opt["optimal_profit"]], color="#2ca02c", zorder=5, label=f"Constrained Optimum (${opt['optimal_p']:.2f})")
        ax1.set_ylabel("Monthly Profit ($)")
        ax1.set_title(f"Constrained Profit & Derivative | {state['team_id']} | {state['snapshot_id']}")
        ax1.legend(loc="best", fontsize=8)
        ax1.grid(True, alpha=0.3)

        left_mask = p_vals < opt["p_corner"]
        right_mask = p_vals > opt["p_corner"]
        ax2.plot(p_vals[left_mask], deriv_vals[left_mask], color="#7570b3", linewidth=2, label="P'(p) (Capacity-Bound)")
        ax2.plot(p_vals[right_mask], deriv_vals[right_mask], color="#e7298a", linewidth=2, label="P'(p) (Demand-Bound)")
        ax2.axhline(0, color="black", linestyle="--", linewidth=0.8)
        if 0 < opt["p_corner"] < opt["p_max"]:
            ax2.scatter([opt["p_corner"], opt["p_corner"]], [cap, opt["a"] + opt["b"] * v - 2 * opt["b"] * opt["p_corner"]], facecolors="white", edgecolors="red", zorder=5, label="Undefined Corner")
        ax2.set_xlabel("Price p ($ per kit)")
        ax2.set_ylabel("Marginal Profit dP/dp ($/$)")
        ax2.legend(loc="best", fontsize=8)
        ax2.grid(True, alpha=0.3)

        st.pyplot(fig)

        st.divider()
        st.markdown("### Advanced Integration Extension: Accumulated Campaign Rate Model")
        st.caption("Isolated rate exercise over [0, 10] days ($/day). Does not alter the monthly ledger.")
        ic1, ic2, ic3 = st.columns(3)
        r0 = ic1.number_input("r(t) Intercept ($/day)", value=100.0)
        r1 = ic1.number_input("r(t) Slope ($/day²)", value=20.0)
        c0 = ic2.number_input("c(t) Intercept ($/day)", value=60.0)
        c1 = ic2.number_input("c(t) Slope ($/day²)", value=5.0)
        t_end = ic3.number_input("Days (0 to T)", min_value=1.0, value=10.0)

        int_res = compute_integral_fixture(r0, r1, c0, c1, 0.0, t_end)
        r_col1, r_col2, r_col3 = st.columns(3)
        r_col1.metric("Accumulated Revenue ∫r(t)dt", f"${int_res['accumulated_revenue']:,.2f}")
        r_col2.metric("Accumulated Cost ∫c(t)dt", f"${int_res['accumulated_cost']:,.2f}")
        r_col3.metric("Net Accumulated Profit", f"${int_res['accumulated_profit']:,.2f}")

    with tabs[3]:
        st.subheader("Run Simulation Step & Dated Event Ledger")
        with st.form("step_form"):
            sc1, sc2, sc3 = st.columns(3)
            run_id = sc1.text_input("Unique Run ID", value=f"RUN-M{state['state_version']:02d}")
            sim_date = sc2.text_input("Period End Date (YYYY-MM-DD)", value="2027-01-31")
            req_units = sc3.number_input("Requested Kits", min_value=0, value=int(state["assumptions"]["D0"]), step=1)

            sc4, sc5, sc6 = st.columns(3)
            restock = sc4.number_input("Restock Component Sets", min_value=0, value=0, step=5)
            mkt_cost = sc5.number_input("Approved Campaign Expense ($)", min_value=0.0, value=0.0, step=25.0)
            loan_in = sc6.number_input("New Loan Proceeds ($)", min_value=0.0, value=0.0, step=100.0)

            submitted = st.form_submit_button("Approve & Advance One Month")
            if submitted:
                state["mode"] = "Normal"
                state, ok, msg = run_monthly_step(
                    state=state,
                    run_id=run_id.strip(),
                    sim_date=sim_date.strip(),
                    requested=int(req_units),
                    restock_units=int(restock),
                    own_marketing=to_money(mkt_cost),
                    loan_cash=to_money(loan_in),
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        if state.get("monthly_summaries"):
            st.markdown("#### Monthly Simulation History")
            sum_df = pd.DataFrame(state["monthly_summaries"])
            st.dataframe(sum_df, use_container_width=True, hide_index=True)

        if state["ledger"]:
            st.markdown("#### Underlying Dated Event Ledger")
            led_df = pd.DataFrame(state["ledger"])
            st.dataframe(led_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Ledger CSV",
                data=led_df.to_csv(index=False),
                file_name=f"{state['team_id']}_ledger_v{state['state_version']}.csv",
                mime="text/csv",
            )

    with tabs[4]:
        st.subheader("Save / Restore Snapshot JSON & Fixture Replay")
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### Export Current Snapshot")
            snap_json = json.dumps(state, indent=2)
            st.download_button(
                "Download Snapshot JSON",
                data=snap_json,
                file_name=f"{state['team_id']}_snapshot_v{state['state_version']}.json",
                mime="application/json",
            )

            st.markdown("#### Replay ROB-3 Official Fixture (`monthly_fixture.csv`)")
            if st.button("Reset & Run 3-Month Fixture"):
                fresh = default_state()
                fresh["mode"] = "Fixture-Test"
                try:
                    fixture_df = pd.read_csv("sample_data/monthly_fixture.csv")
                except FileNotFoundError:
                    fixture_df = pd.DataFrame({
                        "month": ["2027-01", "2027-02", "2027-03"],
                        "requested": [40, 44, 36],
                        "capacity_override": [30, 30, 22],
                        "ad_cost": [0, 100, 0],
                    })
                for idx, row in fixture_df.iterrows():
                    month_str = str(row["month"])
                    last_day = {"2027-01": "2027-01-31", "2027-02": "2027-02-28", "2027-03": "2027-03-31"}.get(month_str, f"{month_str}-28")
                    fresh, _, _ = run_monthly_step(
                        state=fresh,
                        run_id=f"FIX-{month_str}",
                        sim_date=last_day,
                        requested=int(row["requested"]),
                        capacity_override=int(row["capacity_override"]),
                        own_marketing=to_money(row["ad_cost"]),
                    )
                st.session_state.biz_state = fresh
                st.success("Fixture replayed! Check Tab 4 to verify 2027-01 through 2027-03 totals.")
                st.rerun()

        with col_b:
            st.markdown("#### Import Snapshot JSON")
            uploaded = st.file_uploader("Upload Snapshot JSON", type=["json"])
            if uploaded is not None:
                try:
                    incoming = json.load(uploaded)
                    if incoming.get("team_id") != state["team_id"]:
                        st.error(f"Rejected: Wrong team_id '{incoming.get('team_id')}'. Expected '{state['team_id']}'.")
                    elif int(incoming.get("state_version", 0)) < int(state["state_version"]):
                        st.error(
                            f"Rejected: Stale state_version v{incoming.get('state_version')} "
                            f"(current version is v{state['state_version']})."
                        )
                    else:
                        st.session_state.biz_state = incoming
                        st.success(f"Snapshot v{incoming.get('state_version')} restored!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Invalid JSON file: {e}")

    with tabs[5]:
        st.subheader("Unimplemented Modules (Upcoming Stages)")
        st.info(
            "- **Stage 2 (Not Yet Implemented):** AI Departmental Recommendations (Finance, Operations, Marketing, Reviewer), Full Report Center (PDF/CSV Income Statement, Cash Flow, Balance Sheet), Costed Marketing Studio.\n"
            "- **Stage 3 (Not Yet Implemented):** Cross-Course Connections Panel, Snapshot-Based Practice Assessment Panel.\n"
            "- **Stage 4 (Optional, Lowest Priority):** Demonstration Storefront with test orders."
        )

if __name__ == "__main__":
    main()
