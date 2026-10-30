import { useEffect, useState } from 'react';
import { Bot, Check, ChevronRight, CircleAlert, Clock3, FileCheck2, LoaderCircle, UserRound, Workflow } from 'lucide-react';
import './workflow-progress.css';
import { ExecutionDetails } from './ExecutionDetails';

type WorkflowJob = {id:string;status:string;kind?:string;error:string|null};
type Step = {name:string;description:string;statuses:string[]};
const solutionSteps:Step[] = [
 {name:'Request queue',description:'Schedules your request',statuses:['Queued']},
 {name:'Context builder',description:'References & decisions',statuses:['Building Context']},
 {name:'Solution architect',description:'Solution generation',statuses:['Generating Solution']},
 {name:'Document builder',description:'Files & download package',statuses:['Creating Files']},
];
const proposalSteps:Step[] = [
 {name:'Orchestrator',description:'Routes the request',statuses:['Queued','Building Context']},
 {name:'Requirements',description:'Validates scope & inputs',statuses:['Collecting Requirements']},
 {name:'Proposal creator',description:'Drafts the response',statuses:['Planning Proposal','Generating Solution']},
 {name:'Estimations',description:'Effort & commercials',statuses:['Estimating']},
 {name:'Resources',description:'Team & allocation',statuses:['Planning Resources']},
 {name:'Methodology',description:'Delivery & governance',statuses:['Defining Methodology']},
 {name:'Documents',description:'Builds proposal files',statuses:['Preparing Documents','Creating Files']},
 {name:'Human review',description:'Review & approval',statuses:[]},
 {name:'Publish',description:'Response documents',statuses:[]},
];
const documentSteps:Step[] = [solutionSteps[0],solutionSteps[3]];

