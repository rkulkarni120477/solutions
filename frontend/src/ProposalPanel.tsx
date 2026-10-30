import { useState } from 'react';
import { ArrowDownToLine, Bot, CheckCircle2, CircleHelp, ClipboardCheck, FileText, LoaderCircle, RefreshCw, Send, ShieldCheck, Upload, Workflow } from 'lucide-react';
import './proposal.css';
import { TemplateSelectors } from './Templates';
import type { ProposalTemplate, TemplateSelection } from './Templates';

export type AgentMessage = {id:string;agent:string;recipient:string|null;kind:string;content:string;created_at:string};
export type Requirement = {id:string;category:string;statement:string;status:string;source:string};
export type Missing = {id:string;question:string;reason:string;required:boolean};
export type Proposal = {id:string;status:string;request:string;formats:string[];requirements:{summary:string;requirements:Requirement[];missing:Missing[];ready:boolean}|null;answers:Record<string,string>;assumptions_accepted:boolean;plan:{response_type:string;formats:string[];outline:string[];win_themes:string[];tone:string}|null;draft_version_id:string|null;reviews:{decision:string;comments:string;reviewer:string;at:string}[];error:string|null;approved_at:string|null;published_at:string|null;created_at:string;messages:AgentMessage[]};
export type ResponseDocument = {id:string;proposal_id:string;kind:string;filename:string;size:number;created_at:string};
type DraftFile = {id:string;filename:string;kind:string;status:string};
type Api = <T>(path:string, method?:string, body?:unknown)=>Promise<T>;

const PIPELINE = [
 {agent:'Orchestrator', label:'Orchestrator'},
 {agent:'RequirementsCollector', label:'Requirements'},
 {agent:'ProposalCreator', label:'Proposal creator'},
 {agent:'EstimationsAgent', label:'Estimations'},
 {agent:'ResourcesAgent', label:'Resources'},
 {agent:'DeliveryMethodology', label:'Methodology'},
 {agent:'DocumentsAgent', label:'Documents'},
 {agent:'Reviewer', label:'Human review'},
];
const STAGE_AGENT:Record<string,string> = {'Queued':'Orchestrator','Building Context':'Orchestrator','Collecting Requirements':'RequirementsCollector','Planning Proposal':'ProposalCreator','Generating Solution':'ProposalCreator','Estimating':'EstimationsAgent','Planning Resources':'ResourcesAgent','Defining Methodology':'DeliveryMethodology','Preparing Documents':'DocumentsAgent','Creating Files':'DocumentsAgent'};
export const PROPOSAL_STAGES = ['Queued','Collecting Requirements','Planning Proposal','Generating Solution','Estimating','Planning Resources','Defining Methodology','Preparing Documents','Creating Files'];
const BUSY = ['Queued','Collecting Requirements','Drafting'];
const size = (n:number)=>n>1048576?(n/1048576).toFixed(1)+' MB':Math.max(1,Math.round(n/1024))+' KB';
const time = (s:string)=>new Date(s).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});

export function ProposalStart({onStart,disabled,templates,onManageTemplates}:{onStart:(request:string,formats:string[],cloud:string,files:File[],selection:TemplateSelection)=>Promise<void>;disabled:boolean;templates:ProposalTemplate[];onManageTemplates:()=>void}){
 const [request,setRequest]=useState(''),[formats,setFormats]=useState<string[]>(['docx','pptx']),[cloud,setCloud]=useState('No preference'),[files,setFiles]=useState<File[]>([]);
 const [templateSelection,setTemplateSelection]=useState<TemplateSelection>({});
 const toggle=(f:string)=>setFormats(formats.includes(f)?formats.filter(x=>x!==f):[...formats,f]);
 return <section className="surface proposal-start">
  <div className="proposal-title"><span className="proposal-icon"><Workflow size={20}/></span><div><div className="section-eyebrow">PRESALES AGENTS</div><h2>Start an RFP response</h2><p>The Orchestrator assigns your request to the Requirements, Proposal, Estimations, Resources, Methodology and Documents agents. You review and approve before anything goes live.</p></div></div>
  <label className="proposal-label" htmlFor="rfp-request">RFP or opportunity details</label>
  <textarea id="rfp-request" className="proposal-textarea" rows={7} value={request} onChange={e=>setRequest(e.target.value)} placeholder="Paste the RFP summary: client, objectives, scope, timeline, budget or commercial model, platform and non-functional requirements…"/>
  <div className="proposal-options">
   <fieldset><legend>Response documents</legend>
    <label><input type="checkbox" checked={formats.includes('docx')} onChange={()=>toggle('docx')}/> Word document</label>
    <label><input type="checkbox" checked={formats.includes('pptx')} onChange={()=>toggle('pptx')}/> PowerPoint presentation</label>
   </fieldset>
   <label className="proposal-select">Target platform<select value={cloud} onChange={e=>setCloud(e.target.value)}>{['No preference','Azure','AWS','GCP','Hybrid','On-premises'].map(c=><option key={c}>{c}</option>)}</select></label>
   <label className="proposal-upload"><Upload size={15}/> {files.length?`${files.length} RFP file(s)`:'Attach RFP documents'}<input type="file" multiple accept=".pdf,.docx,.txt,.md" onChange={e=>setFiles(Array.from(e.target.files||[]))}/></label>
  </div>
  <div className="template-picker-heading"><h3>Proposal templates</h3><button className="text-button" onClick={onManageTemplates}>Manage templates</button></div><TemplateSelectors templates={templates} value={templateSelection} onChange={setTemplateSelection} disabled={disabled}/>
  <div className="proposal-actions"><span className="muted">{request.trim().length<20?'Describe the RFP in at least 20 characters.':formats.length?'':'No format selected: the Proposal creator will decide.'}</span><button className="primary" disabled={disabled||request.trim().length<20} onClick={()=>onStart(request.trim(),formats,cloud,files,templateSelection)}><Send size={15}/> Send to Orchestrator</button></div>
 </section>;
}

