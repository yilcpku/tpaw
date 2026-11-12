#pragma once
#include "run_tpaw.h"
#include <array>
namespace tpaw {
struct ConditionalResult {
 RunResultPadded paths;
 std::vector<uint32_t> retirement_month;
 std::vector<CURRENCY> reviewed_spending;
 std::vector<uint32_t> forced_below_threshold;
};
ConditionalResult run_conditional(uint32_t runs,uint32_t months,CURRENCY balance,
 const std::array<uint32_t,3>& starts,OptCURRENCY ceiling,OptCURRENCY floor,
 StocksAndBondsFLOAT expected,CURRENCY threshold,
 const std::array<thrust::device_vector<CURRENCY>,3>& income,
 const std::array<thrust::device_vector<CURRENCY>,3>& essential,
 const std::array<thrust::device_vector<CURRENCY>,3>& discretionary,
 const thrust::device_vector<StocksAndBondsFLOAT>& realized,
 const std::array<Cuda_Processed_TPAW_Run_x_MFNSimulated_x_MFN,3>& processed,
 uint32_t notice_months=0);
}