export function WorkflowProgress({job,artifacts=[],proposal}:{job:WorkflowJob;artifacts?:{status:string}[];proposal?:{status:string}}){
 const isProposal=job.kind==='proposal';
 const steps=isProposal?proposalSteps:['files','artifact'].includes(job.kind||'')?documentSteps:solutionSteps;
 const reportedStep=steps.findIndex(step=>step.statuses.includes(job.status));
 const [lastStep,setLastStep]=useState(reportedStep);
 const [detailsOpen,setDetailsOpen]=useState(true),[inspected,setInspected]=useState<number|null>(null);
 useEffect(()=>{if(reportedStep>=0)setLastStep(reportedStep);},[reportedStep]);
 const cancelled=job.status==='Cancelled';
 const failed=job.status==='Failed'||cancelled;
 const waitingForInput=isProposal&&job.status==='Completed'&&proposal?.status==='Awaiting Information';
 const waitingForReview=isProposal&&job.status==='Completed'&&proposal?.status==='Pending Review';
 const paused=waitingForInput||waitingForReview;
 const complete=job.status==='Completed'&&!paused;
 const processed=artifacts.filter(file=>['Completed','Failed'].includes(file.status)).length;
 const documentIndex=isProposal?6:steps.length-1;
 const current=waitingForInput?1:waitingForReview?7:complete?steps.length:reportedStep>=0?reportedStep:failed&&artifacts.length?documentIndex:lastStep;
 let percent=current<0?null:Math.round(current/steps.length*100);
 if(job.status==='Creating Files'&&artifacts.length)percent=Math.min(99,Math.round((documentIndex+processed/artifacts.length)/steps.length*100));
 if(complete)percent=100;
 const detailIndex=inspected??(current>=0?Math.min(current,steps.length-1):-1);
 const detailStep=steps[detailIndex];
 const currentName=steps[current]?.name;
 const queued=job.status==='Queued';
 const badge=cancelled?'Cancelled':failed?'Stopped':paused?'Waiting for you':complete?job.error?'Finished with warnings':'Completed':queued?'Queued':'Executing';
 const owner=failed?'None executing':waitingForInput?'Your clarification':waitingForReview?'Human reviewer':complete?'Workflow finished':queued?'Waiting to start':currentName||job.status;
 const summary=cancelled?'This workflow was cancelled. Your saved project and completed files are kept.':failed?'The workflow stopped. Review the error below before retrying.':waitingForInput?'The Requirements agent needs your input before the workflow can continue.':waitingForReview?'The agents have finished drafting. Review the files and approve to publish.':complete?job.error?'The workflow finished. Some files need attention.':'Your workflow has finished. Generated files are available below.':queued?'Your request is queued. The first stage will start shortly.':`${currentName||'The workflow'} is executing — ${job.status}.`;
 return <section className={'workflow-progress surface'+(failed?' workflow-stopped':'')} aria-label="Agent workflow progress">
  <div className="workflow-heading"><span className="workflow-symbol"><Workflow size={21}/></span><div><h2>{isProposal?'Multi-agent workflow':'Agent workflow'}</h2><p>Follow each hand-off from request to deliverables.</p></div><span className={'workflow-badge '+(complete?'complete':paused?'paused':failed?'stopped':'')}>
   {!complete&&!paused&&!failed&&!queued&&<span className="workflow-live-dot"/>}{badge}
  </span></div>
  <div className="workflow-execution" role="status" aria-live="polite" aria-atomic="true"><div><span>{paused?'CURRENT STAGE':complete?'WORKFLOW STATUS':'CURRENT AGENT'}</span><strong>{owner}</strong></div><p>{summary}</p></div>
  <div className="workflow-progress-label"><span>Workflow progress</span><strong>{percent===null?(cancelled?'Cancelled':'Stopped'):`${percent}%`}</strong></div>
  <div className="workflow-progress-track" role="progressbar" aria-label="Workflow progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent??undefined} aria-valuetext={failed?`Workflow ${cancelled?'cancelled':'stopped'}${percent===null?'':` at ${percent}%`}`:`${percent}% — ${paused?'waiting for your action':complete?'completed':job.status}`}><div className="workflow-progress-fill" style={{width:`${percent??100}%`,opacity:percent===null?.25:1}}/></div>
  <ol className={'workflow-agent-flow '+(isProposal?'proposal-flow':'')}>
   {steps.map((step,index)=>{
    const done=complete||current>=0&&index<current;
    const selected=!complete&&index===current;
    const state=done?'done':selected?failed?'failed':paused?'waiting':queued?'queued':'running':'pending';
    const Icon=done?Check:selected&&failed?CircleAlert:selected&&paused?UserRound:selected&&!queued?LoaderCircle:step.name==='Request queue'?Clock3:step.name==='Human review'?UserRound:step.name==='Publish'||index===documentIndex?FileCheck2:Bot;
    return <li key={step.name} className={'workflow-agent '+state+(detailsOpen&&index===detailIndex?' inspecting':'')} aria-current={selected?'step':undefined}><span className="workflow-agent-icon"><Icon size={17} className={state==='running'?'spin':undefined}/></span><div><strong>{step.name}</strong><p>{step.description}</p><span className="workflow-agent-status">{done?'Completed':selected?failed?'Stopped':paused?'Awaiting action':queued?'Queued':'Executing':'Pending'}</span></div><button className="workflow-agent-select" aria-label={"Execution details: "+step.name} aria-expanded={detailsOpen&&index===detailIndex} aria-controls={"execution-details-"+job.id} onClick={()=>{setInspected(index);setDetailsOpen(true);}}><span>Details</span></button>{index<steps.length-1&&<ChevronRight size={15} className="workflow-connector" aria-hidden="true"/>}</li>;
   })}
  </ol>
  <p className="workflow-progress-note">{job.status==='Creating Files'&&artifacts.length?`${processed} of ${artifacts.length} files processed. `:''}Progress reflects completed workflow stages, not elapsed time.</p>
  <div className="workflow-details-toolbar"><button className="text-button" aria-expanded={detailsOpen} aria-controls={'execution-details-'+job.id} onClick={()=>setDetailsOpen(value=>!value)}>{detailsOpen?'Hide backend execution':'Show backend execution'}</button>{inspected!==null&&<button className="text-button" onClick={()=>setInspected(null)}>Follow current agent</button>}</div>
  {detailsOpen&&<div id={'execution-details-'+job.id}><p className="workflow-component-note">{isProposal?'RFP specialist agents and their backend operations are recorded below.':'Context and document building are worker steps. Solution architect is the model-generation step.'}</p><ExecutionDetails key={job.id} jobId={job.id} jobStatus={job.status} stages={detailStep?.statuses||steps.flatMap(step=>step.statuses)} label={detailStep?.name||'Workflow'}/></div>}

 </section>;
}