type PanelProps = {projectId:string;proposal:Proposal;documents:ResponseDocument[];draft:DraftFile[];jobStatus?:string;busy:boolean;api:Api;refresh:()=>Promise<void>;setError:(s:string)=>void;notify:(s:string)=>void;showDraft:(versionId:string)=>void};

export function ProposalPanel(p:PanelProps){
 const {proposal}=p;
 const [answers,setAnswers]=useState<Record<string,string>>({}),[comments,setComments]=useState(''),[message,setMessage]=useState(''),[sending,setSending]=useState(false);
 const working=BUSY.includes(proposal.status)||p.busy;
 const seen=new Set(proposal.messages.map(m=>m.agent));
 const current=p.jobStatus?STAGE_AGENT[p.jobStatus]:undefined;
 const missing=proposal.requirements?.missing||[];
 const draftReady=p.draft.length>0&&p.draft.every(a=>a.status==='Completed');
 async function act(fn:()=>Promise<unknown>,done:string){setSending(true);p.setError('');try{await fn();p.notify(done);await p.refresh();}catch(e){p.setError((e as Error).message);}finally{setSending(false);}}
 const submitAnswers=(proceed:boolean)=>act(()=>p.api(`/proposals/${proposal.id}/answers`,'POST',{answers:Object.fromEntries(Object.entries(answers).filter(([,v])=>v.trim())),proceed_with_assumptions:proceed}),'Sent to the Requirements agent.');
 const review=(decision:string)=>act(()=>p.api(`/proposals/${proposal.id}/review`,'POST',{decision,comments}),decision==='approve'?'Approved. Response documents are live.':'Changes sent to the Proposal creator.').then(()=>setComments(''));
 const send=()=>act(async()=>{const r=await p.api<{intent:string}>(`/projects/${p.projectId}/orchestrator`,'POST',{message});setMessage('');return r;},'Orchestrator routed your message.');
 async function download(d:ResponseDocument){try{const r=await p.api<{url:string}>(`/response-documents/${d.id}/download-link`,'POST');const link=document.createElement('a');link.href=r.url;link.download=d.filename;document.body.appendChild(link);link.click();link.remove();}catch(e){p.setError((e as Error).message);}}
 const docs=p.documents.filter(d=>d.proposal_id===proposal.id);
 return <section className="surface proposal-panel" aria-label="Presales agent workflow">
  <div className="proposal-title"><span className="proposal-icon"><Workflow size={20}/></span><div><div className="section-eyebrow">PRESALES AGENT WORKFLOW</div><h2>{proposal.plan?.response_type||'RFP response'}</h2><p>Started {time(proposal.created_at)}{proposal.formats.length?' · '+proposal.formats.map(f=>f==='docx'?'Word':'PowerPoint').join(' + '):''}</p></div><span className={'proposal-status s-'+proposal.status.toLowerCase().replace(/\s+/g,'-')}>{working&&<LoaderCircle size={13} className="spin"/>}{proposal.status}</span></div>
  <ol className="agent-pipeline">{PIPELINE.map(s=><li key={s.agent} className={current===s.agent?'running':seen.has(s.agent)?'done':''}><span>{current===s.agent?<LoaderCircle size={12} className="spin"/>:seen.has(s.agent)?<CheckCircle2 size={12}/>:<Bot size={12}/>}</span>{s.label}</li>)}<li className={proposal.status==='Live'?'done live':''}><span>{proposal.status==='Live'?<CheckCircle2 size={12}/>:<ShieldCheck size={12}/>}</span>Live</li></ol>

  {['Failed','Cancelled'].includes(proposal.status)&&<div className="notice failure"><CircleHelp size={18}/><span>{proposal.error||'The workflow failed.'}</span><button className="text-button" disabled={sending||p.busy} onClick={()=>act(()=>p.api(`/proposals/${proposal.id}/retry`,'POST'),'Orchestrator restarted the workflow.')}><RefreshCw size={14}/> Retry</button></div>}

  {proposal.status==='Awaiting Information'&&<div className="proposal-block">
   <h3><CircleHelp size={17}/> The Requirements agent needs more information</h3>
   <p className="muted">{proposal.requirements?.summary}</p>
   {missing.map(m=><label key={m.id} className="missing-item"><span><strong>{m.question}</strong>{m.required?<em>Required</em>:<em className="optional">Optional</em>}</span><small>{m.reason}</small><textarea rows={2} value={answers[m.id]||''} onChange={e=>setAnswers({...answers,[m.id]:e.target.value})} maxLength={4000}/></label>)}
   <div className="proposal-actions"><button className="secondary" disabled={sending} onClick={()=>submitAnswers(true)}>Proceed with assumptions</button><button className="primary" disabled={sending||!Object.values(answers).some(v=>v.trim())} onClick={()=>submitAnswers(false)}><Send size={15}/> Submit answers</button></div>
  </div>}

  {proposal.status==='Pending Review'&&<div className="proposal-block review">
   <h3><ClipboardCheck size={17}/> Ready for your review and approval</h3>
   <p className="muted">The agents have finalized the draft. Review the solution tabs and files below, then approve to publish the Response Documents or send it back with changes.</p>
   {proposal.plan&&<div className="plan-grid"><div><strong>Outline</strong><ol>{proposal.plan.outline.map((o,i)=><li key={i}>{o}</li>)}</ol></div><div><strong>Win themes</strong><ul>{proposal.plan.win_themes.map((o,i)=><li key={i}>{o}</li>)}</ul></div></div>}
   <div className="draft-files">{p.draft.filter(a=>!a.kind.startsWith('diagram:')).map(a=><span key={a.id} className={'file-status '+a.status.toLowerCase()}><FileText size={12}/>{a.filename} · {a.status}</span>)}{proposal.draft_version_id&&<button className="text-button" onClick={()=>p.showDraft(proposal.draft_version_id!)}>Open draft</button>}</div>
   {!draftReady&&<p className="warning-text">All draft files must be completed before approval. Retry failed files from the Files tab.</p>}
   <label className="proposal-label" htmlFor="review-comments">Reviewer comments</label>
   <textarea id="review-comments" className="proposal-textarea" rows={3} value={comments} onChange={e=>setComments(e.target.value)} maxLength={4000} placeholder="Required when requesting changes, optional for approval."/>
   <div className="proposal-actions"><button className="secondary" disabled={sending||p.busy||comments.trim().length<5} onClick={()=>review('request_changes')}>Request changes</button><button className="primary" disabled={sending||p.busy||!draftReady} onClick={()=>review('approve')}><CheckCircle2 size={15}/> Approve &amp; publish</button></div>
  </div>}

  {proposal.status==='Live'&&<div className="proposal-block live"><h3><ShieldCheck size={17}/> Response Documents are live</h3><p className="muted">Approved {proposal.approved_at?time(proposal.approved_at):''}. Published copies are immutable and kept separately from working drafts.</p>
   <div className="response-docs">{docs.map(d=><article key={d.id}><span className={'file-format '+d.filename.split('.').at(-1)}>{d.kind.toUpperCase()}</span><div><strong>{d.filename}</strong><small>{size(d.size)}</small></div><button className="icon-button" aria-label={'Download '+d.filename} onClick={()=>download(d)}><ArrowDownToLine size={17}/></button></article>)}</div></div>}

  {proposal.status!=='Live'&&<div className="orchestrator-input"><label htmlFor="orchestrator-message"><Bot size={15}/> Message the Orchestrator</label><div><input id="orchestrator-message" value={message} onChange={e=>setMessage(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&message.trim().length>1&&!sending)send();}} disabled={working} placeholder={working?'Agents are working…':proposal.status==='Awaiting Information'?'Answer in your own words, or say "proceed with assumptions"':proposal.status==='Pending Review'?'Describe changes for the next draft':'Type "retry" or describe a new RFP'}/><button className="primary compact" disabled={working||sending||message.trim().length<2} onClick={send}><Send size={14}/></button></div></div>}

  {proposal.requirements&&<details className="proposal-details"><summary>Requirements ({proposal.requirements.requirements.length})</summary><ul className="requirement-list">{proposal.requirements.requirements.map(r=><li key={r.id}><span className={'req-status '+r.status}>{r.status}</span><div><strong>{r.category}</strong> {r.statement}{r.source&&<small>{r.source}</small>}</div></li>)}</ul></details>}
  <details className="proposal-details" open={working}><summary>Agent activity ({proposal.messages.length})</summary><ol className="agent-log">{proposal.messages.map(m=><li key={m.id} className={'k-'+m.kind}><div><strong>{m.agent}</strong>{m.recipient&&<> → <strong>{m.recipient}</strong></>}<span>{m.kind}</span><time>{time(m.created_at)}</time></div><p>{m.content}</p></li>)}</ol></details>
 </section>;
}
