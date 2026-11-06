# Lumen10 Guardian AI

Monitor local com painel, Codex autenticado com ChatGPT, especialistas efêmeros e PowerShell. A pasta `lumen10_guardian_ia` pode ser incluída no repositório de outro projeto como componente auxiliar.

**Estado desta entrega: versão local funcional 0.1.0.** Monitoramento e diagnóstico funcionam sem chave de API dedicada. O ciclo de correção, testes, publicação e rollback está implementado e foi validado com IA real no laboratório Python fornecido. Publicação no Moodle/produção ainda não está habilitada. Este código não é um SaaS comercial completo.

## Abrir agora

No PowerShell, na pasta que contém `lumen10_guardian_ia`:

```powershell
.\lumen10_guardian_ia\scripts\Abrir-Painel.ps1
```

O serviço inicia em segundo plano e o navegador recebe um acesso temporário. Clique **Ativar Guardian** para iniciar a coleta. No VS Code, use a paleta de comandos e execute **Guardian: Abrir painel**. A extensão foi instalada nesta máquina.

## Documentação

- [Instalar e integrar em outros projetos](docs/INSTALAR_EM_OUTROS_PROJETOS.md) — passo a passo, compatibilidade, exemplos, migração e problemas comuns.
- [Arquitetura e decisões](docs/ARQUITETURA.md).
- [Operação, credenciais e recuperação](docs/OPERACAO_E_SEGURANCA.md).
- [Estado real da entrega e aceites](docs/ENTREGA_E_VALIDACAO.md).
- [Contrato de API](docs/API.md).
- [Campos de conexão](docs/credenciais.md).

## Instalação nova

Requisitos: Windows com Python 3.11+, PowerShell 7, Git e Codex CLI. VS Code é necessário para a integração com o editor; o monitor trabalha com o editor fechado.

```powershell
.\lumen10_guardian_ia\scripts\Instalar-Guardian.ps1 -Autostart -Extensao
.\lumen10_guardian_ia\scripts\Abrir-Painel.ps1
```

O login do Codex é feito pelo fluxo oficial do ChatGPT. E-mail, senha e tokens de login não devem ser adicionados ao projeto. A disponibilidade da IA depende de internet, autenticação, sandbox funcional e limites da conta. [Documentação oficial: Codex não interativo](https://learn.chatgpt.com/docs/non-interactive-mode).

## Verificação de desenvolvimento

```powershell
cd .\lumen10_guardian_ia
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check guardian tests agents scripts
```

Aceites adicionais: `scripts/validar_codex_real.py` usa **duas sessões reais** do Codex e consome limites da conta; `scripts/validar_painel.py` requer Playwright e Chrome. Veja os relatórios JSON em `docs/`.


Guias adicionais: [autoria e autorização assinada](docs/AUTORIA_E_LICENCIAMENTO.md), [código por chave e endereço público](docs/CONEXAO_POR_CHAVE_E_PUBLICACAO.md), [segurança global e avisos](docs/SEGURANCA_GLOBAL_E_ALERTAS.md). A IA responde a incidentes e a pedidos explícitos; há duas revisões globais programadas por dia, às 08h e 20h de Brasília.
