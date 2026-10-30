import { useMemo, useState } from 'react';
import { ArrowRight, BookOpen, Check, Copy, Search, X } from 'lucide-react';
import { promptCategories, promptTemplates } from './prompts';
import type { PromptCategory, PromptTemplate } from './prompts';
import './prompt-library.css';

export function PromptLibrary({ onUse }: { onUse: (template: PromptTemplate) => void }) {
  const [category, setCategory] = useState<PromptCategory | 'all'>('all');
  const [query, setQuery] = useState('');
  const [copied, setCopied] = useState('');
  const [copyError, setCopyError] = useState('');
  const visible = useMemo(() => {
    const search = query.trim().toLowerCase();
    return promptTemplates.filter(template => {
      const categoryName = promptCategories.find(c => c.id === template.category)!.name;
      return (category === 'all' || template.category === category) &&
        `${template.title} ${template.description} ${template.prompt} ${categoryName}`.toLowerCase().includes(search);
    });
  }, [category, query]);

  async function copy(template: PromptTemplate) {
    try {
      await navigator.clipboard.writeText(template.prompt);
      setCopied(template.id);
      setCopyError('');
    } catch {
      setCopyError('Clipboard access is unavailable. Expand the prompt to select and copy its text.');
    }
  }

  return <section className="prompt-library" aria-labelledby="prompt-library-title">
    <div className="library-heading">
      <div className="eyebrow"><BookOpen size={14} /> THE PROMPT LIBRARY</div>
      <h1 id="prompt-library-title">A better starting point.<br />For every kind of solution.</h1>
      <p>Explore ready-to-use prompts, organized around your work. Choose one for a new solution, replace the details in brackets, and review it before submitting.</p>
      <div className="library-summary"><span>{promptTemplates.length} sample prompts</span><span>{promptCategories.length} categories</span><span>Editable before submission</span></div>
    </div>
    <div className="library-tools">
      <label className="library-search"><Search size={18} /><input aria-label="Search sample prompts" placeholder="Search prompts, topics or technologies…" value={query} onChange={e => setQuery(e.target.value)} />{query && <button aria-label="Clear prompt search" onClick={() => setQuery('')}><X size={16} /></button>}</label>
      <p>Tip: attach your reference documents after choosing a prompt.</p>
    </div>
    <div className="library-layout">
      <nav className="prompt-categories" aria-label="Prompt categories">
        <div className="nav-label">BROWSE BY CATEGORY</div>
        <button className={category === 'all' ? 'active' : ''} aria-pressed={category === 'all'} onClick={() => setCategory('all')}><span>All prompts</span><span>{promptTemplates.length}</span></button>
        {promptCategories.map(c => <button key={c.id} className={category === c.id ? 'active' : ''} aria-pressed={category === c.id} onClick={() => setCategory(c.id)}><span>{c.name}</span><span>{promptTemplates.filter(p => p.category === c.id).length}</span></button>)}
      </nav>
      <div className="library-results">
        <div className="library-result-heading"><div><h2>{category === 'all' ? 'Explore all prompts' : promptCategories.find(c => c.id === category)!.name}</h2><p>{category === 'all' ? 'From the first architecture sketch to the delivery roadmap.' : promptCategories.find(c => c.id === category)!.description}</p></div><span role="status" aria-live="polite">{visible.length} {visible.length === 1 ? 'prompt' : 'prompts'}</span></div>
        {copyError && <div className="notice" role="alert">{copyError}</div>}
        <div className="prompt-card-grid">{visible.map(template => <article className="surface prompt-template" key={template.id}>
          <div className="prompt-template-category">{promptCategories.find(c => c.id === template.category)!.name}</div>
          <h3>{template.title}</h3><p>{template.description}</p>
          <details><summary>Read full prompt</summary><p className="prompt-full-text">{template.prompt}</p></details>
          <div className="template-outputs" aria-label="Included output selections">{template.outputs.map(output => <span key={output}>{({ solution: 'Solution', diagrams: 'Diagrams', estimates: 'Estimates', plan: 'Delivery plan', presentation: 'Presentation' } as Record<string, string>)[output]}</span>)}</div>
          <div className="prompt-template-actions"><button className="text-button" onClick={() => onUse(template)}>Use this prompt <ArrowRight size={14} /></button><button className="icon-button" aria-label={copied === template.id ? 'Copied ' + template.title : 'Copy ' + template.title} onClick={() => copy(template)}>{copied === template.id ? <Check size={16} /> : <Copy size={16} />}</button></div>
        </article>)}</div>
        {!visible.length && <div className="surface prompt-search-empty"><Search size={27} /><h3>No matching prompts</h3><p>Try a different keyword or explore another category.</p><button className="secondary" onClick={() => { setQuery(''); setCategory('all'); }}>Show all prompts</button></div>}
      </div>
    </div>
  </section>;
}
