"""Optional Windows64 bridge to the pinned offline CUDA research export.

No binary downloads, network or plan normalization. The caller must supply a
hash-verified processed native export and matching explicitly pinned local DLL.
The original CUDA circular sampler is retained in this separate benchmark.
"""
import ctypes as C
import hashlib
import math
import os
from pathlib import Path
import re
from .storage import private_root

U=C.c_uint32;F=C.c_float;D=C.c_double


class Pair(C.Structure): _fields_=[("stocks",F),("bonds",F)]
class Ages(C.Structure): _fields_=[("months",U),("retirement",U)]
class Opt(C.Structure): _fields_=[("is_set",U),("value",D)]
class Adjustments(C.Structure): _fields_=[("ceiling",Opt),("floor",Opt),("legacy",D)]
class RiskTPAW(C.Structure): _fields_=[("rho",F),("tilt",F),("legacy_rra",F)]
class RiskSWR(C.Structure): _fields_=[("kind",U),("value",D)]
class Risk(C.Structure): _fields_=[("tpaw",RiskTPAW),("swr",RiskSWR)]
class ReturnStats(C.Structure): _fields_=[("expected",Pair),("variance",F)]
class MonteCarlo(C.Structure): _fields_=[("seed",C.c_uint64),("runs",U),("block",U),("stagger",U)]
class SamplingData(C.Union): _fields_=[("mc",MonteCarlo),("historical",U)]
class Sampling(C.Structure): _fields_=[("kind",U),("data",SamplingData)]
class Advanced(C.Structure): _fields_=[("returns",ReturnStats),("sampling",Sampling),("strategy",U)]
class Params(C.Structure): _fields_=[("ages",Ages),("adjustments",Adjustments),("risk",Risk),("advanced",Advanced)]
class HistoricalPart(C.Structure): _fields_=[("returns",F),("expected_change",F)]
class Historical(C.Structure): _fields_=[("stocks",HistoricalPart),("bonds",HistoricalPart)]
class Arrays(C.Structure):
    _fields_=[("future",C.POINTER(D)),("income",C.POINTER(D)),("essential",C.POINTER(D)),("discretionary",C.POINTER(D)),
              ("rra",C.POINTER(F)),("tilt",C.POINTER(F)),("allocation",C.POINTER(F)),("percentile_count",U),
              ("percentiles",C.POINTER(U)),("history_count",U),("history",C.POINTER(Historical))]


def verify_abi():
    if C.sizeof(C.c_void_p)!=8: raise ValueError("Native bridge requires64-bit process")
    sizes={Opt:16,Risk:32,MonteCarlo:24,Sampling:32,Advanced:56,Params:136,Arrays:88,Historical:16}
    if any(C.sizeof(kind)!=size for kind,size in sizes.items()): raise ValueError("Pinned CUDA ABI layout differs")
    if (Params.adjustments.offset,Params.risk.offset,Params.advanced.offset,Advanced.sampling.offset)!=(8,48,80,16):
        raise ValueError("Pinned CUDA ABI offsets differ")


def adjusted_history(source:Path,processed:dict,case:dict):
    """Recover f32 source values before f64 log shift, as in original Rust.

    Uses serialized processed log means. Full export-to-original marginal checks
    must verify the possible serialization/reconstruction rounding difference.
    """
    entries=re.findall(r'RawMonthlyNonLogSeriesEntry::new\((\d+),\s*(\d+),\s*([^,]+),\s*([^\)]+)\)',source.read_text(encoding="utf-8"))
    if len(entries)!=processed["historicalReturns"]["stocks"]["stats"]["log"]["n"]:
        raise ValueError("Native historical version/length mismatch")
    result=[]; columns=[]
    for j,name in enumerate(("stocks","bonds")):
        logs=[math.log1p(F(float(row[j+2])).value) for row in entries]
        running=0.
        for value in logs: running+=value
        mean=running/len(logs)
        target=processed["historicalReturns"][name]["stats"]["log"]["mean"]
        if name=="stocks": scale=case["plan"]["advanced"]["returnsStatsForPlanning"]["standardDeviation"][name]["scale"]["log"]
        else: scale=case["plan"]["advanced"]["historicalReturnsAdjustment"]["standardDeviation"][name]["scale"]["log"]
        delta=mean-target
        values=[math.expm1(target+((value-delta)-target)*scale) for value in logs]
        # Check actual adjusted moments against the original processed export.
        adjusted=[math.log1p(v) for v in values]
        actual_mean=sum(adjusted)/len(adjusted)
        actual_var=sum((v-actual_mean)**2 for v in adjusted)/(len(adjusted)-1)
        expected=processed["historicalReturns"][name]["stats"]["log"]
        if not math.isclose(actual_mean,expected["mean"],abs_tol=1e-12) or not math.isclose(actual_var,expected["variance"],abs_tol=1e-12):
            raise ValueError("Reconstructed native historical moments differ")
        columns.append(values)
    for a,b in zip(*columns): result.append(Historical(HistoricalPart(a,0),HistoricalPart(b,0)))
    return (Historical*len(result))(*result)


