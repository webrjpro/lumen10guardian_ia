# Operação, acessos e recuperação

## Inicialização

Use `scripts/Abrir-Painel.ps1`. O lançador inicia um supervisor Python oculto e abre o navegador com ticket único. `Instalar-Inicializacao.ps1` registra tarefa no logon deste usuário; há fallback para Startup se a tarefa não puder ser registrada. Isso foi registrado nesta máquina, mas reinício completo/logoff ainda não foi ensaiado.

A máquina deve permanecer ligada, acordada e com sessão iniciada. O editor pode ser fechado. Falhas do backend recebem reinício com espera progressiva e limite de dez tentativas; consulte `service.log` em caso de interrupção persistente. `Parar-Guardian.ps1` solicita parada ao supervisor. Um processo iniciado diretamente em primeiro plano deve ser encerrado no próprio terminal.

## Ativação, pausa e emergência

**Ativar Guardian** persiste a ativação do tenant e desperta o monitor para coleta imediata. **Pausar monitoramento** interrompe novos ciclos e revisões periódicas; não cancela investigações já enfileiradas nem notificações explicitamente habilitadas. Na política de cada ambiente, **Suspender mudanças** bloqueia novas correções e publicações, preservando diagnóstico e observação. Não interrompe à força uma operação que já começou.

O monitor local mede CPU, memória e disco; HTTP mede status e latência sem seguir redirects. O indicador de disponibilidade da estação representa a proporção de amostras que passaram pelos critérios de saúde, não um SLA de uptime do Moodle. Um HTTP 200 não verifica matrícula, login ou avaliação. Gráficos mostram apenas o período medido; não há dados históricos simulados.

Dois resultados locais/HTTP consecutivos com falha abrem incidente. Agente remoto sem heartbeat por mais de 120 segundos é sinalizado. Uma revisão periódica analisa a telemetria disponível, não constitui pentest completo. Um monitor independente é necessário para detectar esta estação desligada; ele não foi provisionado nesta entrega.

## Credenciais existentes

O arquivo de acesso fornecido foi analisado localmente e excluído do Git. O projeto identificou SSH, MariaDB, R2 e SMTP. Não foi estabelecida conexão remota SSH: a configuração presente não fornece um caminho válido de chave privada para o adaptador atual. Não houve alteração no banco, Moodle, armazenamento, nginx ou DNS.

O leitor aceita `SSH_HOST`, `SSH_USER`, `SSH_PORT`, `SSH_KEY_PATH`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`, `APP_URL`, `MOODLE_URL`. Também reconhece os rótulos explícitos `IP do Servidor`, `Usuário`, `Porta`, `Chave SSH configurada`, `Servidor SMTP`, `Usuário SMTP`, `Chave/Senha SMTP`. Uma anotação “chave configurada: sim” não é um arquivo de chave válido.

SSH exige chave existente, host previamente conferido em `known_hosts`, autenticação não interativa e verificação estrita do host. O adaptador não usa senha root e não desativa a conferência de identidade do servidor para “fazer funcionar”. O inventário retorna nomes de campos e capacidades, não valores de passwords.

Não reutilize credenciais administrativas de produção para uma futura homologação. Testes de código de clientes exigirão um runner isolado e credenciais específicas. Os filtros de segredos são heurísticos; fontes sensíveis devem ser minimizadas antes da coleta.

## E-mail e avisos de manutenção

O worker usa uma outbox persistida na mesma transação do evento auditado. São elegíveis: incidente novo, release agendada, início, conclusão, restauração, falha de implantação e tarefa definitivamente falha. Alertas repetidos do mesmo incidente não criam um e-mail por amostra.

O envio fica desabilitado por padrão. No painel **Alertas por e-mail → Configurar canal SMTP**, selecione a pasta com os dados SMTP, informe remetente verificado no provedor e até cinco destinatários, e habilite o canal. Habilitar inclui avisos pendentes. O Brevo usa a chave SMTP, que é distinta de chave de API. [Documentação SMTP Brevo](https://developers.brevo.com/docs/smtp-integration).

Transporte exige TLS/STARTTLS nas portas 465 ou 587, com validação de certificado. A senha é lida no momento do envio e não vai ao prompt. Mensagens contêm tipo de evento, identificador e data; detalhes sensíveis ficam no painel autenticado. “sent” significa aceitação pelo SMTP, não leitura ou entrega comprovada. Há até três tentativas com backoff. Um crash depois da aceitação SMTP e antes do registro pode duplicar o aviso; o Message-ID permanece estável.

Nenhum e-mail real foi enviado no aceite: os testes do worker usam transporte local explicitamente substituído. Não há remetente e destinatários habilitados na instalação entregue.

## Backup da estação

O banco ativo usa WAL. Para um backup consistente, use a API `sqlite3.Connection.backup` ou pare o supervisor e copie a base juntamente com a pasta de dados. Preserve `fixtures/` e seus artefatos se precisar manter os laboratórios restauráveis. Proteja também licenças, PDFs finais e referências de conexão conforme sua política; eles podem conter dados privados.

Não copie a chave privada do emissor para clientes ou para a pasta da aplicação. Faça um backup privado e seguro conforme o ambiente do autor; DPAPI vincula a recuperação ao perfil/máquina Windows. O Guardian não tem cópia na nuvem dessas chaves e não implementa recuperação de conta externa.

Na restauração, pare a instância, preserve o estado anterior para investigação, restaure uma cópia verificada e execute testes e verificação da auditoria antes de retomar. SQLite, arquivos de laboratório e eventuais backups de banco da aplicação são coisas diferentes; restaurar um não restaura os demais.

## Falhas e reconciliação

Sem IA, monitoramento continua; jobs falham/reentram dentro dos limites e depois aguardam atenção. Sem licença válida, novas coletas e operações autorizadas são bloqueadas, enquanto o painel permanece disponível para ativação e consulta. Sem testes ou backup, a release é recusada. Um pacote adulterado não é implantado.

Após interrupção durante uma implantação de laboratório, compare o hash de `live/app.py`, o pacote e o backup da release antes de retomar. O sistema não repete automaticamente uma release cuja lease expirou. Não existe promessa de execução exatamente uma vez em todos os efeitos externos.

## Ameaças e limites de confiança

O painel escuta somente loopback e usa validação de Host, Origin em mutações, cookies HttpOnly/SameSite e CSP. A extensão conserva a credencial na memória do host; o frontend do webview usa mensagens e não recebe o token da sessão. Tokens de fonte ficam protegidos por DPAPI no Windows.

O banco e os arquivos pertencem ao usuário Windows. Um administrador do host pode alterar código, banco, chave pública e relógio; o produto não apresenta licenciamento local ou auditoria como proteção absoluta contra esse adversário. A cadeia de hashes detecta alterações internas verificáveis, mas não comprova sozinha ausência de truncamento da cauda. Para prova independente, será necessário ancorar/exportar eventos em armazenamento confiável externo.

Logs, código e documentos são dados não confiáveis. O modelo não recebe endpoint de shell, comandos administrativos não são derivados desses textos e a publicação passa por gates independentes. A sandbox de leitura do Codex não é cofre de segredos nem isolamento por tenant contra o próprio perfil. Clientes não confiáveis precisam de máquinas/perfis/runners separados.
