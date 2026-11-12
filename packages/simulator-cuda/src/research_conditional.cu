#include "src/simulate/run/research_conditional.h"
#include "src/public_headers/plan_params_cuda.h"
#include "src/simulate/plan_params_cuda_vectors.h"
#include "src/simulate/cuda_process_sampling.h"
#include "src/utils/cuda_utils.h"
#include "src/utils/run_mfn_indexing.h"
#include <fstream>
#include <iomanip>
extern "C" int cuda_research_conditional_notice(uint32_t months,CURRENCY balance,
 const PlanParamsCuda* p,const PlanParamsCuda_C_Arrays* arrays,CURRENCY threshold,uint32_t notice_months,const char* pathfile,const char* decisionfile){
 try{
  std::array<PlanParamsCuda_Vectors,3> v;
  std::array<uint32_t,3> starts;
  for(int i=0;i<3;++i){
   if(p[i].advanced.strategy!=PlanParamsCuda::Advanced::Strategy_TPAW || p[i].ages.simulation_months.num_months!=months)return 2;
   v[i]=get_plan_params_cuda_vectors(arrays[i],months);starts[i]=p[i].ages.simulation_months.withdrawal_start_month;
  }
  auto sampling=cuda_process_sampling(p[0].advanced.sampling,v[0].historical_returns_series.size(),months,months);
  thrust::device_vector<HistoricalReturnsCuda> history(v[0].historical_returns_series);
  auto returns=cuda_process_historical_returns(sampling,months,history,p[0].advanced.return_stats_for_planning.expected_returns_at_month_0);
  std::array<Cuda_Processed_TPAW_Run_x_MFNSimulated_x_MFN,3> processed;
  std::array<thrust::device_vector<CURRENCY>,3> income,essential,discretionary;
  for(int i=0;i<3;++i){
   processed[i]=cuda_process_tpaw_run_x_mfn_simulated_x_mfn(sampling.num_runs,months,months,
    v[i].income_combined_by_mfn,v[i].essential_expenses_by_mfn,v[i].discretionary_expenses_by_mfn,
    v[i].tpaw_rra_including_pos_infinity_by_mfn,p[i].advanced.return_stats_for_planning.annual_empirical_log_variance_stocks,
    p[i].risk.tpaw.time_preference,p[i].risk.tpaw.annual_additional_spending_tilt,p[i].risk.tpaw.legacy_rra_including_pos_infinity,
    p[i].adjustments_to_spending.tpaw_and_spaw.legacy,returns.expected_returns_by_mfn_simulated_for_expected_run,
    returns.expected_returns_by_run_by_mfn_simulated);
   income[i]=v[i].income_combined_by_mfn;essential[i]=v[i].essential_expenses_by_mfn;discretionary[i]=v[i].discretionary_expenses_by_mfn;
  }
  auto r=tpaw::run_conditional(sampling.num_runs,months,balance,starts,p[0].adjustments_to_spending.tpaw_and_spaw.spending_ceiling,
   p[0].adjustments_to_spending.tpaw_and_spaw.spending_floor,p[0].advanced.return_stats_for_planning.expected_returns_at_month_0,
   threshold,income,essential,discretionary,returns.historical_returns_by_run_by_mfn_simulated,processed,notice_months);
  auto b=device_vector_to_host(r.paths.by_run_by_mfn_simulated_month_major_balance_start);
  auto g=device_vector_to_host(r.paths.by_run_by_mfn_simulated_month_major_withdrawals_general);
  auto t=device_vector_to_host(r.paths.by_run_by_mfn_simulated_month_major_withdrawals_total);
  auto allocation=device_vector_to_host(r.paths.by_run_by_mfn_simulated_month_major_after_withdrawals_allocation_savings_portfolio);
  auto end=device_vector_to_host(r.paths.by_run_ending_balance);
  auto indices=device_vector_to_host(sampling.index_by_run_by_mfn_simulated);
  auto realized=device_vector_to_host(returns.historical_returns_by_run_by_mfn_simulated);
  std::ofstream f(pathfile,std::ios::binary),d(decisionfile,std::ios::binary);if(!f||!d)return 3;
  f<<std::setprecision(17)<<"month,run,balance_start,general,total,balance_end,sample_index,stock_return,bond_return,stock_fraction,income_applied\n";
  for(uint32_t m=0;m<months;++m)for(uint32_t n=0;n<sampling.num_runs;++n){
   auto i=MonthMajor::get_run_by_mfn_index(r.paths.num_runs_padded,n,m);auto j=get_run_by_mfn_index(sampling.num_runs,months,n,m);
   auto e=m+1<months?b[MonthMajor::get_run_by_mfn_index(r.paths.num_runs_padded,n,m+1)]:end[n];
   uint32_t active=0;
   for(uint32_t k=0;k<2;++k)if(m>=starts[k]-notice_months && r.retirement_month[n]>starts[k])active=k+1;
   f<<m<<','<<n<<','<<b[i]<<','<<g[i]<<','<<t[i]<<','<<e<<','<<indices[j]<<','<<realized[j].stocks<<','<<realized[j].bonds<<','<<allocation[i]<<','<<v[active].income_combined_by_mfn[m]<<'\n';
  }
  d<<std::setprecision(17)<<"run,retirement_month,forced_below_threshold,would_still_work_if_threshold_required,review0,review1,review2,notice_months,commitment_month,actual_initial_spending,actual_initial_below_threshold\n";
  for(uint32_t n=0;n<sampling.num_runs;++n){
   auto exit=r.retirement_month[n];auto actual=g[MonthMajor::get_run_by_mfn_index(r.paths.num_runs_padded,n,exit)];
   d<<n<<','<<exit<<','<<r.forced_below_threshold[n]<<','<<r.forced_below_threshold[n]<<','<<r.reviewed_spending[n*3]<<','<<r.reviewed_spending[n*3+1]<<','<<r.reviewed_spending[n*3+2]<<','<<notice_months<<','<<exit-notice_months<<','<<actual<<','<<(actual<threshold)<<'\n';
  }
  return f.good()&&d.good()?0:3;
 }catch(...){return 2;}
}

// Preserve the original research ABI for already-built frictionless callers.
extern "C" int cuda_research_conditional(uint32_t months,CURRENCY balance,
 const PlanParamsCuda* p,const PlanParamsCuda_C_Arrays* arrays,CURRENCY threshold,
 const char* pathfile,const char* decisionfile){
 return cuda_research_conditional_notice(months,balance,p,arrays,threshold,0,pathfile,decisionfile);
}
