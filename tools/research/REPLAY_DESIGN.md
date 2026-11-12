# File-only replay: implemented boundary and remaining gate

The separate `tpaw-replay` binary bypasses `src/main.rs`. Its entry point does not
initialize dotenv, CONFIG, Sentry, cloud clients or an HTTP listener. It accepts
local files, calls the existing Rust processing and CUDA implementation, then
writes a new private result protobuf. No production credentials are required.

## Flow

1. `EncodeReplay.ts` reads a private prepared case. It applies the author's v30
   `planParamsGuard`, `normalizePlanParams`, `getPlanParamsServer`, and existing
   `WireSimulationArgs` encoder. It requires explicit clock, timezone, seed/count,
   and an explicit current balance. It writes an uncompressed request protobuf
   and SHA-256 outside Git. Deflate is only an HTTP transport step, so file replay
   does not need it.
2. `tpaw-replay --request request.pb --presets presets.json --output result.pb`
   reads an immutable upstream-schema `DailyMarketDataForPresets` JSON array.
   The request's `live` selector means "use this supplied snapshot unchanged" in
   this executable; no downloader is invoked. The compiled historical-return and
   real-earnings series retain upstream timestamp selection behavior.
3. Rust calls the existing `simulate()` and `into_wire()` functions. Current
   support requires `no_estimate`: VT/BND balance-estimation replay is a later
   explicit extension, not an automatic substitution. Result schema/scales remain
   the upstream protobuf schema. Existing outputs and Git-checkout destinations
   are refused. Errors print generic statuses, never plan values.
4. `InspectReplay.ts request.pb result.pb result.json [repeat.pb]` validates
   simulation count, dimensions and finite result arrays, checks for positive
   retirement consumption, and saves private decoded JSON. Repeat comparisons
   exclude timing fields and normalize only id-keyed record order. Rust HashMaps
   serialize those records in arbitrary order; financial arrays and values remain
   in the comparison. Raw result bytes/hashes are retained separately.

Replay currently limits Monte Carlo requests to 10,000 paths, block size >0 and
at most 120 years of monthly observations. It validates finite preset values,
ordered unique dates, a covered starting date and at most seven days of staleness.
These checks are bounded research safeguards, not complete hostile-input auditing.
The author guard/normalizer remains a required preceding step.

## Windows linking and ABI

`Build-CudaLibrary.ps1` builds a separate optimized DLL/import library with the
existing CUDA 13.3/MSVC toolchain. Its exports are the existing `cuda_simulate`
and `cuda_get_empirical_annual_non_log_mean` functions. The Rust build script
accepts process-local `CUDA_PATH` and `TPAW_CUDA_LIB_DIR` on Windows, retaining
the original Linux search paths on other targets.

The old generated file contains unused Linux aliases, but the used public seed
fields already use u64. Independent Windows-target bindgen review found **21
shared public structs/unions with identical field declarations**, zero opaque
fields in those allowed types; the only missing old struct was unused `__fsid_t`.
Existing generated size/offset assertions compile on Windows. Targeted tests also
verify the 24-byte sampling struct, seed offset 0, run-count offset 8, and protobuf
round-trip of a seed above 32 bits. No seed-width defect was demonstrated; the
working bridge was not replaced just to remove unused aliases. Bindgen reports
warnings for unrelated compiler builtins, retained in its review log.

## Verification and reproducibility

A computable local benchmark is distinct from reproducing a historical website
result. Freeze source/build identity, daily presets, return-series version,
request bytes, evaluation clock, seed/count and result bytes independently.
Absent original inputs must remain explicit differences; numerical proximity is
not proof of parity. Personal experiment chronology, amounts, outputs and local
machine paths are deliberately excluded from this source document.

The current-source CUDA suite passes42 correctness cases/490 assertions with19
benchmarks skipped. The generic Python research helpers pass23 tests. The full
upstream Rust suite and production Linux/deployment parity are not asserted.
Use the isolated tool homes and process-local build variables appropriate to the
local machine; the scripts do not require persistent system PATH changes.

Separate full-path rolling-horizon and conditional-date experiments are described
in [HORIZON_EXPERIMENT.md](HORIZON_EXPERIMENT.md) and
[CONDITIONAL_RETIREMENT.md](CONDITIONAL_RETIREMENT.md). Their mortality censoring,
finite-horizon exhaustion and known-income coverage remain explicit. The CNY
account model, Astryx interface and edited-input native control are documented in
[the local lab](../local-lab/README.md), with current scope and verification in
[its completion audit](../local-lab/REQUIREMENTS.md).
