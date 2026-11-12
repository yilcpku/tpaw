"""Immutable original native references and honest input-change disclosure."""
import hashlib
import json

COMPARISON_FIELDS=("retirement_plans","retirement_withdrawal","real_cashflows_only","initial_assets","current_age","evaluation_month","candidates","notice_months","threshold_annual",
    "annual_budget","reserve","reserve_basis","reserve_funding","cash_multiple","defensive","term_years","cashflow_rows",
    "planning_cpi","savings_mode","savings_coverage_end","risk_tolerance","policy_rra","policy_variance_annual",
    "time_preference","additional_spending_tilt","stock_return","stock_volatility","planning_defensive_return",
    "horizon","margin","dataset","use_forward_targets","seed","runs","risk_delta_at90","monthly_savings",
    "require_savings_coverage","reserve_cash_rate","reserve_draws","floor_trigger_fraction","cpi_publication_lag_months",
    "defensive_rate_mode","rate_persistence","initial_deposit_rate","initial_government_yield","demand_rate","legacy_target","legacy_rra")


def input_signature(s):
    values={key:s.get(key) for key in COMPARISON_FIELDS}
    return hashlib.sha256(json.dumps(values,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def reference_view(s,baseline):
    expected=baseline.get('imported_scenario_inputs',{}).get(s.get('import_variant'),{})
    differences=[key for key in COMPARISON_FIELDS if expected.get(key)!=s.get(key)] if expected else list(COMPARISON_FIELDS)
    return {**{k:v for k,v in baseline.items() if k!='imported_scenario_inputs'},
            'additional_input_changes':differences,'import_inputs_unchanged':not differences,
            'intended_changes':s.get('native_differences',[]),
            'comparison_status':'Archived native result is an immutable reference; it is not a rerun of edited inputs and has different realized sampling. Paired horizon/channel panels provide the controlled comparisons.'}
