# Entrega 0.1.0 — estado verificável

Data: 06/11/2026. Desenvolvedor/titular informado: Carlos Antonio de Oliveira Piquet.

Esta é uma versão **local funcional**, organizada na pasta `lumen10_guardian_ia`, com contratos e persistência vinculados à organização. Não é a conclusão de todas as fases comerciais da especificação original.

## Implementado e exercitado

| Componente | Evidência |
|---|---|
| Painel profissional com ativação e nove seções | Chrome headless, desktop e celular; sem erros de JavaScript ou overflow horizontal no aceite |
| Abas por sistema | Estação Guardian e Lumen10 HTTP, com troca de fontes/gráficos e escopo de incidentes verificados |
| Telemetria real | CPU/memória/disco locais e respostas HTTP; nenhuma série histórica simulada |
| Portal e cursos Lumen10 | Observação pública por HTTP; últimas medições desta sessão retornaram 200 |
| IA de alta capacidade | GPT-6.1 Sol high executado de verdade; Astra high configurado para segurança/banco; nenhuma família inferior aceita |
| Gerente + especialista | Sessões separadas, tarefas persistidas e trilha auditável |
| Código por chave | Gateway com raiz fixa, expiração, revogação, exclusão de credenciais/dados e consumidor com token protegido |
| Segurança global | Agendamento 08h/20h BRT, testes de idempotência, fontes CISA/PHP consultadas realmente e relatório de correspondências potenciais |
| PowerShell | Script fixo de snapshot executado; terminal completo disponibilizado na extensão VS Code |
| Integração VS Code | VSIX empacotado e instalação local realizada; interface web validada em Chrome, não por automação do host nativo do VS Code |
| Reparo, regressão, publicação e rollback | Ciclo real no laboratório Python, incluindo correção por Codex real e três regressões aprovadas |
| Isolamento e segurança | 47 testes automatizados passando, incluindo tenants, escopos, revogação, CSRF/Host, gates, licença, feeds, instalação idempotente e rejeição de propostas perigosas no laboratório |
| E-mail | Worker/outbox/TLS/retries e configuração reais; transporte substituído apenas nos testes, sem envio de mensagem real |
| Licenciamento | Assinatura Ed25519, validade, instalação/dispositivo/tenant, documento vinculado e edição de desenvolvimento identificada |
| Documentação de autorização | Minuta PDF preenchível, duas páginas e oito campos canônicos/aparências conferidos e renderizados com Poppler |
| Portabilidade | Cópia testada para outra pasta, sem `.venv`, dados operacionais ou chave privada; constraints de runtime e inventário de dependências gerados |
| Operação residente | Serviço supervisionado oculto, tarefa de logon registrada, parada/reinício sem servidor órfão verificados |

## Arquivos de evidência

- `test-results.xml`: último aceite automatizado. Há um aviso de depreciação de compatibilidade do TestClient; os testes passaram.
- `aceite-codex-real.json`: duas sessões reais, modelo solicitado, high, commit, pacote, testes, publicação e restauração do fixture.
- `aceite-painel.json` e `screenshots/`: navegação, abas, responsividade e dados reais.
- `SBOM_RUNTIME.json`: inventário de versões de runtime; não representa certificação formal de SBOM ou conformidade.
- `requirements-runtime.lock`: constraints das dependências exercitadas. `requirements-dev.lock` inclui ferramentas opcionais de QA.

CI está configurada em `.github/workflows/test.yml`; não foi executada em um repositório remoto nesta sessão. A instalação da extensão pode exigir recarregar a janela do VS Code depois de salvar o trabalho.

## Estado operacional entregue

O monitor local está ativo, com coleta a cada 30 segundos e atualização do painel a cada cinco segundos. A IA não é chamada em cada amostra saudável. Incidentes e pedidos explícitos acionam análise; as duas revisões globais são a exceção programada. O histórico preserva execuções de validação anteriores às últimas alterações de política.

O canal de e-mail permanece **desabilitado**: faltam definição de remetente verificado e destinatários. Os valores SMTP existentes são lidos localmente quando o operador habilitar o canal. A interface permite revisar a configuração antes disso.

Há uma licença local de desenvolvimento do autor. Nenhum documento foi assinado pelo gov.br ou reconhecido em cartório pelo software. O PDF é uma minuta para preenchimento, revisão e assinatura real. A chave privada do emissor e os dados pessoais completos ficam fora do código distribuível.

## Dependências externas e recursos ainda não habilitados

- Conexão administrativa da VPS, inventário real do PHP/pacotes e repositório do Moodle: não validados. O arquivo fornecido não apontou uma chave privada válida para o adaptador SSH atual; senha root não foi usada como fallback.
- Alteração e implantação em Moodle/produção: não implementadas como adaptador validado. O ciclo executável entregue é o laboratório Python, identificado como tal.
- Homologação de clientes, runners isolados por stack, backup/restauração de banco e testes Moodle: dependem da infraestrutura real. Docker estava instalado, com daemon indisponível no levantamento; nenhum teste em contêiner foi declarado aprovado.
- Publicação do painel em `/guardiania` e DNS/subdomínio: não realizados. Há somente um exemplo comentado de proxy para leitura de código, que ainda exige revisão e homologação.
- Banco MariaDB e R2 existentes: não foram acionados ou modificados.
- Coletor Linux: código e unidade systemd fornecidos; execução após boot e integração com uma VPS Linux real não foram ensaiadas.
- Disponibilidade sem logon ou com PC suspenso/desligado: não fornecida pelo modelo local. É necessário monitor externo e operação de servidor para essa cobertura.
- OIDC/MFA, cobrança, planos, SLA comercial, assinatura de instaladores, revogação distribuída de licenças e auditoria externa imutável: não prontos nesta versão.

Nenhuma operação administrativa modificou o Moodle, banco, nginx, DNS ou armazenamento da produção durante a entrega. As observações públicas HTTP não comprovam o funcionamento de todos os fluxos dos alunos. Notícias globais não comprovam que a versão instalada está vulnerável e não autorizam atualização automática.

## Abrir e instalar

Nesta máquina, execute `Iniciar-Guardian.ps1` na raiz do workspace, ou `scripts/Abrir-Painel.ps1` dentro da pasta distribuível. Para instalar em outro projeto, siga `INSTALAR_EM_OUTROS_PROJETOS.md`; para autorização, `AUTORIA_E_LICENCIAMENTO.md`; para avisos globais, `SEGURANCA_GLOBAL_E_ALERTAS.md`.
