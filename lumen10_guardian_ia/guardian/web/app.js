'use strict';
const $ = (s) => document.querySelector(s);
const escape = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const parse = (s, fallback = {}) => { try { return JSON.parse(s); } catch { return fallback; } };
const fmt = (s) => s ? new Date(s).toLocaleString('pt-BR', {timeZone:'America/Sao_Paulo',dateStyle:'short',timeStyle:'short'}) : 'Sem medição';
const titles = {overview:'Visão geral',incidents:'Incidentes',environments:'Ambientes',releases:'Correções e releases',terminal:'PowerShell e VS Code',audit:'Trilha de auditoria',license:'Licença e autoria',notifications:'Alertas por e-mail',security:'Segurança global'};
const specialistNames = {'security':'Segurança','php-moodle':'PHP / Moodle','infrastructure':'Infraestrutura','database':'Banco de dados','qa':'Testes e qualidade'};
let view = 'overview', data = null, allData = null, activeSystem = '', samples = [], graphEnvironment = '';
let refreshWork = null, refreshAgain = false;
let bridge = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null;
let requestId = 0;
const pending = new Map();
if (bridge) window.addEventListener('message', ({data:msg}) => {
  if (msg.type !== 'api-result' || !pending.has(msg.id)) return;
  const pair = pending.get(msg.id); pending.delete(msg.id);
  clearTimeout(pair.timer); msg.error ? pair.reject(new Error(msg.error)) : pair.resolve(msg.result);
});
async function api(path, method = 'GET', body) {
  if (bridge) return new Promise((resolve, reject) => {
    const id = ++requestId;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('Tempo de resposta excedido')); }, 35000);
    pending.set(id,{resolve,reject,timer}); bridge.postMessage({type:'api',id,path,method,body});
  });
  const response = await fetch(path, {method, credentials:'same-origin',headers:{'Content-Type':'application/json'},body:body === undefined ? undefined : JSON.stringify(body)});
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Falha no servidor. Consulte o log local do Guardian.');
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Solicitação inválida');
  return result;
}
function toast(message) { $('#toast').textContent = message; $('#toast').classList.add('show'); setTimeout(() => $('#toast').classList.remove('show'), 5500); }
function modal(title, content) { $('#modal-title').textContent = title; $('#modal-body').innerHTML = content; if (!$('#modal').open) $('#modal').showModal(); }
$('#close-modal').addEventListener('click', () => $('#modal').close());
function pill(text, color='') { return `<span class="pill ${color}">${escape(text)}</span>`; }
function statePill(state) { return pill(state.replaceAll('_',' '), /FALHA|REPROVADO|HUMANO|BLOQUEADO/.test(state) ? 'red' : /EXECUCAO|INVESTIGACAO|IMPLANTANDO|AGENDADO/.test(state) ? 'amber' : state === 'DETECTADO' ? 'gray' : ''); }
function empty(message, icon='◈') { return `<div class="empty"><span class="empty-icon">${icon}</span>${escape(message)}</div>`; }
function button(action, label, id='', className='') { return `<button class="${className}" data-action="${action}" data-id="${escape(id)}">${escape(label)}</button>`; }
function heading(title, subtitle, actions='') { return `<div class="heading"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="actions">${actions}</div></div>`; }
function chart() {
  if (!samples.length) return empty('Ative o monitoramento. O gráfico aparecerá após as primeiras medições.', '⌁');
  const env = data.environments.find(e => e.id === graphEnvironment);
  const items = [...samples].reverse();
  const local = ['local','agent'].includes(env?.kind);
  const values = items.map(s => local ? Number(parse(s.data).cpu_percent ?? 0) : Number(s.latency ?? 0));
  const max = local ? 100 : Math.max(10, Math.ceil(Math.max(...values) / 10) * 10);
  const points = values.map((value,index) => [44 + index * 540 / Math.max(1,values.length-1), 145 - value / max * 125]);
  const line = points.map(p => p.join(',')).join(' ');
  const memoryLine = local ? items.map((s,index)=>`${44+index*540/Math.max(1,items.length-1)},${145-Number(parse(s.data).memory_percent??0)/100*125}`).join(' ') : '';
  const grid = [0,.25,.5,.75,1].map(v => `<line class="chart-grid" x1="44" y1="${145-v*125}" x2="584" y2="${145-v*125}"/><text x="2" y="${148-v*125}">${Math.round(v*max)}${local?'%':''}</text>`).join('');
  return `<svg class="chart" role="img" aria-label="${local?'Uso de CPU e memória':'Latência HTTP'} medido ao longo do tempo" viewBox="0 0 600 175" preserveAspectRatio="none"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#53e6b7" stop-opacity=".2"/><stop offset="1" stop-color="#53e6b7" stop-opacity="0"/></linearGradient></defs>${grid}<polygon fill="url(#area)" points="44,145 ${line} ${points.at(-1)[0]},145"/><polyline class="chart-line" points="${line}"/>${local?`<polyline fill="none" stroke="#55bbf4" stroke-width="2" points="${memoryLine}"/>`:''}${points.map(p=>`<circle cx="${p[0]}" cy="${p[1]}" r="2" fill="#6aefc3"/>`).join('')}<text x="44" y="169">${escape(fmt(items[0].observed_at))}</text><text x="584" y="169" text-anchor="end">${escape(fmt(items.at(-1).observed_at))}</text></svg><div class="chart-caption"><span class="chart-legend">● ${local?'CPU (%) <span class="blue">● Memória (%)</span>':'Latência (ms)'}</span><span>${items.length} amostras reais · janela de até 7 dias</span></div>`;
}
function incidentTable(list, compact=false) {
  if (!list.length) return empty('Nenhum incidente registrado neste workspace.');
  return `<div class="table-wrap"><table><thead><tr><th>INCIDENTE</th><th>PRIORIDADE</th><th>ESTADO</th><th></th></tr></thead><tbody>${list.map(i=>`<tr><td class="cell-main">${escape(i.title.slice(0,compact?65:100))}<small>${escape(i.id.slice(0,8))} · ${fmt(i.created_at)} · ${i.occurrences} ocorrência(s)</small></td><td>${pill(i.severity,i.severity==='P1'||i.severity==='P0'?'red':'gray')}</td><td>${statePill(i.state)}</td><td>${button('incident','Ver análise',i.id,'table-action')}</td></tr>`).join('')}</tbody></table></div>`;
}
function overview() {
  const active = data.monitoring_active;
  const open = data.incidents.filter(i=>!['RESOLVIDO','REVERTIDO','ENCERRADO_SEM_CORRECAO'].includes(i.state));
  const local = data.environments.find(e=>['local','agent'].includes(e.kind));
  const measured = data.environments.filter(e=>e.sample_count);
  const total = measured.reduce((sum,e)=>sum+e.sample_count,0);
  const availability = total ? measured.reduce((sum,e)=>sum + e.availability*e.sample_count,0)/total : null;
  const memory = parse(local?.latest?.data).memory_percent;
  const jobs = data.jobs.filter(j=>j.state==='running').length;
  return heading('Seu ambiente, sob controle.', 'Monitoramento contínuo. Diagnóstico especializado. Cada ação rastreável.',
    button('new-env','＋ Conectar ambiente','','secondary') + button('toggle',active?'Ⅱ Pausar monitoramento':'▶ Ativar Guardian','','primary')) +
    `<section class="hero"><div class="hero-copy"><div class="eyebrow"><span class="dot"></span> GUARDIAN LOCAL INTELLIGENCE</div><h2>${active?'Observando cada sinal.<br>Preparado para agir.':'Inteligência pronta.<br>Você inicia a operação.'}</h2><p>${active?'Medições locais e ambientes conectados alimentam o gerente. Incidentes seguem para especialistas com políticas verificáveis.':'Ative o monitor para iniciar as medições reais. O Codex conectado será acionado por incidentes confirmados pelo detector.'}</p><div class="hero-tags"><span>Sem chave de API</span><span>Contexto protegido</span><span>Auditoria persistente</span></div></div><div class="radar" aria-hidden="true"><div class="orbit"></div><div class="orbit"></div><div class="orbit"></div><div class="radar-core"><span>G</span></div><div class="radar-label l1"><i class="dot"></i> Monitor · ${active?'ativo':'pronto'}</div><div class="radar-label l2"><i class="dot"></i> ${data.provider.authenticated?'Codex conectado':'Codex pendente'}</div><div class="radar-label l3"><i class="dot"></i> Executor · controlado</div></div></section>
    <div class="stats"><section class="card stat"><span class="stat-label">Disponibilidade observada</span><span class="mini">⌁</span><strong class="green">${availability===null?'—':availability.toFixed(2)+'<small> %</small>'}</strong><small>${total?total+' medições na janela disponível':'Aguardando primeiras medições'}</small></section><section class="card stat"><span class="stat-label">Incidentes abertos</span><span class="mini">⚑</span><strong>${open.length.toString().padStart(2,'0')}</strong><small>${open.filter(i=>['P0','P1'].includes(i.severity)).length} de prioridade elevada</small></section><section class="card stat"><span class="stat-label">Ambientes cadastrados</span><span class="mini">▧</span><strong>${data.environments.length.toString().padStart(2,'0')}</strong><small>${measured.length} com telemetria disponível</small></section><section class="card stat"><span class="stat-label">Memória do host</span><span class="mini">▥</span><strong class="blue">${memory??'—'}${memory===undefined?'':'<small> %</small>'}</strong><small>${local?'Última amostra do host':'Conecte um agente para medir o host'}</small></section></div>
    <div class="grid-main"><section class="card"><div class="card-head"><h2>Telemetria em tempo real</h2><select id="graph-env" aria-label="Ambiente do gráfico">${data.environments.filter(e=>['local','http','agent'].includes(e.kind)).map(e=>`<option value="${e.id}" ${graphEnvironment===e.id?'selected':''}>${escape(e.name)}</option>`).join('')}</select></div><div class="chart-body">${chart()}</div></section><section class="card"><div class="card-head"><h2>Motor de operação</h2>${pill('LOCAL','gray')}</div><div class="engine-row"><div class="engine-icon">⌁</div><div><strong>Monitor determinístico</strong><small>Coleta a cada 30 segundos</small></div>${pill(active?'Ativo':'Pausado',active?'':'gray')}</div><div class="engine-row"><div class="engine-icon">✧</div><div><strong>Gerente · Codex</strong><small>${escape(data.provider.message)}</small></div>${pill(data.provider.authenticated?'Pronto':'Pendente',data.provider.authenticated?'':'amber')}</div><div class="engine-row"><div class="engine-icon">◇</div><div><strong>Especialistas efêmeros</strong><small>${data.specialists.filter(s=>s.state==='running').length} em análise · ${data.specialists.length} registrados</small></div>${pill(jobs?'Em execução':'Disponível',jobs?'amber':'gray')}</div><div class="engine-row"><div class="engine-icon">⊞</div><div><strong>Análises de IA</strong><small>Quota diária por empresa · UTC</small></div>${pill(data.ai_used+' / '+data.ai_limit,'gray')}</div></section></div>
    <section class="card"><div class="card-head"><h2>Incidentes recentes</h2>${button('go-incidents','Ver todos →','','table-action secondary')}</div>${incidentTable(data.incidents.slice(0,5),true)}</section>`;
}
function environments() { return heading('Ambientes conectados','Disponibilidade HTTP, saúde local e conexões de projeto.',button('remote-source','Conectar código por chave','','secondary')+button('new-env','＋ Conectar ambiente','','primary')) +
  `<section class="card"><div class="table-wrap"><table><thead><tr><th>AMBIENTE</th><th>TIPO</th><th>DISPONIBILIDADE</th><th>POLÍTICA</th><th></th></tr></thead><tbody>${data.environments.map(e=>`<tr><td class="cell-main">${escape(e.name)}<small>${escape(e.target)}</small></td><td>${pill(e.kind,'gray')}</td><td>${e.availability===null?'Aguardando amostras':e.availability+'%'}<small class="muted"> · ${e.sample_count} amostras</small></td><td>${pill(e.paused?'Mudanças suspensas':e.auto_ai?'IA por incidente':'IA sob demanda',e.paused?'red':'gray')}</td><td><div class="actions">${button('policy','Configurar',e.id,'table-action')+button('group-env','Sistema',e.id,'table-action')}${button('review','Analisar',e.id,'table-action')}${e.kind==='project'?button('connection','Conexão',e.id,'table-action')+button('source-key','Gerar chave de código',e.id,'table-action'):''}</div></td></tr>`).join('')}</tbody></table></div></section>`; }