def private_output_path(output:Path)->Path:
    if output.is_symlink() or output.exists():raise ValueError('Native output already exists or is a symbolic link')
    root=private_root(output.parent)
    canonical=output.resolve()
    if not canonical.is_relative_to(root):raise ValueError('Native output escapes verified private directory')
    try:str(canonical).encode('ascii')
    except UnicodeEncodeError:raise ValueError('Pinned Windows native export requires an ASCII private output directory') from None
    return canonical


def export_paths(case:dict,decoded:dict,retirement:int,dll:Path,dll_sha256:str,cuda_bin:Path,source:Path,output:Path,runs:int|None=None):
    verify_abi()
    if os.name!="nt": raise ValueError("Pinned native DLL requires Windows")
    if hashlib.sha256(dll.read_bytes()).hexdigest()!=dll_sha256: raise ValueError("Native DLL hash changed")
    output=private_output_path(output)
    p=decoded["result"]["planParamsProcessed"]; cash=p["amountTimed"]
    risk=p["risk"]["tpaw"];preferences=case["plan"]["risk"]["tpaw"]
    if set(p["adjustmentsToSpending"]["tpawAndSpaw"])!={"legacy"}:
        raise ValueError("Native adapter currently requires unconstrained spending")
    arrays_data=[(D*len(cash[k]["totalX100"]))(*(x/100 for x in cash[k]["totalX100"])) for k in
                 ("wealthFutureSavings","wealthIncomeDuringRetirement","extraExpensesEssential","extraExpensesDiscretionary")]
    n=len(arrays_data[0]); count=runs or decoded["result"]["numRuns"]
    if not 1<=count<=1000 or not 0<=retirement<n: raise ValueError("Native export bounds")
    rra=(F*n)(*risk["rraUnclampedIncludingPosInfinityByMfn"]);zero=(F*n)();percentiles=(U*3)(5,50,95)
    history=adjusted_history(source,p,case)
    arrays=Arrays(*arrays_data,rra,zero,zero,3,percentiles,len(history),history)
    r=p["returnsStatsForPlanning"]
    mu=[math.pow(1+r[name]["empiricalAnnualNonLogExpectedReturn"],1/12)-1 for name in ("stocks","bonds")]
    sampling=case["plan"]["advanced"]["sampling"]
    if sampling["type"]!="monteCarlo": raise ValueError("Native bridge requires Monte Carlo")
    spec=sampling["data"]
    params=Params(Ages(n,retirement),Adjustments(Opt(0,0),Opt(0,0),p["adjustmentsToSpending"]["tpawAndSpaw"]["legacy"]["target"]),
                  Risk(RiskTPAW(preferences["timePreference"],preferences["additionalAnnualSpendingTilt"],risk["legacyRraIncludingPosInfinity"]),RiskSWR(0,0)),
                  Advanced(ReturnStats(Pair(*mu),r["stocks"]["empiricalAnnualLogVariance"]),
                           Sampling(0,SamplingData(mc=MonteCarlo(case["run"]["seed"],count,spec["blockSize"]["inMonths"],int(spec["staggerRunStarts"])))),0))
    ends=(U*n)(*([n]*n))
    balance=decoded["result"]["arrays"]["byPercentileByMfnSimulatedPercentileMajorBalanceStartX100"][0]/100
    with os.add_dll_directory(str(cuda_bin.resolve())),os.add_dll_directory(str(dll.resolve().parent)):
        library=C.CDLL(str(dll.resolve()))
        function=library.cuda_research_horizon
        function.argtypes=[U,D,C.POINTER(Params),C.POINTER(Arrays),C.POINTER(U),C.c_char_p];function.restype=C.c_int
        status=function(n,balance,C.byref(params),C.byref(arrays),ends,str(output.resolve()).encode("ascii"))
    if status!=0: raise RuntimeError("Offline native path export did not complete")
    return {"months":n,"runs":count,"rows":n*count,"dll_sha256":dll_sha256,
            "path_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),
            "historical_source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
            "scope":"Pinned original CUDA calculations through separate full-path export; original circular sampler retained; processed historical-moment reconstruction still needs marginal parity check"}
