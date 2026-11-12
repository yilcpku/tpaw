//! Offline, file-only replay: deliberately does not initialize CONFIG, dotenv,
//! Sentry, an HTTP listener, or any market-data downloader.
use clap::Parser;
use prost::Message;
use simulator::{
    historical_monthly_returns::{HISTORICAL_MONTHLY_RETURNS,
        data::average_annual_real_earnings_for_sp500_for_10_years::AVERAGE_ANNUAL_REAL_EARNINGS_FOR_SP500_FOR_10_YEARS},
    market_data::market_data_defs::{DailyMarketDataForPresets, MarketDataSeriesForSimulation},
    simulate::{simulate, plan_params_server::PlanParamsServer},
    wire::{wire_simulation_args, WireSimulationArgs},
};
use std::{fs::{File, OpenOptions}, io::{Read, Write}, path::PathBuf, time::Instant};

#[derive(Parser)]
struct Args {
    /// Uncompressed, normalized WireSimulationArgs protobuf; never a raw plan JSON.
    #[arg(long)] request: PathBuf,
    /// Immutable JSON array with the upstream DailyMarketDataForPresets schema.
    #[arg(long)] presets: PathBuf,
    /// New private output protobuf. Existing files are never overwritten.
    #[arg(long)] output: PathBuf,
}

fn run(args: Args) -> Result<(), Box<dyn std::error::Error>> {
    if args.output.exists() { return Err("output already exists".into()); }
    let parent = args.output.parent().ok_or("missing output directory")?.canonicalize()?;
    if parent.ancestors().any(|p| p.join(".git").exists()) {
        return Err("private output cannot be inside a Git checkout".into());
    }
    let mut bytes = Vec::new();
    File::open(&args.request)?.take(32 * 1024 * 1024).read_to_end(&mut bytes)?;
    let request = WireSimulationArgs::decode(bytes.as_slice())?;
    let balance = match request.current_portfolio_balance {
        Some(wire_simulation_args::CurrentPortfolioBalance::NoEstimate(value)) if value.is_finite() && value >= 0.0 => value,
        _ => return Err("replay requires an explicit finite no_estimate balance; estimation is not yet supported".into()),
    };
    if !matches!(request.market_daily_series_src, Some(wire_simulation_args::MarketDailySeriesSrc::Live(_))) {
        return Err("replay uses the supplied snapshot directly; synthetic/live downloads are disabled".into());
    }
    if request.percentiles.is_empty() || request.percentiles.iter().any(|p| *p > 100) {
        return Err("invalid percentile request".into());
    }
    let months = request.plan_params.ages.simulation_months.num_months;
    if months == 0 || months > 120 * 12 || request.plan_params.ages.simulation_months.withdrawal_start_month >= months {
        return Err("unsupported simulation horizon".into());
    }
    if let Some(simulator::wire::wire_plan_params_server_advanced::Sampling::MonteCarlo(ref spec)) =
        request.plan_params.advanced.sampling {
        if spec.num_runs == 0 || spec.num_runs > 10000 || spec.block_size == 0 {
            return Err("unsupported sample count or block size".into());
        }
    }
    let presets: Vec<DailyMarketDataForPresets> = serde_json::from_reader(File::open(&args.presets)?)?;
    if presets.is_empty() || presets.windows(2).any(|w| w[0].closing_time_ms >= w[1].closing_time_ms) {
        return Err("presets must be nonempty, strictly ordered and unique".into());
    }
    for row in &presets {
        let values = [row.inflation.value, row.sp500.value, row.bond_rates.five_year,
            row.bond_rates.seven_year, row.bond_rates.ten_year,
            row.bond_rates.twenty_year, row.bond_rates.thirty_year];
        if values.iter().any(|x| !x.is_finite()) || row.sp500.value <= 0.0 {
            return Err("invalid preset value".into());
        }
    }
    if request.timestamp_for_market_data_ms < presets[0].closing_time_ms {
        return Err("snapshot does not cover requested market-data date".into());
    }
    if request.timestamp_for_market_data_ms - presets.last().unwrap().closing_time_ms > 7 * 24 * 60 * 60 * 1000 {
        return Err("snapshot is more than seven days stale at the evaluation date".into());
    }
    // No download or synthetic transformation: use exactly the supplied series.
    let data = MarketDataSeriesForSimulation {
        daily_market_data_for_presets_series: &presets,
        historical_monthly_returns_info_series: &HISTORICAL_MONTHLY_RETURNS,
        average_annual_real_earnings_for_sp500_for_10_years_series:
            &AVERAGE_ANNUAL_REAL_EARNINGS_FOR_SP500_FOR_10_YEARS,
    };
    let params: PlanParamsServer = request.plan_params.into();
    let start = Instant::now();
    let (result, processed) = simulate(balance, &request.percentiles, months, &params,
                                      request.timestamp_for_market_data_ms, &data);
    let elapsed = start.elapsed().as_millis() as i64;
    let output = result.into_wire(None, processed, 0, elapsed, elapsed).encode_to_vec();
    OpenOptions::new().write(true).create_new(true).open(args.output)?.write_all(&output)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use simulator::wire::WirePlanParamsServerSamplingMonteCarlo;
    use simulator::cuda_bridge::PlanParamsCuda_Advanced_Sampling_MonteCarlo;

    #[test]
    fn protobuf_preserves_seed_above_32_bits() {
        let seed = (1_u64 << 48) + 123;
        let spec = WirePlanParamsServerSamplingMonteCarlo {
            seed, num_runs: 1000, block_size: 60, stagger_run_starts: true,
        };
        let decoded = WirePlanParamsServerSamplingMonteCarlo::decode(spec.encode_to_vec().as_slice()).unwrap();
        assert_eq!(decoded.seed, seed);
        assert_eq!(decoded.num_runs, 1000);
        assert!(decoded.stagger_run_starts);
    }

    #[test]
    fn public_sampling_ffi_uses_64_bit_seed_and_expected_layout() {
        let spec = PlanParamsCuda_Advanced_Sampling_MonteCarlo {
            seed: (1_u64 << 48) + 123, num_runs: 1000, block_size: 60, stagger_run_starts: 1,
        };
        assert_eq!(spec.seed >> 48, 1);
        assert_eq!(std::mem::size_of::<PlanParamsCuda_Advanced_Sampling_MonteCarlo>(), 24);
        assert_eq!(std::mem::offset_of!(PlanParamsCuda_Advanced_Sampling_MonteCarlo, seed), 0);
        assert_eq!(std::mem::offset_of!(PlanParamsCuda_Advanced_Sampling_MonteCarlo, num_runs), 8);
    }
}

fn main() {
    // Never send raw errors/panics to a telemetry service or console: they may
    // contain plan values. Local diagnostics belong in explicitly private files.
    std::panic::set_hook(Box::new(|_| {}));
    let result = std::panic::catch_unwind(|| run(Args::parse()).is_ok());
    match result {
        Ok(true) => println!("Offline replay completed; result saved locally"),
        _ => { eprintln!("Offline replay failed validation or execution; no plan data logged"); std::process::exit(2); }
    }
}