function releases() { return heading('Correções com evidência.','Git, testes reais, artefatos verificados e histórico de publicação.',button('laboratory','＋ Criar laboratório local','','primary'))+
  `<div class="warning">Publicação executável habilitada no laboratório local. Produção depende de conexão, homologação, backup e habilitação específica do adaptador.</div><section class="card"><div class="flow"><span>1 · Diagnosticar</span><span>2 · Especialista</span><span>3 · Branch</span><span>4 · Testar</span><span>5 · Validar política</span><span>6 · Publicar e verificar</span></div>${!data.changes.length?empty('Crie um laboratório e investigue o incidente para iniciar o ciclo.'): `<div class="table-wrap"><table><thead><tr><th>ALTERAÇÃO</th><th>ESTADO</th><th>CRIADA EM</th><th></th></tr></thead><tbody>${data.changes.map(c=>`<tr><td class="cell-main">${escape(c.id.slice(0,8))}<small>${escape(parse(c.artifact).branch)}</small></td><td>${statePill(c.state)}</td><td>${fmt(c.created_at)}</td><td>${button('change','Diff e testes',c.id,'table-action')}</td></tr>`).join('')}</tbody></table></div>`}</section>`; }
function incidents() { return heading('Do sinal à causa.','O gerente seleciona um especialista e preserva o contexto de cada investigação.') +
  `<section class="card">${incidentTable(data.incidents)}</section><section class="card section-space"><div class="card-head"><h2>Especialistas acionados</h2>${pill(data.specialists.length+' tarefas','gray')}</div>${data.specialists.length?`<div class="table-wrap"><table><thead><tr><th>ESPECIALISTA</th><th>ESTADO</th><th>INÍCIO</th><th>CONCLUSÃO</th></tr></thead><tbody>${data.specialists.map(s=>`<tr><td>${escape(specialistNames[s.specialist]||s.specialist)}</td><td>${pill(s.state,s.state==='running'?'amber':s.state==='failed'?'red':'')}</td><td>${fmt(s.created_at)}</td><td>${fmt(s.finished_at)}</td></tr>`).join('')}</tbody></table></div>`:empty('As tarefas de especialistas aparecerão após uma investigação.')}</section>`; }
