export type DiagnosticsData={name:string;rate_sensitivities:{data:string;kind:string;persistence:number;zero_floor_clamps:number;government_yield_path_min_max:number[];outcomes:Record<string,number>}[];
  seed_sensitivities:{seed:number;cagr:number;outcomes:Record<string,number>}[];regime_sensitivities:{regime:string;cagr:number;outcomes:Record<string,number>}[];limits:string[]}
export default function Diagnostics({data:d}: {data?:DiagnosticsData}) {
  if(!d)return null
  return <><h3>合成与利率假设的敏感性</h3><p>以下为已保存的通用示例核验，不是当前个人情景。长期合成结果随校准期、种子及利率持续性明显变化，应作为压力情景阅读。</p>
    <div className="comparison"><table><thead><tr><th>校准期 / 构造种子</th><th>合成股票人民币复合年化</th></tr></thead><tbody>
      {d.regime_sensitivities.map(r=><tr key={r.regime}><th>{r.regime}</th><td>{(r.cagr*100).toFixed(2)}%</td></tr>)}
      {d.seed_sensitivities.map(r=><tr key={r.seed}><th>种子 {r.seed}</th><td>{(r.cagr*100).toFixed(2)}%</td></tr>)}
    </tbody></table></div>
    <div className="comparison"><table><thead><tr><th>数据</th><th>防御资产</th><th>利率持续性</th><th>零下限截断（期限×月份×路径）</th><th>5年国债收益率路径范围</th></tr></thead><tbody>
      {d.rate_sensitivities.map((r,i)=><tr key={i}><th>{r.data==='observed'?'观测联合区间':'长历史合成'}</th><td>{r.kind==='deposit'?'存款':'国债'}</td><td>{r.persistence}</td><td>{r.zero_floor_clamps}</td><td>{r.government_yield_path_min_max.map(v=>(v*100).toFixed(2)+'%').join(' – ')}</td></tr>)}
    </tbody></table></div>{d.limits.map(note=><p className="small" key={note}>{note}</p>)}</>
}
