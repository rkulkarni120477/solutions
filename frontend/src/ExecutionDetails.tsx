import { useEffect, useState } from 'react';
import { Clock3, LoaderCircle, RefreshCw } from 'lucide-react';

type Component = {stage:string;agent:string;implementation:string;agent_type:string};
type Stage = Component & {started_at:string;finished_at:string|null;duration_ms:number|null;outcome:string};
type Activity = Component & {id:string;kind:string;message:string;details:Record<string,unknown>;created_at:string};
type Execution = {job_id:string;status:string;created_at:string;updated_at:string;server_time:string;recorded:boolean;current:Component;handlers:Component[];stages:Stage[];activity:Activity[]};
const terminal=(status:string)=>['Completed','Failed','Cancelled'].includes(status);
const duration=(value:number|null)=>value===null?'Not recorded':value<1000?'<1s':value<60000?`${Math.floor(value/1000)}s`:`${Math.floor(value/60000)}m ${Math.floor(value%60000/1000)}s`;
const time=(value:string)=>new Date(value).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const labels:Record<string,string>={provider:'Provider',model:'Model',schema:'Schema',input_tokens:'Input tokens',output_tokens:'Output tokens',total_tokens:'Total tokens',duration_ms:'Duration',stop_reason:'Stop reason',attempt:'Attempt',worker_pid:'Worker PID',selected_passages:'Selected passages',available_passages:'Available passages',history_versions:'History versions',filename:'File',format:'Format',bytes:'Bytes',architecture_diagrams:'Architecture diagrams',delivery_diagrams:'Delivery diagrams',racii_rows:'RACII activities',estimate_rows:'Estimate rows',commercial_model:'Commercial model',priced:'Priced',caller:'Caller',callee:'Recipient',message_kind:'Hand-off',variation_count:'Variations',part_index:'Section',part_count:'Total sections',diagram_index:'Diagram',error_type:'Error type',max_output_tokens:'Output token limit'};

function metadata(details:Record<string,unknown>){return Object.entries(details).filter(([key,value])=>labels[key]&&value!==null&&value!==undefined&&['string','number','boolean'].includes(typeof value)).map(([key,value])=><span key={key}><b>{labels[key]}:</b> {key==='duration_ms'?duration(Number(value)):typeof value==='number'?value.toLocaleString():String(value)}</span>);}

