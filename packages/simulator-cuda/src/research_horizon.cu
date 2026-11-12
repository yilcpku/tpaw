// Separate offline research entry; original production ABI remains unchanged.
#include "src/public_headers/plan_params_cuda.h"
#include "src/simulate/plan_params_cuda_vectors.h"
#include "src/simulate/cuda_process_sampling.h"
#include "src/simulate/cuda_process_historical_returns.h"
#include "src/simulate/cuda_process_run_x_mfn_simulated_x_mfn/cuda_process_tpaw_run_x_mfn_simulated_x_mfn.h"
#include "src/simulate/run/run_tpaw.h"
#include "src/utils/cuda_utils.h"
#include "src/utils/run_mfn_indexing.h"
#include <fstream>
#include <iomanip>
#include "extern/doctest.h"

extern "C" int cuda_research_horizon(
    uint32_t months, CURRENCY balance, const PlanParamsCuda *params,
    const PlanParamsCuda_C_Arrays *arrays, const uint32_t *end_by_month,
    const char *output_file) {
  try {
    if (params->advanced.strategy != PlanParamsCuda::Advanced::Strategy_TPAW) return 2;
    const auto v = get_plan_params_cuda_vectors(*arrays, params->ages.simulation_months.num_months);
    const std::vector<uint32_t> ends(end_by_month, end_by_month + months);
    const auto sampled = cuda_process_sampling(params->advanced.sampling,
        v.historical_returns_series.size(), params->ages.simulation_months.num_months, months);
    const thrust::device_vector<HistoricalReturnsCuda> history(v.historical_returns_series);
    const auto returns = cuda_process_historical_returns(sampled, months, history,
        params->advanced.return_stats_for_planning.expected_returns_at_month_0);
    const auto processed = cuda_process_tpaw_run_x_mfn_simulated_x_mfn(sampled.num_runs, months,
        params->ages.simulation_months.num_months, v.income_combined_by_mfn,
        v.essential_expenses_by_mfn, v.discretionary_expenses_by_mfn,
        v.tpaw_rra_including_pos_infinity_by_mfn,
        params->advanced.return_stats_for_planning.annual_empirical_log_variance_stocks,
        params->risk.tpaw.time_preference, params->risk.tpaw.annual_additional_spending_tilt,
        params->risk.tpaw.legacy_rra_including_pos_infinity,
        params->adjustments_to_spending.tpaw_and_spaw.legacy,
        returns.expected_returns_by_mfn_simulated_for_expected_run,
        returns.expected_returns_by_run_by_mfn_simulated, ends);
    const thrust::device_vector<CURRENCY> income(v.income_combined_by_mfn), essential(v.essential_expenses_by_mfn), discretionary(v.discretionary_expenses_by_mfn);
    const auto paths = tpaw::run(sampled.num_runs, months, balance,
        params->ages.simulation_months.withdrawal_start_month,
        params->adjustments_to_spending.tpaw_and_spaw.spending_ceiling,
        params->adjustments_to_spending.tpaw_and_spaw.spending_floor,
        params->advanced.return_stats_for_planning.expected_returns_at_month_0,
        income, essential, discretionary,
        returns.historical_returns_by_run_by_mfn_simulated, processed);
    const auto balances = device_vector_to_host(paths.by_run_by_mfn_simulated_month_major_balance_start);
    const auto general = device_vector_to_host(paths.by_run_by_mfn_simulated_month_major_withdrawals_general);
    const auto total = device_vector_to_host(paths.by_run_by_mfn_simulated_month_major_withdrawals_total);
    const auto allocation = device_vector_to_host(paths.by_run_by_mfn_simulated_month_major_after_withdrawals_allocation_savings_portfolio);
    const auto ending = device_vector_to_host(paths.by_run_ending_balance);
    const auto indices = device_vector_to_host(sampled.index_by_run_by_mfn_simulated);
    const auto realized = device_vector_to_host(returns.historical_returns_by_run_by_mfn_simulated);
    std::ofstream file(output_file, std::ios::out | std::ios::binary);
    if (!file) return 3;
    file << std::setprecision(17) << "month,run,balance_start,general,total,stock_fraction,balance_end,sample_index,stock_return,bond_return\n";
    for (uint32_t m=0; m<months; ++m) for (uint32_t r=0; r<sampled.num_runs; ++r) {
      const auto i=MonthMajor::get_run_by_mfn_index(paths.num_runs_padded,r,m);
      const auto j=get_run_by_mfn_index(sampled.num_runs,months,r,m);
      const auto end=m+1<months ? balances[MonthMajor::get_run_by_mfn_index(paths.num_runs_padded,r,m+1)] : ending[r];
      file << m << ',' << r << ',' << balances[i] << ',' << general[i] << ',' << total[i] << ',' << allocation[i]
           << ',' << end << ',' << indices[j] << ',' << realized[j].stocks << ',' << realized[j].bonds << '\n';
    }
    return file.good() ? 0 : 3;
  } catch (...) { return 2; }
}

