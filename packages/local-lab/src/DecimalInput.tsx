import {useEffect,useRef,useState} from 'react'
import {TextInput} from '@astryxdesign/core/TextInput'

const display=(value:number,scale:number)=>Number.isFinite(value)?String(Number((value*scale).toPrecision(14))):''
export default function DecimalInput({label,value,onChange,description,scale=1,integer=false}:{
  label:string;value:number;onChange:(value:number)=>void;description?:string;scale?:number;integer?:boolean
}){
  const [draft,setDraft]=useState(()=>display(value,scale));const [blurred,setBlurred]=useState(false)
  const editing=useRef(false);const dirty=useRef(false)
  useEffect(()=>{if(!editing.current)setDraft(display(value,scale))},[value,scale])
  const parsed=draft.trim()===''?NaN:Number(draft.replace('。','.'))/scale
  const valid=Number.isFinite(parsed)&&(!integer||Number.isInteger(parsed))
  return <div className="decimal-field"><TextInput label={label} description={description} inputMode={integer?'numeric':'decimal'} value={draft}
    onFocus={()=>{editing.current=true;dirty.current=false;setBlurred(false)}}
    onChange={text=>{dirty.current=true;setDraft(text);const number=text.trim()===''?NaN:Number(text.replace('。','.'))/scale;onChange(number)}}
    onBlur={()=>{editing.current=false;setBlurred(true);if(valid){setDraft(display(parsed,scale));if(dirty.current)onChange(parsed)}}}/>
    {blurred&&!valid&&<p role="alert" className="input-error">{integer?'请输入有效整数。':'请输入有效数字。'}</p>}
  </div>
}
