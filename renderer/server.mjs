import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';
const script = await readFile(new URL('./dist/mermaid.js', import.meta.url), 'utf8');
const secret = process.env.RENDERER_SECRET || 'development-renderer-secret';
let busy = false;
const server = http.createServer(async (req,res) => {
  res.setHeader('Content-Type','application/json');
  if(req.url === '/health') { res.end('{"status":"ok"}'); return; }
  if(req.method !== 'POST' || req.url !== '/render') { res.writeHead(404).end('{}'); return; }
  if(req.headers.authorization !== `Bearer ${secret}`) { res.writeHead(401).end('{}'); return; }
  if(busy) { res.writeHead(429).end('{"error":"Renderer busy; retry shortly"}'); return; }
  busy=true;
  let browser;
  const timeout=setTimeout(()=>{req.destroy(); if(browser) browser.close().catch(()=>{});},35000);
  try {
    let body='';
    for await(const chunk of req) { body+=chunk; if(body.length>24000) throw Error('Request exceeds limit'); }
    const { source } = JSON.parse(body);
    if(typeof source !== 'string' || source.length>20000 || !/^\s*(flowchart|graph|sequenceDiagram)\b/.test(source)) throw Error('Unsupported diagram');
    const clean=source.replace(/[-=.]>{1,2}|--[xo]|<<[-=.]|[-=.]>>/g,'');
    if(/%%\{|[<>]|\bclick\b|https?:|javascript:|data:|@\{|image:|href|url\s*\(/i.test(clean)) throw Error('Unsafe diagram');
    browser=await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH || undefined, args:process.env.RENDERER_NO_SANDBOX==='true'?['--no-sandbox']:[]});
    const context=await browser.newContext({viewport:{width:1600,height:900},javaScriptEnabled:true});
    await context.route('**/*', route => route.abort());
    const page=await context.newPage();
    page.setDefaultTimeout(20000);
    await page.setContent('<!doctype html><html><body style="margin:0;background:#fff"><div id="output" style="padding:32px;display:inline-block;background:white"></div></body></html>');
    await page.addScriptTag({content:script});
    const svg=await page.evaluate(async source=>{
      window.mermaid.initialize({startOnLoad:false,securityLevel:'strict',maxTextSize:20000,maxEdges:100,theme:'base',themeVariables:{primaryColor:'#edf3ff',primaryTextColor:'#173554',primaryBorderColor:'#8ba9d5',lineColor:'#6484b1',fontFamily:'Arial',fontSize:'16px'},flowchart:{htmlLabels:false,useMaxWidth:false},sequence:{useMaxWidth:false}});
      await window.mermaid.parse(source);
      const {svg}=await window.mermaid.render('architecture',source);
      document.getElementById('output').innerHTML=svg;
      return svg;
    },source);
    const box=await page.locator('#output').boundingBox();
    if(!box || box.width>6000 || box.height>6000 || box.width*box.height>16000000) throw Error('Diagram exceeds rendering dimensions');
    const png=await page.locator('#output').screenshot({type:'png',timeout:10000});
    const jpg=await page.locator('#output').screenshot({type:'jpeg',quality:92,timeout:10000});
    res.end(JSON.stringify({svg:Buffer.from(svg).toString('base64'),png:png.toString('base64'),jpg:jpg.toString('base64')}));
  } catch(e) { if(!res.destroyed) res.writeHead(422).end(JSON.stringify({error:'Diagram could not be safely rendered. Check Mermaid syntax and limits.'})); }
  finally { clearTimeout(timeout); if(browser) await browser.close().catch(()=>{}); busy=false; }
});
server.requestTimeout=35000;
server.listen(Number(process.env.PORT||3001),process.env.HOST||'127.0.0.1',()=>console.log('Renderer ready on port '+(process.env.PORT||3001)));