let terminalOutput = 'PS > Guardian executor pronto.\n\nSelecione “Coletar diagnóstico” para consultar processos, discos e versão do PowerShell.\nEste painel aceita operações cadastradas; o terminal completo está no VS Code.';
function terminal() { return heading('Ferramentas de operação.','PowerShell para diagnósticos. VS Code para contexto, código e revisão.',button('snapshot','Coletar diagnóstico','','primary')+button('vscode','Abrir VS Code','','secondary'))+
  `<div class="connection"><section class="card terminal-box"><div class="terminal-header"><span></span><span></span><span></span><b>PowerShell · executor local</b></div><pre>${escape(terminalOutput)}</pre></section><section class="card"><div class="card-head"><h2>Conexão direta com o agente</h2>${pill('Codex CLI','gray')}</div><div class="timeline"><p class="small muted">O botão de investigação cria uma tarefa persistente e envia o contexto saneado ao Codex conectado. O gerente aciona uma nova sessão especializada para o problema.</p><p class="code-note">Incidente → Gerente → Especialista<br>Branch → Testes → Política → Release</p><p class="small muted">A extensão Guardian abre este painel dentro do editor, oferece terminal PowerShell e prepara um documento de contexto para revisão no chat Codex.</p>${button('vscode','Conectar ao editor','','secondary')}</div></section></div>`; }
