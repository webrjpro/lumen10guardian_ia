# Instalação em outros projetos — guia completo

## 1. Posso colocar a pasta dentro de qualquer código-fonte?

Você pode colocar a pasta **ao lado dos arquivos do projeto**, independentemente de a aplicação ser PHP, Moodle, WordPress, Python, Node.js, Java ou .NET. O Guardian é um processo separado: ele não precisa ser importado pelo PHP, incluído no `package.json` da aplicação nem carregado a cada requisição.

**Incluir a pasta não concede suporte automático para corrigir e publicar qualquer tecnologia.** Há quatro capacidades diferentes:

| Capacidade | O que funciona nesta versão |
|---|---|
| Monitorar uma URL HTTP/HTTPS | Funciona para aplicações de qualquer linguagem. Mede status e tempo de resposta. Não comprova login, matrícula ou outros fluxos internos. |
| Monitorar esta máquina Windows | CPU, memória e disco reais, com gráfico e detecção de limiares. |
| Coletar host/logs Linux ou Windows | Coletor fornecido, heartbeat, fila local e ingestão autenticada. A instalação em um servidor externo ainda precisa ser validada naquele ambiente. |
| Ler o projeto local | Descoberta da stack, contexto limitado de arquivos rastreados no Git e inventário dos acessos locais. |
| Diagnosticar com IA | Gerente e especialista são executados pelo Codex autenticado. A qualidade depende das evidências disponíveis. |
| Corrigir, testar, publicar e reverter | Ciclo executável e validado no laboratório Python incluído. O adaptador de produção de outros projetos ainda precisa ser implementado e validado. |

Você não deve interpretar a presença da pasta como autorização para a IA alterar automaticamente seu servidor. O painel informa os limites e bloqueia publicação externa nesta versão.

## 2. Estrutura correta

Exemplo de Moodle, com o Guardian dentro do repositório e fora da raiz pública quando a estrutura permitir:

```text
meu-projeto/
├── .git/
├── .env                       # Acessos locais existentes; não versionar
├── credenciais.md             # Orientações/referências de acesso
├── public/                    # Raiz publicada pelo servidor web, se existir
├── src/                       # Código da aplicação
├── tests/
└── lumen10_guardian_ia/
    ├── guardian/              # Backend, painel, executor, especialistas
    ├── agents/                # Coletor de telemetria
    ├── scripts/               # Instalação, inicialização e validação
    ├── vscode-extension/
    ├── docs/
    ├── tests/
    ├── pyproject.toml
    └── README.md
```

Se a raiz do repositório também for a raiz pública do Moodle/WordPress, **não envie a pasta Guardian para essa raiz pública da produção**. Instale o Guardian apenas na estação administrativa e exclua a pasta dos artefatos publicados. A instalação local não precisa acompanhar o código servido aos visitantes. Não coloque `.env`, chaves ou `credenciais.md` em diretórios públicos.

O Guardian mantém seu banco, tokens, logs, branches de laboratório e artefatos em `%LOCALAPPDATA%\Lumen10Guardian`. Esses dados não ficam na pasta do projeto nem devem entrar no Git. O processo utiliza um bloqueio exclusivo para evitar duas instâncias na mesma base.

## 3. Copiar para um projeto existente

Nesta máquina, você pode usar o instalador de cópia:

```powershell
.\lumen10_guardian_ia\scripts\Copiar-ParaProjeto.ps1 -ProjectPath 'C:\Projetos\MeuMoodle'
```

Ele copia somente os arquivos distribuíveis para `C:\Projetos\MeuMoodle\lumen10_guardian_ia`. Não copia a `.venv`, dados operacionais ou credenciais. Se a pasta de destino já existir, o comando interrompe a operação para não sobrescrever sua instalação.

Também é possível copiar a pasta manualmente, excluindo `.venv`, `node_modules`, caches, `*.egg-info` e pacotes `.vsix`. Não copie `%LOCALAPPDATA%\Lumen10Guardian` para outro computador como forma de instalação: o login do Codex e a proteção DPAPI pertencem ao usuário da máquina de origem.

## 4. Preparar a outra máquina

Instale Python 3.11 ou superior, PowerShell 7, Git e VS Code. Instale e autentique o Codex pelo fluxo oficial do ChatGPT. O comando `codex login status` deve indicar login com ChatGPT. O Guardian também encontra o binário do Codex que acompanha a extensão oficial do VS Code no Windows.

