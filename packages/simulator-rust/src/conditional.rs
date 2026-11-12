//! Separate local research executable; no telemetry/server/cloud initialization.
use clap::Parser;use prost::Message;
use simulator::{cuda_bridge::{PlanParamsCuda,PlanParamsCuda_C_Arrays},
 historical_monthly_returns::{HISTORICAL_MONTHLY_RETURNS,data::average_annual_real_earnings_for_sp500_for_10_years::AVERAGE_ANNUAL_REAL_EARNINGS_FOR_SP500_FOR_10_YEARS},
 market_data::market_data_defs::{DailyMarketDataForPresets,MarketDataSeriesForSimulation},
 simulate::{plan_params_server::PlanParamsServer,process_plan_params_server::process_plan_params_server},
 wire::{WireSimulationArgs,wire_simulation_args}};
use std::{path::PathBuf,fs::File,ffi::{CString,c_char}};
unsafe extern "C" {fn cuda_research_conditional_notice(months:u32,balance:f64,p:*const PlanParamsCuda,a:*const PlanParamsCuda_C_Arrays,threshold:f64,notice_months:u32,paths:*const c_char,decisions:*const c_char)->i32;}
#[derive(Parser)]struct Args{
 #[arg(long)] requests:PathBuf,#[arg(long)] presets:PathBuf,#[arg(long)] threshold:f64,#[arg(long)] output_prefix:PathBuf,
 #[arg(long,default_value_t=0)] notice_months:u32,
}
fn run(a:Args)->Result<(),Box<dyn std::error::Error>>{
 if !a.threshold.is_finite()||a.threshold<0.0{return Err("threshold".into())}
 let prefix=a.output_prefix.to_str().filter(|x|x.is_ascii()).ok_or("ASCII output")?;
 let paths=PathBuf::from(format!("{prefix}-paths.csv"));let decisions=PathBuf::from(format!("{prefix}-decisions.csv"));
 if paths.exists()||decisions.exists(){return Err("existing output".into())}
 let parent=a.output_prefix.parent().ok_or("directory")?.canonicalize()?;
 if parent.ancestors().any(|p|p.join(".git").exists()){return Err("private directory".into())}
 let files:Vec<PathBuf>=serde_json::from_reader(File::open(a.requests)?)?;
 if files.len()!=3{return Err("three candidate dates required".into())}
 let requests:Vec<WireSimulationArgs>=files.iter().map(|p|Ok(WireSimulationArgs::decode(std::fs::read(p)?.as_slice())?)).collect::<Result<_,Box<dyn std::error::Error>>>()?;
 let base=&requests[0];let months=base.plan_params.ages.simulation_months.num_months;
 if months==0||months>1440||a.notice_months>12||a.notice_months>base.plan_params.ages.simulation_months.withdrawal_start_month{return Err("horizon/notice".into())}
 let balance=match base.current_portfolio_balance{Some(wire_simulation_args::CurrentPortfolioBalance::NoEstimate(x)) if x.is_finite()&&x>=0.0=>x,_=>return Err("explicit balance".into())};
 match base.plan_params.advanced.sampling{Some(simulator::wire::wire_plan_params_server_advanced::Sampling::MonteCarlo(ref s))if s.num_runs>0&&s.num_runs<=1000&&s.block_size>0=>(),_=>return Err("bounded MC required".into())}
 for (i,req) in requests.iter().enumerate(){
  if req.timestamp_for_market_data_ms!=base.timestamp_for_market_data_ms||req.current_portfolio_balance!=base.current_portfolio_balance||req.percentiles!=base.percentiles||req.plan_params.advanced!=base.plan_params.advanced||req.plan_params.risk!=base.plan_params.risk||req.plan_params.constants!=base.plan_params.constants||req.plan_params.ages.longer_lived_person!=base.plan_params.ages.longer_lived_person||req.plan_params.ages.simulation_months.num_months!=months||req.plan_params.ages.simulation_months.withdrawal_start_month!=base.plan_params.ages.simulation_months.withdrawal_start_month+12*i as u32{return Err("unmatched controls".into())}
  if !matches!(req.market_daily_series_src,Some(wire_simulation_args::MarketDailySeriesSrc::Live(_))){return Err("snapshot selector".into())}
 }
 let presets:Vec<DailyMarketDataForPresets>=serde_json::from_reader(File::open(a.presets)?)?;
 if presets.is_empty()||presets.windows(2).any(|w|w[0].closing_time_ms>=w[1].closing_time_ms)||base.timestamp_for_market_data_ms<presets[0].closing_time_ms||base.timestamp_for_market_data_ms-presets.last().unwrap().closing_time_ms>7*86400000{return Err("snapshot dates".into())}
 for row in &presets{if [row.sp500.value,row.inflation.value,row.bond_rates.five_year,row.bond_rates.seven_year,row.bond_rates.ten_year,row.bond_rates.twenty_year,row.bond_rates.thirty_year].iter().any(|x|!x.is_finite())||row.sp500.value<=0.0{return Err("snapshot values".into())}}
 let data=MarketDataSeriesForSimulation{daily_market_data_for_presets_series:&presets,historical_monthly_returns_info_series:&HISTORICAL_MONTHLY_RETURNS,average_annual_real_earnings_for_sp500_for_10_years_series:&AVERAGE_ANNUAL_REAL_EARNINGS_FOR_SP500_FOR_10_YEARS};
 let mut processed=Vec::new();let mut cuda=Vec::new();
 for req in &requests{let p:PlanParamsServer=req.plan_params.clone().into();let x=process_plan_params_server(&req.percentiles,&p,&data.for_timestamp(req.timestamp_for_market_data_ms));
  // This pinned Rust pipeline sets these fields to zero. The CUDA update is
  // inclusive, so a future nonzero implementation needs explicit date alignment
  // before using it in a beginning-of-month financial decision.
  if x.historical_returns.cuda.iter().any(|v|v.stocks.expected_return_change!=0.0||v.bonds.expected_return_change!=0.0){return Err("expected-return changes require timing audit".into())}
  cuda.push(x.into_cuda(&p));processed.push(x);}
 let arrays:Vec<PlanParamsCuda_C_Arrays>=processed.iter_mut().map(|x|x.into()).collect();
 let pathc=CString::new(paths.to_str().ok_or("path")?)?;let decisionc=CString::new(decisions.to_str().ok_or("path")?)?;
 let code=unsafe{cuda_research_conditional_notice(months,balance,cuda.as_ptr(),arrays.as_ptr(),a.threshold,a.notice_months,pathc.as_ptr(),decisionc.as_ptr())};
 if code!=0{return Err("conditional execution".into())}Ok(())
}
fn main(){std::panic::set_hook(Box::new(|_|{}));if std::panic::catch_unwind(||run(Args::parse()).is_ok()).unwrap_or(false){println!("Offline conditional paths and decisions saved privately")}else{eprintln!("Offline conditional research failed; no financial values logged");std::process::exit(2)}}