function audit() { return heading('Cada decisão deixa uma trilha.','Eventos por empresa com encadeamento de hashes para verificar alterações.',button('verify','Verificar integridade','','primary'))+
  `<section class="card"><div class="table-wrap"><table><thead><tr><th>HORÁRIO</th><th>ATOR</th><th>EVENTO</th><th>RECURSO</th></tr></thead><tbody>${data.audit.map(a=>`<tr><td>${fmt(a.occurred_at)}</td><td>${escape(a.actor)}</td><td>${escape(a.action)}</td><td>${escape(a.resource.slice(0,12))}</td></tr>`).join('')}</tbody></table></div></section><section class="card section-space"><div class="card-head"><h2>Fila persistente</h2>${pill('Até 3 tentativas','gray')}</div>${data.jobs.length?`<div class="table-wrap"><table><thead><tr><th>TAREFA</th><th>ESTADO</th><th>TENTATIVAS</th><th>ÚLTIMA FALHA</th></tr></thead><tbody>${data.jobs.map(j=>`<tr><td>${escape(j.kind)}</td><td>${pill(j.state,j.state==='failed'?'red':j.state==='running'?'amber':'gray')}</td><td>${j.attempts}</td><td>${escape(j.error||'—')}</td></tr>`).join('')}</tbody></table></div>`:empty('A fila está vazia.')}</section>`; }