Você não informa sua senha ao Guardian. A conta de cada máquina precisa ter acesso válido ao Codex. Não compartilhe `auth.json` ou uma pasta de perfil do ChatGPT com clientes.

Dentro da pasta do projeto novo:

```powershell
.\lumen10_guardian_ia\scripts\Instalar-Guardian.ps1 -Autostart -Extensao
```

O instalador cria uma `.venv` própria, instala o backend, registra a pasta do projeto ao redor do Guardian, verifica as ferramentas, instala a extensão e configura a inicialização no logon. Conexão de produção não é habilitada por esse processo.

**Licença obrigatória em outra máquina:** abra **Licença e autoria**, gere a solicitação e ative o JSON assinado emitido pelo titular após conferência do termo final assinado pelo gov.br ou reconhecido em cartório. A edição atual é de desenvolvimento do autor. Veja [autoria e emissão](AUTORIA_E_LICENCIAMENTO.md). Sem licença válida, o painel permite configurar e ativar, mas bloqueia operação.

Se a política de execução do Windows bloquear scripts, você pode executar apenas esse processo com:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\lumen10_guardian_ia\scripts\Instalar-Guardian.ps1 -Autostart -Extensao
```

Esse parâmetro vale para o processo iniciado; não modifica permanentemente a política de execução da máquina. Respeite políticas administrativas corporativas existentes.

## 5. Abrir o painel e ativar

```powershell
.\lumen10_guardian_ia\scripts\Abrir-Painel.ps1
```

O endereço padrão é `http://127.0.0.1:8765`. Abra inicialmente pelo script: ele gera um ticket de uso único, válido por dois minutos, e cria uma sessão local de oito horas. Abrir somente o endereço numa janela sem sessão mostra a orientação de login local.

No painel:

1. Clique **Ativar Guardian**. O estado fica persistido entre reinícios.
2. Em **Conectar ambiente**, escolha **Disponibilidade HTTP(S)** e informe o endereço que você está autorizado a monitorar.
3. Cadastre também uma **Pasta do projeto**, se desejar diagnóstico com contexto do repositório e conexão SSH configurada.
4. Em **Ambientes → Configurar**, selecione a investigação automática somente por incidente, o fuso e a janela de manutenção.
5. Confira os gráficos após as primeiras amostras. O painel atualiza a cada cinco segundos; o monitor coleta a cada trinta segundos. Não há histórico anterior à instalação.

Cada ambiente representa uma fonte. Use **Novo sistema** para criar abas independentes e agrupe nele URL, agente e pasta de código. Ao cadastrar um ambiente com a aba selecionada, ele entra naquele sistema; para fontes já existentes, use **Ambientes → Sistema**. A investigação pode receber contexto limitado de até dois projetos associados. O diagnóstico não presume que uma pasta qualquer seja o código real de produção.

**Pausar monitoramento** interrompe novas coletas locais e revisões periódicas. Trabalhos que já estavam na fila continuam. Para bloquear mudanças de um ambiente, marque **Suspender mudanças** na política dele. Nenhuma dessas ações interrompe à força um comando que já começou; isso exige avaliação operacional.

## 6. Integrar com o VS Code

Abra a pasta do seu projeto no VS Code. Na paleta (`Ctrl+Shift+P`):

- **Guardian: Abrir painel** abre o centro de operações dentro do editor.
- **Guardian: Abrir PowerShell** abre um terminal nativo na pasta do Guardian.
- **Guardian: Iniciar serviço local** inicia o backend supervisionado.

Se o Guardian estiver fora do workspace, configure o caminho absoluto em `guardian.home`. A extensão somente executa ações em workspaces confiáveis.

Em um incidente, **Contexto no VS Code** abre um documento de diagnóstico ao lado do Codex. O documento pode ser adicionado ao chat pelo comando da extensão oficial **Add to Codex Chat**. Essa interação é para revisão humana. A investigação automática funciona por `codex exec`: ela não depende de simular teclado, clicar na caixa de mensagem ou manter o editor aberto.

Uma extensão recém-instalada pode exigir recarregar a janela do VS Code. Salve seu trabalho antes de usar **Developer: Reload Window**. Você também pode continuar pelo navegador enquanto isso.

