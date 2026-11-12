//! Offline experimental horizon policy. Original replay executable stays intact.
use clap::Parser;
use prost::Message;
use serde::Deserialize;
use simulator::{cuda_bridge::{PlanParamsCuda, PlanParamsCuda_C_Arrays},
    historical_monthly_returns::{HISTORICAL_MONTHLY_RETURNS,data::average_annual_real_earnings_for_sp500_for_10_years::AVERAGE_ANNUAL_REAL_EARNINGS_FOR_SP500_FOR_10_YEARS},
    market_data::market_data_defs::{DailyMarketDataForPresets,MarketDataSeriesForSimulation},
    simulate::{plan_params_server::PlanParamsServer,process_plan_params_server::process_plan_params_server},
    wire::{WireSimulationArgs,wire_simulation_args}};
use std::{fs::File,path::PathBuf,ffi::{CString,c_char}};

unsafe extern "C" {
    fn cuda_research_horizon(months:u32,balance:f64,params:*const PlanParamsCuda,
        arrays:*const PlanParamsCuda_C_Arrays,ends:*const u32,output:*const c_char)->i32;
}
#[derive(Parser)]
struct Args {
    #[arg(long)] request:PathBuf,
    #[arg(long)] presets:PathBuf,
    #[arg(long)] schedule:PathBuf,
    #[arg(long)] output:PathBuf,
}
#[derive(Deserialize)]
struct Schedule { evaluation_months:u32, planning_months:u32, end_by_month:Vec<u32> }
fn run(a:Args)->Result<(),Box<dyn std::error::Error>> {
    if a.output.exists() {return Err("existing output".into())}
    let parent=a.output.parent().ok_or("directory")?.canonicalize()?;
    if parent.ancestors().any(|p|p.join(".git").exists()) {return Err("private directory".into())}
    let dest=CString::new(a.output.to_str().filter(|x|x.is_ascii()).ok_or("ASCII path required")?)?;
    let s:Schedule=serde_json::from_reader(File::open(a.schedule)?)?;
    if s.evaluation_months==0 || s.evaluation_months>1440 || s.planning_months>1440 ||
        s.end_by_month.len()!=s.evaluation_months as usize || s.end_by_month.iter().enumerate().any(|(m,e)|*e<=m as u32 || *e>s.planning_months) {return Err("schedule bounds".into())}
    let req=WireSimulationArgs::decode(std::fs::read(a.request)?.as_slice())?;
    if !matches!(req.market_daily_series_src,Some(wire_simulation_args::MarketDailySeriesSrc::Live(_))) {return Err("snapshot selector".into())}
    let balance=match req.current_portfolio_balance {Some(wire_simulation_args::CurrentPortfolioBalance::NoEstimate(x)) if x.is_finite() && x>=0.0=>x,_=>return Err("explicit balance".into())};
    match req.plan_params.advanced.sampling {Some(simulator::wire::wire_plan_params_server_advanced::Sampling::MonteCarlo(ref x)) if x.num_runs>0 && x.num_runs<=1000 && x.block_size>0=>(),_=>return Err("bounded Monte Carlo only".into())}
    let presets:Vec<DailyMarketDataForPresets>=serde_json::from_reader(File::open(a.presets)?)?;
    if presets.is_empty() || presets.windows(2).any(|w|w[0].closing_time_ms>=w[1].closing_time_ms) || req.timestamp_for_market_data_ms<presets[0].closing_time_ms || req.timestamp_for_market_data_ms-presets.last().unwrap().closing_time_ms>7*86400000 {return Err("snapshot dates".into())}
    for x in &presets {if [x.sp500.value,x.inflation.value,x.bond_rates.five_year,x.bond_rates.seven_year,x.bond_rates.ten_year,x.bond_rates.twenty_year,x.bond_rates.thirty_year].iter().any(|x|!x.is_finite()) || x.sp500.value<=0.0 {return Err("snapshot values".into())}}
    let data=MarketDataSeriesForSimulation {daily_market_data_for_presets_series:&presets,
        historical_monthly_returns_info_series:&HISTORICAL_MONTHLY_RETURNS,
        average_annual_real_earnings_for_sp500_for_10_years_series:&AVERAGE_ANNUAL_REAL_EARNINGS_FOR_SP500_FOR_10_YEARS};
    let params:PlanParamsServer=req.plan_params.into();
    let mut processed=process_plan_params_server(&req.percentiles,&params,&data.for_timestamp(req.timestamp_for_market_data_ms));
    let mut cuda=processed.into_cuda(&params);
    if s.planning_months<cuda.ages.simulation_months.num_months {return Err("planning arrays cannot truncate original".into())}
    let n=s.planning_months as usize;
    // Scope: retain original goal/risk arrays through age90; zero cashflows and
    // hold terminal risk thereafter. No mortality, pay or liability is invented.
    for x in [&mut processed.amount_timed.future_savings,&mut processed.amount_timed.income_during_retirement,
        &mut processed.amount_timed.essential_expenses,&mut processed.amount_timed.discretionary_expenses] {x.total_by_mfn.resize(n,0.0);}
    let risk=&mut processed.risk.tpaw.rra_unclamped_including_pos_infinity_by_mfn_fcuda;
    risk.resize(n,*risk.last().ok_or("risk")?);
    let tilt=&mut processed.risk.spaw.monthly_spending_tilt_by_mfn_fcuda;tilt.resize(n,*tilt.last().ok_or("tilt")?);
    let alloc=&mut processed.risk.spaw_and_swr.stock_allocation_savings_portfolio_by_mfn_fcuda;alloc.resize(n,*alloc.last().ok_or("allocation")?);
    cuda.ages.simulation_months.num_months=s.planning_months;
    let arrays:PlanParamsCuda_C_Arrays=(&mut processed).into();
    let code=unsafe{cuda_research_horizon(s.evaluation_months,balance,&cuda,&arrays,s.end_by_month.as_ptr(),dest.as_ptr())};
    if code!=0 {return Err("research execution".into())}
    Ok(())
}
fn main(){std::panic::set_hook(Box::new(|_|{}));if std::panic::catch_unwind(||run(Args::parse()).is_ok()).unwrap_or(false){println!("Offline horizon paths saved privately")}else{eprintln!("Offline horizon execution failed; no financial values logged");std::process::exit(2)}}