function render() {
  if (!data) return;
  $('#tenant-name').innerHTML = `${escape(data.tenant.name)}<small>Workspace privado</small>`;
  $('#incident-count').textContent = data.incidents.filter(i=>!['RESOLVIDO','REVERTIDO'].includes(i.state)).length;
  $('#page-title').textContent = titles[view];
  document.querySelectorAll('[data-view]').forEach(n=>n.classList.toggle('active',n.dataset.view===view));
  const tabs=`<div class="system-tabs" aria-label="Sistemas monitorados"><button data-system="" class="${activeSystem?'':'selected'}">Todos os sistemas</button>${(allData?.systems||[]).map(s=>`<button data-system="${s.id}" class="${activeSystem===s.id?'selected':''}">${escape(s.name)}</button>`).join('')}${button('new-system','＋ Novo sistema','','secondary')}</div>`;
  $('#main').innerHTML = tabs + (data.license?.valid?'':`<div class="warning">Operação bloqueada até ativação de licença assinada pelo desenvolvedor. Abra “Licença e autoria”.</div>`) + ({overview,incidents,environments,releases,terminal,audit,license,notifications,security}[view])();
}
function security(){
  const reports=allData.threat_reports||[];
  return heading('Antecipar também é proteger.','Boletins oficiais às 08h e 20h · America/Sao_Paulo.',button('security-profile','Tecnologias do sistema','','secondary')+button('threat-review','Analisar segurança global agora','','primary'))+
  `<div class="warning">Fontes: PHP oficial e CISA KEV, com espelho mantido pela própria CISA. Sem versão confirmada, uma correspondência é potencial. Nenhum aviso publica atualização automaticamente.</div><section class="card"><div class="card-head"><h2>Revisões de inteligência</h2>${pill('2 janelas por dia','gray')}</div>${reports.length?`<div class="table-wrap"><table><thead><tr><th>REVISÃO</th><th>NOVOS AVISOS</th><th>COBERTURA</th><th></th></tr></thead><tbody>${reports.map(r=>`<tr><td>${fmt(r.reviewed_at)}</td><td>${r.new_count}</td><td>${pill(parse(r.sources,[]).some(s=>s.status!=='ok')?'Parcial':'Fontes consultadas',parse(r.sources,[]).some(s=>s.status!=='ok')?'amber':'gray')}</td><td>${button('threat-report','Ver boletim',r.id,'table-action')}</td></tr>`).join('')}</tbody></table></div>`:empty('As revisões aparecerão na próxima janela após a ativação, ou mediante análise solicitada.')}</section><p class="form-note">Durante a operação normal, a IA só investiga incidentes ou pedidos explícitos. A inteligência global é a exceção programada de duas revisões diárias. Sem novidade relevante, o boletim fica no histórico; novos avisos e falhas de fonte entram na fila de e-mail habilitada.</p>`;
}
function systemData(source, systemId=activeSystem){
  if(!systemId)return source;
  const envs=source.environments.filter(e=>e.system_id===systemId), ids=new Set(envs.map(e=>e.id));
  const result={...source,environments:envs};
  for(const key of ['incidents','jobs','changes','specialists'])result[key]=source[key].filter(r=>ids.has(r.environment_id));
  const resources=new Set([...ids,systemId,...result.incidents.map(r=>r.id),...result.jobs.map(r=>r.id),...result.changes.map(r=>r.id),...result.specialists.map(r=>r.id)]);
  result.audit=source.audit.filter(a=>resources.has(a.resource));
  result.notifications=(source.notifications||[]).filter(n=>resources.has(n.resource));
  return result;
}
function notifications(){
  const ch=data.notification_channel;
  return heading('Alertas que chegam até você.','Incidentes, manutenção, resultado de publicação e falhas de tarefas.',button('mail-settings','Configurar canal SMTP','','primary'))+
  `<div class="warning">${ch?.enabled?'Canal habilitado. Mensagens pendentes serão entregues ao SMTP configurado.':'Canal desabilitado. Nenhum e-mail será enviado até configurar remetente, destinatários e habilitar o canal.'}</div><section class="card"><div class="card-head"><h2>Fila de notificações</h2>${pill(ch?.enabled?'SMTP habilitado':'Aguardando configuração',ch?.enabled?'':'gray')}</div>${data.notifications?.length?`<div class="table-wrap"><table><thead><tr><th>EVENTO</th><th>ESTADO</th><th>TENTATIVAS</th><th>REGISTRO</th></tr></thead><tbody>${data.notifications.map(n=>`<tr><td>${escape(n.action)}</td><td>${pill(n.state,n.state==='failed'?'red':n.state==='sent'?'':'gray')}</td><td>${n.attempts}</td><td>${fmt(n.created_at)}</td></tr>`).join('')}</tbody></table></div>`:empty('Os próximos eventos elegíveis aparecerão nesta fila.')}</section><p class="form-note">“sent” indica aceitação pelo servidor SMTP; não comprova leitura ou entrega na caixa de entrada. Os avisos não incluem credenciais, código-fonte ou logs de alunos. A fila usa até três tentativas com espera progressiva.</p>`;
}
function license(){
  const l=data.license||{}, ai=data.ai_configuration||{};
  return heading('Autorização verificável.','Desenvolvedor: Carlos Antonio de Oliveira Piquet.',button('license-request','Gerar solicitação','','secondary')+button('license-activate','Ativar licença','','primary'))+
    `<div class="connection"><section class="card"><div class="card-head"><h2>Licenciamento da instalação</h2>${pill(l.valid?'Assinatura válida':'Não licenciado',l.valid?'':'red')}</div><div class="timeline"><p>${escape(l.message)}</p><p class="form-note">Edição: ${escape(l.edition||'Pendente')}<br>Validade: ${fmt(l.expires_at)}<br>ID: ${escape(l.license_id||'Não emitida')}</p><p class="form-note">Uso por terceiros depende de autorização assinada via gov.br validada ou reconhecimento em cartório, conferência pelo emissor e licença digital vinculada à instalação.</p><p class="form-note">A edição de desenvolvimento do autor não é certificado cartorial. O Guardian não assina documentos em seu nome.</p></div></section><section class="card"><div class="card-head"><h2>Política de inteligência</h2>${pill('Alto ou superior','gray')}</div><div class="timeline"><p class="code-note">Gerente e especialistas: ${escape(ai.model||'gpt-6.1-sol')}<br>Segurança e banco: ${escape(ai.security_model||'gpt-6-astra')}<br>Raciocínio: ${escape(ai.reasoning||'high')}</p><p class="form-note">Modelos permitidos: GPT-6.1 Sol e GPT-6 Astra. Níveis permitidos: high, xhigh e max. A indisponibilidade não autoriza redução silenciosa do modelo.</p><p class="form-note">CPF e filiação do autor são mantidos em documentação privada, fora da distribuição e dos prompts.</p></div></section></div>`;
}
async function refreshCycle() {
  const requestedSystem=activeSystem, requestedGraph=graphEnvironment;
  try {
    allData = await api('/api/v1/overview');
    const nextData=systemData(allData,requestedSystem);
    const nextGraph=nextData.environments.some(e=>e.id===requestedGraph)?requestedGraph:(nextData.environments.find(e=>e.kind==='local')?.id||nextData.environments.find(e=>['http','agent'].includes(e.kind))?.id||'');
    const nextSamples=nextGraph?await api('/api/v1/environments/'+nextGraph+'/samples'):[];
    if(requestedSystem!==activeSystem||requestedGraph!==graphEnvironment){refreshAgain=true;return;}
    data=nextData;graphEnvironment=nextGraph;samples=nextSamples;
    $('#sync-state').textContent = '● Sincronizado às '+new Date().toLocaleTimeString('pt-BR');
    render();
  } catch(error) {
    $('#sync-state').textContent = 'Conexão pendente';
    if (!data) $('#main').innerHTML = `<section class="card auth"><div class="card-head"><h2>Acesso à estação Guardian</h2></div><div class="timeline"><p>Abra o painel pelo arquivo <strong>Abrir-Painel.ps1</strong> para iniciar uma sessão protegida.</p><pre>.\\lumen10_guardian_ia\\scripts\\Abrir-Painel.ps1</pre><p class="form-note">${escape(error.message)}</p>${button('retry','Tentar novamente','','primary')}</div></section>`;
  }
}
function refresh(){
  refreshAgain=true;
  if(refreshWork)return refreshWork;
  refreshWork=(async()=>{do{refreshAgain=false;await refreshCycle();}while(refreshAgain);})().finally(()=>{refreshWork=null;});
  return refreshWork;
}
function showIncident(id) {
  const i = data.incidents.find(x=>x.id===id), d = parse(i.diagnosis,null);
  modal('Incidente · '+id.slice(0,8), `<div class="detail-meta">${pill(i.severity,'gray')}${statePill(i.state)}</div><h2>${escape(i.title)}</h2><p class="form-note">${escape(parse(i.evidence).summary)}</p>${d?`<h3 class="small">Diagnóstico · ${escape(specialistNames[d.specialist])}</h3><p>${escape(d.summary)}</p><p class="form-note">${escape(d.cause)}</p><p class="form-note">Confiança declarada: ${Math.round(d.confidence*100)}% · Risco: ${escape(d.risk)}. A confiança é avaliação do modelo, não comprovação.</p><pre>${escape(d.test_plan.join('\n'))}</pre>`: '<p class="form-note">A investigação ainda não produziu um diagnóstico.</p>'}<div class="actions">${button('investigate','Investigar com especialista',id,'primary')}${d?.changes?.length?button('repair','Preparar correção e testar',id):''}${button('handoff','Contexto no VS Code',id,'secondary')}</div>`);
}
function showChange(id) {
  const c = data.changes.find(x=>x.id===id), a = parse(c.artifact);
  modal('Alteração · '+id.slice(0,8), `<div class="detail-meta">${statePill(c.state)}${pill('Risco: '+a.risk,'gray')}</div><p class="form-note">Commit: ${escape(a.commit||'Sem commit aprovado')}<br>SHA-256: ${escape(a.sha256||'Sem pacote')}</p><h3 class="small">Diff real</h3><pre>${escape(a.diff)}</pre><h3 class="small">Resultado real dos testes</h3><pre>${escape(a.test_output)}</pre><div class="actions">${c.state==='TESTES_APROVADOS'?button('deploy','Publicar no laboratório',id,'primary')+button('schedule','Agendar para 01h',id):''}${c.state==='RESOLVIDO'?button('rollback','Restaurar versão anterior',id,'danger'):''}</div>`);
}
document.addEventListener('change', async e=>{
  if (e.target.id==='graph-env') {graphEnvironment=e.target.value;await refresh();}
});
document.addEventListener('click', async event=>{
  const system=event.target.closest('[data-system]');if(system){activeSystem=system.dataset.system;graphEnvironment='';samples=[];if(allData){data=systemData(allData);render();}await refresh();return;}
  const nav = event.target.closest('[data-view]'); if(nav){view=nav.dataset.view;render();return;}
  const el = event.target.closest('[data-action]'); if (!el) return;
  const {action,id} = el.dataset;
  try {
    if (action==='go-incidents'){view='incidents';render();return;}
    if (action==='incident'){showIncident(id);return;}
    if (action==='change'){showChange(id);return;}
    if (action==='retry'){await refresh();return;}
    if(action==='threat-review'){await api('/api/v1/security/threat-review','POST');toast('Revisão de fontes oficiais adicionada à fila');await refresh();return;}
    if(action==='threat-report'){const r=allData.threat_reports.find(r=>r.id===id),d=parse(r.diagnosis);modal('Boletim de segurança global',`<p>${escape(d.summary)}</p><p class="form-note">${escape(d.cause)}</p><pre>${escape(JSON.stringify(parse(r.sources,[]),null,2))}</pre>${parse(r.findings,[]).map(f=>`<p class="small"><strong>${escape(f.title)}</strong> ${f.new?pill('Novo','amber'):''}<br>${escape(f.applicability)}<br><a href="${escape(f.url)}" target="_blank" rel="noopener noreferrer">Consultar fonte oficial</a></p>`).join('')}`);return;}
    if(action==='security-profile'){if(!activeSystem)throw new Error('Selecione um sistema nas abas para configurar as tecnologias');const profile=allData.security_profiles?.find(p=>p.system_id===activeSystem);modal('Tecnologias e versões declaradas',`<form id="security-form"><label>Tecnologias (separadas por vírgula)<input name="technologies" required value="${escape(parse(profile?.technologies,['php','moodle']).join(', '))}"></label><label>Versão PHP ou pacote completo instalado (se conhecida)<input name="php_version" value="${escape(parse(profile?.versions).php||'')}"></label><p class="form-note">Use nomes como php, moodle, nginx, apache, mariadb, docker, wordpress. A versão declarada precisa ser conferida; pacotes com backports não devem ser classificados só pelo número upstream.</p><button class="primary">Salvar inventário</button></form>`);return;}
    if(action==='new-system'){modal('Novo sistema monitorado',`<form id="system-form"><label>Nome do sistema<input name="name" required maxlength="100" placeholder="Moodle Lumen10, loja, portal..."></label><p class="form-note">Agrupe neste sistema a URL, o agente e a pasta de código correspondentes. Cada sistema terá seus próprios gráficos e incidentes.</p><button class="primary">Criar sistema</button></form>`);return;}
    if(action==='group-env'){if(!allData.systems?.length)throw new Error('Crie um sistema primeiro');modal('Associar ambiente a um sistema',`<form id="group-form" data-id="${id}"><label>Sistema<select name="system_id" required>${(allData.systems||[]).map(s=>`<option value="${s.id}">${escape(s.name)}</option>`).join('')}</select></label><button class="primary">Associar ambiente</button></form>`);return;}
    if(action==='remote-source'){modal('Conectar código por chave',`<form id="source-form"><label>Nome da conexão<input name="name" required placeholder="Projeto autorizado"></label><label>URL do conector (HTTPS ou túnel local)<input name="base_url" required placeholder="https://guardian.seu-dominio.com.br"></label><label>ID do ambiente de projeto no conector<input name="environment_id" required></label><label>Chave source.read<input name="token" type="password" autocomplete="off" required></label><p class="form-note">O outro Guardian precisa estar instalado junto ao código, licenciado e acessível por um canal seguro. A chave é protegida localmente e permite somente leitura do escopo autorizado.</p><button class="primary">Conectar projeto</button></form>`);return;}
    if(action==='mail-settings'){const ch=data.notification_channel||{};const projects=data.environments.filter(e=>e.kind==='project');if(!projects.length)throw new Error('Cadastre primeiro a pasta do projeto que contém os dados SMTP');modal('Canal de alertas por e-mail',`<form id="mail-form"><label>Pasta com .env / credenciais.md<select name="environment_id">${projects.map(e=>`<option value="${e.id}" ${e.id===ch.environment_id?'selected':''}>${escape(e.name)}</option>`).join('')}</select></label><label>Remetente verificado no provedor<input name="sender" type="email" required value="${escape(ch.sender||'')}"></label><label>Destinatários (separados por vírgula, até 5)<input name="recipients" required value="${escape(parse(ch.recipients,[]).join(', '))}"></label><label><input type="checkbox" name="enabled" ${ch.enabled?'checked':''}> Habilitar envio dos avisos pendentes e novos</label><p class="form-note">A senha permanece nos arquivos locais. SMTP exige TLS/STARTTLS. No Brevo, o remetente deve estar autorizado na conta.</p><button class="primary">Salvar canal</button></form>`);return;}
    if(action==='source-key'){const result=await api(`/api/v1/environments/${id}/source-key`,'POST');modal('Chave de leitura de código · exibida uma vez',`<p class="form-note">Guarde em arquivo protegido no outro Guardian. Escopo source.read, duração de 30 dias. A chave não autoriza executar comandos, ler .env ou publicar. Utilize HTTPS ou túnel SSH.</p><pre>${escape(JSON.stringify(result,null,2))}</pre><p class="form-note">Revogação imediata pelo botão abaixo.</p>${button('revoke-source','Revogar esta chave',result.credential_id,'danger')}`);return;}
    if(action==='revoke-source'){await api('/api/v1/source-keys/'+id,'DELETE');$('#modal').close();toast('Chave revogada');return;}
    if (action==='license-request'){const request=await api('/api/v1/license/activation-request');modal('Solicitação de licença',`<p class="form-note">Entregue esta solicitação ao desenvolvedor junto ao termo assinado. Ela não inclui senhas nem credenciais do Codex.</p><pre>${escape(JSON.stringify(request,null,2))}</pre>`);return;}
    if (action==='license-activate'){modal('Ativar licença assinada',`<form id="license-form"><label>Arquivo JSON de licença nesta máquina<input name="license_path" required placeholder="C:\\Licencas\\guardian-license.json"></label><label>PDF final assinado (licença comercial)<input name="document_path" placeholder="C:\\Licencas\\autorizacao-assinada.pdf"></label><p class="form-note">O desenvolvedor emite a licença depois da conferência da assinatura gov.br ou do reconhecimento em cartório. O arquivo final deve corresponder exatamente ao documento autorizado.</p><button class="primary">Validar e ativar</button></form>`);return;}
    if (action==='new-env') {modal('Conectar ambiente',`<form id="environment-form"><label>Nome do ambiente<input name="name" required placeholder="Moodle · produção" maxlength="100"></label><label>Tipo<select name="kind"><option value="http">Disponibilidade HTTP(S)</option><option value="project">Pasta do projeto · .env e credenciais.md</option><option value="agent">Agente Linux / Windows · telemetria de host</option></select></label><label>URL, caminho da pasta ou identificação do host<input name="target" required placeholder="https://seu-sistema.com.br ou C:\\projetos\\moodle"></label><p class="form-note">A conexão HTTP faz apenas leitura. A conexão de projeto lê localmente os campos autorizados dos arquivos de acesso.</p><button class="primary">Conectar ambiente</button></form>`);return;}
    if (action==='policy') {const e=data.environments.find(x=>x.id===id);modal('Política · '+e.name,`<form id="policy-form" data-id="${id}"><label><input type="checkbox" name="enabled" ${e.enabled?'checked':''}> Monitorar este ambiente</label><label><input type="checkbox" name="auto_ai" ${e.auto_ai?'checked':''}> Acionar IA somente quando houver incidente</label><label><input type="checkbox" name="paused" ${e.paused?'checked':''}> Suspender mudanças neste ambiente (emergência)</label><label>Fuso horário<input name="timezone" value="${escape(e.timezone)}" required></label><label>Janela de manutenção<input name="maintenance" type="time" value="${escape(e.maintenance)}" required></label><p class="form-note">Próxima janela: ${fmt(e.next_window)}. Diagnósticos e monitoramento permanecem disponíveis durante a suspensão de mudanças. A janela não habilita publicação em produção.</p><button class="primary">Salvar política</button></form>`);return;}
    if (action==='vscode'||action==='handoff') {if(bridge){bridge.postMessage({type:action==='handoff'?'handoff':'terminal',incident:id});toast('Solicitação enviada ao VS Code');}else {window.location.href='vscode://lumen10.guardian/open'+(id?'?incident='+encodeURIComponent(id):'');toast('Abrindo a extensão Guardian no VS Code');}return;}
    el.disabled=true;
    if (action==='toggle'){await api('/api/v1/system/monitor','POST',{active:!data.monitoring_active});toast(data.monitoring_active?'Monitoramento pausado':'Guardian ativado. Iniciando medições reais.');}
    if (action==='investigate'||action==='repair') {await api(`/api/v1/incidents/${id}/${action}`,'POST');$('#modal').close();toast(action==='investigate'?'Investigação enviada ao gerente e ao especialista':'Correção adicionada à fila de testes');}
    if (action==='review') {await api(`/api/v1/environments/${id}/review`,'POST');toast('Análise especializada adicionada à fila');}
    if (action==='laboratory'){const result=await api('/api/v1/laboratory','POST');if(activeSystem)await api(`/api/v1/environments/${result.environment_id}/system/${activeSystem}`,'PUT');await refresh();showIncident(result.incident_id);return;}
    if (['deploy','schedule','rollback'].includes(action)){const result=await api(`/api/v1/changes/${id}/${action}`,'POST');$('#modal').close();toast(result.scheduled_at?'Agendado: '+fmt(result.scheduled_at):'Resultado: '+result.state);}
    if(action==='snapshot'){const result=await api('/api/v1/powershell/snapshot','POST');terminalOutput=result.output||'O executor não retornou saída.';render();}
    if(action==='verify'){const result=await api('/api/v1/audit/verify');toast(result.valid?'Cadeia local de auditoria íntegra':'Falha de integridade na cadeia');}
    if(action==='connection'){const result=await api(`/api/v1/environments/${id}/connection`);modal('Acesso local ao projeto',`<pre>${escape(JSON.stringify(result,null,2))}</pre><p class="form-note">Valores de credenciais são usados localmente e não aparecem no painel nem no contexto da IA. SSH exige chave já confiada no known_hosts.</p>${button('ssh-snapshot','Diagnóstico SSH de leitura',id,'primary')}`);}
    if(action==='ssh-snapshot'){const result=await api(`/api/v1/environments/${id}/ssh-snapshot`,'POST');modal('Diagnóstico remoto · somente leitura',`<pre>${escape(result.output)}</pre>`);}
    await refresh();
  } catch(error){toast(error.message);} finally {el.disabled=false;}
});
document.addEventListener('submit', async event=>{
  if (!['environment-form','policy-form','license-form','mail-form','source-form','system-form','group-form','security-form'].includes(event.target.id)) return;
  event.preventDefault(); const form=event.target, values=new FormData(form), submit=form.querySelector('button');submit.disabled=true;
  try {
    if(form.id==='environment-form') await api('/api/v1/environments','POST',{...Object.fromEntries(values),system_id:activeSystem||null});
    else if(form.id==='system-form'){const result=await api('/api/v1/systems','POST',Object.fromEntries(values));activeSystem=result.id;}
    else if(form.id==='security-form')await api(`/api/v1/systems/${activeSystem}/security-profile`,'PUT',{technologies:values.get('technologies').split(',').map(v=>v.trim().toLowerCase()).filter(Boolean),versions:values.get('php_version')?{php:values.get('php_version')}: {}});
    else if(form.id==='group-form')await api(`/api/v1/environments/${form.dataset.id}/system/${values.get('system_id')}`,'PUT');
    else if(form.id==='source-form'){const result=await api('/api/v1/source-connections','POST',Object.fromEntries(values));if(activeSystem)await api(`/api/v1/environments/${result.environment_id}/system/${activeSystem}`,'PUT');}
    else if(form.id==='mail-form') await api('/api/v1/notifications/settings','PUT',{environment_id:values.get('environment_id'),sender:values.get('sender'),recipients:values.get('recipients').split(',').map(x=>x.trim()).filter(Boolean),enabled:values.has('enabled')});
    else if(form.id==='license-form') await api('/api/v1/license/activate','POST',{license_path:values.get('license_path'),document_path:values.get('document_path')||null});
    else await api(`/api/v1/environments/${form.dataset.id}/policy`,'PUT',{paused:values.has('paused'),auto_ai:values.has('auto_ai'),enabled:values.has('enabled'),timezone:values.get('timezone'),maintenance:values.get('maintenance')});
    $('#modal').close();toast('Configuração salva');await refresh();
  } catch(error){toast(error.message);} finally{submit.disabled=false;}
});
async function boot(){
  const fragment=new URLSearchParams(location.hash.slice(1)), ticket=fragment.get('ticket');
  if(ticket&&!bridge){history.replaceState(null,'',location.pathname);try{await api('/auth/exchange','POST',{ticket});}catch(error){toast(error.message);}}
  await refresh();setInterval(refresh,5000);
}
boot();