## 7. Usar .env e credenciais.md

O Guardian tem autorização de leitura local desses arquivos na pasta de projeto cadastrada. Ele não executa o conteúdo como shell nem envia os arquivos completos ao modelo. Atualmente reconhece campos estruturados:

```dotenv
SSH_HOST=servidor.exemplo.com
SSH_USER=guardian
SSH_PORT=22
SSH_KEY_PATH=C:/Users/SEU_USUARIO/.ssh/guardian_ed25519
APP_URL=https://aplicacao.exemplo.com
```

Não substitua seu `.env` existente. Acrescente somente os campos necessários, ou registre esses campos em `credenciais.md` no formato `CAMPO=valor` ou `CAMPO: valor`. A leitura do `.env` tem precedência. Variáveis com substituição como `${OUTRA_VAR}` e comandos como `$(...)` não são interpretados.

**Limite atual:** o leitor reconhece rótulos específicos em português, mas não interpreta livremente todas as anotações de acesso nem conecta automaticamente ao banco Moodle por encontrar `DB_PASSWORD`. A conexão SSH implementada usa chave, `BatchMode=yes` e `StrictHostKeyChecking=yes`. Senha SSH não é suportada por esse adaptador. Cadastre e confira o host no `known_hosts` pelo seu terminal antes de usar **Diagnóstico SSH de leitura**.

O botão SSH consulta sistema operacional, uptime, disco e versão do PHP. Não executa SQL, não reinicia serviços e não publica arquivos. Os demais valores do `.env` permanecem no projeto e não são carregados globalmente no processo do Guardian.

## 8. Como ocorre a investigação e a correção

Um evento relevante cria um incidente. Se a IA automática estiver habilitada, o gerente faz a triagem e aciona uma segunda sessão com papel especializado: segurança, PHP/Moodle, infraestrutura, banco de dados ou testes. As tarefas são efêmeras; seus estados e resultados são persistidos no banco e aparecem no painel.

Problemas de segurança recebem especialista de segurança e risco alto. O executor não recebe ordens de shell livres do modelo. Um diagnóstico não equivale à autorização de publicação.

Para exercitar o ciclo executável desta versão:

1. Abra **Correções e releases → Criar laboratório local**.
2. Investigue o incidente com o especialista.
3. Após o diagnóstico, selecione **Preparar correção e testar**.
4. Abra o diff e a saída real dos testes.
5. Publique no laboratório, ou agende pela janela configurada.
6. Use **Restaurar versão anterior** para exercitar o rollback.

O laboratório contém um bug Python conhecido; não é o seu Moodle e não representa validação do seu servidor. A função corrigida aceita apenas uma linguagem restrita de operações de string verificada por AST. Os testes ficam fora do worktree modificável pela IA. O pacote é vinculado a um hash e o backup pertence àquela release.

Para habilitar esse ciclo em outra aplicação será necessário implementar/configurar e validar: caminho do repositório de homologação; escopo de arquivos; suíte confiável de testes; isolamento por contêiner/runner; montagem de dependências; artefato imutável; estratégia de backup; executor da stack; smoke tests e procedimento de recuperação. **Esses adaptadores de produção não estão incluídos como prontos nesta entrega.**

## 9. Vários projetos e várias empresas

Uma instância local pode cadastrar vários ambientes e pastas de projeto. Copiar a pasta para outro repositório na mesma conta Windows não cria automaticamente outro servidor independente: o diretório de dados e a porta padrões são compartilhados por máquina/usuário.

Para uma instância realmente separada, configure `GUARDIAN_DATA` e `GUARDIAN_PORT` antes de iniciar, e ajuste também `guardian.port` na extensão. O instalador de inicialização automática padrão usa um único nome de tarefa; instâncias adicionais exigem tarefas próprias e variáveis persistidas no lançador. O produto não cria automaticamente um SaaS ou uma assinatura comercial ao copiar a pasta.

Tenants têm credenciais e consultas segregadas no backend. Este isolamento lógico foi testado por API. Ele não protege contra um administrador local com acesso ao banco, ao perfil do usuário e à conta do Codex. Clientes mutuamente não confiáveis precisam de processos, perfis e infraestrutura separados, autenticação empresarial, TLS e revisão de segurança antes de oferta comercial.