TEST_CASE("research_horizon::annuity_deadline_update_and_continuity") {
  const uint32_t planning=24,months=12,runs=1;
  const std::vector<CURRENCY> zero(planning,0.0);
  const std::vector<FLOAT> risk(planning,INFINITY);
  const thrust::device_vector<MonthlyAndAnnual<StocksAndBondsFLOAT>> expected(
      months, MonthlyAndAnnual<StocksAndBondsFLOAT>{{0.0f,0.0f},{0.0f,0.0f}});
  std::vector<uint32_t> ends(months,12);
  for (uint32_t m=6;m<months;++m) ends[m]=18;
  const auto data=cuda_process_tpaw_run_x_mfn_simulated_x_mfn(runs,months,planning,
      zero,zero,zero,risk,0.04f,0.0f,0.0f,INFINITY,0.0,expected,expected,ends);
  const auto denominators=device_vector_to_host(data.for_normal_run);
  CHECK(denominators[0].cumulative_1_plus_g_over_1_plus_r==12.0f);
  CHECK(denominators[6].cumulative_1_plus_g_over_1_plus_r==12.0f);
  const thrust::device_vector<CURRENCY> zero_gpu(zero);
  const thrust::device_vector<StocksAndBondsFLOAT> realized(months,StocksAndBondsFLOAT{0.0f,0.0f});
  const auto result=tpaw::run(runs,months,1200.0,0,OptCURRENCY{0,0},OptCURRENCY{0,0},
      StocksAndBondsFLOAT{0.0f,0.0f},zero_gpu,zero_gpu,zero_gpu,realized,data);
  CHECK(result.get_single(0,0).withdrawals_general==doctest::Approx(100.0));
  CHECK(result.get_single(0,6).balance_start==doctest::Approx(600.0));
  CHECK(result.get_single(0,6).withdrawals_general==doctest::Approx(50.0));
  CHECK(static_cast<CURRENCY>(result.by_run_ending_balance[0])==doctest::Approx(300.0));
  auto invalid=ends;invalid[6]=6;
  CHECK_THROWS(cuda_process_tpaw_run_x_mfn_simulated_x_mfn(runs,months,planning,
      zero,zero,zero,risk,0.04f,0.0f,0.0f,INFINITY,0.0,expected,expected,invalid));
  std::vector<StocksAndBondsFLOAT> shock(months,StocksAndBondsFLOAT{0.0f,0.0f});
  shock[9].bonds=-0.5f;
  const thrust::device_vector<StocksAndBondsFLOAT> shock_gpu(shock);
  const auto changed=tpaw::run(runs,months,1200.0,0,OptCURRENCY{0,0},OptCURRENCY{0,0},
      StocksAndBondsFLOAT{0.0f,0.0f},zero_gpu,zero_gpu,zero_gpu,shock_gpu,data);
  for (uint32_t m=0;m<=9;++m) {
    CHECK(changed.get_single(0,m).balance_start==result.get_single(0,m).balance_start);
    CHECK(changed.get_single(0,m).withdrawals_general==result.get_single(0,m).withdrawals_general);
  }
  CHECK(changed.get_single(0,10).balance_start==doctest::Approx(result.get_single(0,10).balance_start*0.5));
}