export function ExecutionDetails({jobId,jobStatus,stages:selectedStages,label}:{jobId:string;jobStatus:string;stages:string[];label:string}){
 const [data,setData]=useState<Execution|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[reload,setReload]=useState(0),[all,setAll]=useState(false),[clock,setClock]=useState(Date.now()),[received,setReceived]=useState(Date.now());
 useEffect(()=>{
  let alive=true,inFlight=false;const controller=new AbortController();
  async function refresh(){if(inFlight)return;inFlight=true;try{const response=await fetch(`/api/jobs/${jobId}/execution`,{credentials:'same-origin',signal:controller.signal});if(!response.ok)throw Error('Execution details could not be loaded.');const result=await response.json() as Execution;if(alive){setData(result);setReceived(Date.now());setClock(Date.now());setError('');}}catch(e){if(alive&&(e as Error).name!=='AbortError')setError('Execution details could not be refreshed.');}finally{inFlight=false;if(alive)setLoading(false);}}
  refresh();const poll=terminal(jobStatus)?undefined:setInterval(refresh,1800);const timer=terminal(jobStatus)?undefined:setInterval(()=>setClock(Date.now()),1000);
  return()=>{alive=false;controller.abort();if(poll)clearInterval(poll);if(timer)clearInterval(timer);};
 },[jobId,jobStatus,reload]);
 const stageRows=data?.stages.filter(stage=>selectedStages.includes(stage.stage))||[];
 const activity=data?.activity.filter(event=>all||selectedStages.includes(event.stage))||[];
 const selected=label==='Workflow'?data?.current:stageRows.at(-1)||data?.handlers.find(handler=>handler.stage===data.current.stage&&selectedStages.includes(handler.stage))||data?.handlers.find(handler=>selectedStages.includes(handler.stage));
 const serverNow=data?new Date(data.server_time).getTime()+Math.max(0,clock-received):0;
 const elapsed=stageRows.length&&!(terminal(data?.status||'')&&stageRows.some(stage=>stage.duration_ms===null))?stageRows.reduce((sum,stage)=>sum+(stage.duration_ms??(!terminal(data!.status)?Math.max(0,serverNow-new Date(stage.started_at).getTime()):0)),0):null;
 const requests=data?.activity.filter(event=>selectedStages.includes(event.stage)&&event.kind==='provider_request_started')||[];
 const latestModel=requests.at(-1)?.details;
 const state=label==='Workflow'?data?.status:stageRows.at(-1)?.outcome||(selectedStages.includes(data?.status||'')?'Running':'Pending');
 return <div className="execution-details">
  <div className="execution-details-heading"><div><h3>{label}: backend execution</h3><p>Recorded operations and timings. Click another workflow card to inspect its component.</p></div><button className="icon-button" aria-label="Refresh execution details" onClick={()=>setReload(value=>value+1)}><RefreshCw size={15}/></button></div>
  {loading&&!data?<p className="execution-loading"><LoaderCircle size={15} className="spin"/> Loading backend activity…</p>:null}
  {error&&<div className="execution-error" role="alert">{error} <button className="text-button" onClick={()=>setReload(value=>value+1)}>Retry</button></div>}
  {data&&<>
   {!data.recorded&&<p className="execution-empty">No execution events were recorded for this run. Detailed timings and activity are available for newly recorded work.</p>}
   {selected?<div className="execution-component"><div><span>{selected.agent_type}</span><strong>{selected.agent}</strong><code>{selected.implementation}</code></div><span className="execution-state">{state}</span></div>:<p className="execution-empty">This transition is recorded in the proposal’s agent activity log, including human review and publication.</p>}
   <div className="execution-metrics"><div><small><Clock3 size={12}/> Elapsed in this step</small><strong>{duration(elapsed)}</strong></div><div><small>Started</small><strong>{stageRows[0]?time(stageRows[0].started_at):state==='Pending'&&data.recorded?'Not started':'Not recorded'}</strong></div><div><small>Recorded model calls</small><strong>{requests.length.toLocaleString()}</strong></div><div><small>Model</small><strong className="execution-model">{latestModel?String(latestModel.model):'No recorded call in this step'}</strong>{latestModel&&<span>{String(latestModel.provider)}</span>}</div></div>
   {stageRows.length>0&&<div className="execution-stage-table"><table><caption>Stage timings</caption><thead><tr><th>Backend stage</th><th>Started</th><th>Finished</th><th>Duration</th><th>Outcome</th></tr></thead><tbody>{stageRows.map((stage,index)=><tr key={stage.stage+index}><td>{stage.stage}</td><td>{time(stage.started_at)}</td><td>{stage.finished_at?time(stage.finished_at):terminal(data.status)?'Not recorded':'Executing'}</td><td>{duration(stage.duration_ms??(!terminal(data.status)?Math.max(0,serverNow-new Date(stage.started_at).getTime()):null))}</td><td>{stage.outcome}</td></tr>)}</tbody></table></div>}
   <div className="execution-activity-heading"><h4>Execution activity</h4><label><input type="checkbox" checked={all} onChange={e=>setAll(e.target.checked)}/> All workflow activity</label></div>
   {activity.length?<ol className="execution-activity">{activity.slice(-30).reverse().map(event=><li key={event.id}><time dateTime={event.created_at}>{time(event.created_at)}</time><div><strong>{event.message}</strong><small>{event.agent} · {event.stage}</small><div className="execution-metadata">{metadata(event.details)}</div></div></li>)}</ol>:<p className="execution-empty">No activity recorded for this step yet.</p>}
   <p className="execution-privacy">Operational events only. Prompts, document contents, credentials and hidden model reasoning are excluded. Showing up to 30 recent events from the selected view.</p>
  </>}
 </div>;
}