## 10. A máquina precisa ficar ligada?

Sim. No modelo local que você escolheu, o Windows precisa estar em execução, o usuário precisa ter iniciado sessão e o computador precisa estar conectado à rede para investigar produção e usar o Codex. O VS Code pode ser fechado. Bloquear a tela normalmente preserva os processos; desligar, hibernar ou suspender interrompe a operação. A inicialização instalada é **no logon**, não um serviço de boot sem sessão de usuário.

O supervisor reinicia o backend após falhas com espera progressiva e limite de tentativas. O estado de ativação do monitor permanece salvo. Para cobrir períodos em que seu computador estiver desligado ou sem rede, é necessário um monitor externo independente; ele ainda não foi provisionado. O Guardian não consegue detectar a própria estação desligada a partir dessa mesma estação.

## 11. Segurança de distribuição e Git

Versione código e documentação; exclua `.venv`, caches, `.env`, tokens, chaves e logs operacionais. Confira também a configuração de publicação da aplicação para excluir `lumen10_guardian_ia` dos artefatos públicos. Não faça commit de um `credenciais.md` que já contenha senhas. A leitura local autorizada não torna o arquivo adequado para distribuição.

O painel escuta somente em `127.0.0.1`. Não publique a porta 8765 diretamente na internet. O coletor remoto pode usar um túnel SSH corretamente configurado. Uma central remota exige HTTPS, autenticação e operação própria; não é ativada pelo instalador local.

## 12. Diagnóstico e desinstalação

```powershell
# Verificar ferramentas e autenticação
.\lumen10_guardian_ia\.venv\Scripts\python.exe -m guardian doctor

# Parar o processo supervisionado
.\lumen10_guardian_ia\scripts\Parar-Guardian.ps1

# Desativar inicialização no logon
.\lumen10_guardian_ia\scripts\Remover-Inicializacao.ps1
```

Se o painel disser que a sessão expirou, reabra por `Abrir-Painel.ps1`. Se o Codex não autenticar, use `codex login` e o fluxo oficial. Se o SSH falhar, confira campos estruturados, chave e `known_hosts`. Se a porta estiver ocupada, pare a outra instância ou configure outra porta e outro diretório de dados. Logs do serviço ficam em `%LOCALAPPDATA%\Lumen10Guardian\service.log`.

Para atualizar, pare o serviço, preserve a pasta de dados e os arquivos de acesso do projeto, atualize os arquivos distribuíveis, execute o instalador novamente e valide. Para remover, pare, remova a inicialização e desinstale a extensão no VS Code; depois remova a pasta do Guardian. Os scripts não apagam automaticamente evidências, tokens ou o banco local. Faça backup ou descarte desses dados conforme a política da sua organização.


## 13. Múltiplos sistemas, alertas e inteligência global

Use **Novo sistema** para criar quantas visões forem necessárias dentro dos limites de ambientes da instalação. Cada aba filtra gráficos, fontes, incidentes, tarefas, alterações e auditoria por sistema, preservando também o isolamento entre empresas no backend. Cadastre a URL e associe a pasta/coletores corretos.

A IA só é acionada por incidentes ou pedidos explícitos, com a exceção aprovada de duas revisões de segurança global às **08h e 20h de Brasília**. Cadastre tecnologias e versões em **Segurança global → Tecnologias do sistema**. Veja [fontes, critérios e limites](SEGURANCA_GLOBAL_E_ALERTAS.md).

Para e-mails, configure o canal em **Alertas por e-mail**, escolhendo a pasta com SMTP, um remetente autorizado pelo provedor e os destinatários. Habilitar inclui avisos pendentes. Os testes não enviam mensagens reais. Sem remetente/destinatários habilitados, os eventos ficam na outbox.

Para acesso ao código com chave e discussão de `/guardiania`, veja [conector e publicação](CONEXAO_POR_CHAVE_E_PUBLICACAO.md). A chave não publica um painel nem instala o conector sozinha.


O registro pelo instalador cria automaticamente uma aba de sistema para a pasta do novo projeto. Acrescente a URL e os coletores nessa aba. O instalador usa requirements-runtime.lock como constraints; outra instância da extensão também pode configurar guardian.data e guardian.port.
