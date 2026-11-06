# API local v1

Base padrão: `http://127.0.0.1:8765`. O esquema OpenAPI atual está em `GET /api/v1/openapi.json`, autenticado. O painel usa cookie de sessão; integrações usam `Authorization: Bearer TOKEN`. Não coloque tokens na URL.

| Método | Caminho | Autorização / finalidade |
|---|---|---|
| GET | `/healthz` | Saúde mínima pública em loopback |
| POST | `/auth/exchange` | Consome ticket local de uso único |
| POST | `/auth/logout` | Revoga sessão atual |
| GET | `/api/v1/overview` | Dados somente do tenant autenticado |
| POST | `/api/v1/system/monitor` | Owner; ativa/pausa coleta do próprio tenant |
| POST | `/api/v1/environments` | Owner; HTTP, projeto local ou agente |
| PUT | `/api/v1/environments/{id}/policy` | Owner; IA automática, suspensão, fuso e janela |
| GET | `/api/v1/environments/{id}/samples` | Histórico limitado de amostras do tenant |
| GET | `/api/v1/environments/{id}/connection` | Inventário saneado do projeto |
| POST | `/api/v1/environments/{id}/ssh-snapshot` | Owner; comando remoto fixo de leitura |
| POST | `/api/v1/environments/{id}/agents` | Owner; emite token de ingestão, devolvido uma vez |
| DELETE | `/api/v1/agents/{hash}` | Owner; revoga agente do tenant |
| POST | `/api/v1/telemetry/events` | Agente vinculado ao ambiente; idempotência por evento |
| POST | `/api/v1/telemetry/heartbeat` | Agente; métricas numéricas validadas |
| POST | `/api/v1/incidents/{id}/investigate` | Owner; enfileira gerente e especialista |
| POST | `/api/v1/incidents/{id}/repair` | Owner; pipeline do laboratório |
| POST | `/api/v1/environments/{id}/review` | Owner; revisão por IA sob demanda |
| POST | `/api/v1/laboratory` | Owner; aplicação sintética com bug real |
| POST | `/api/v1/changes/{id}/deploy` | Owner; publicação no laboratório após gates |
| POST | `/api/v1/changes/{id}/schedule` | Owner; agenda próxima janela local |
| POST | `/api/v1/changes/{id}/rollback` | Owner; recuperação da release de laboratório |
| POST | `/api/v1/powershell/snapshot` | Owner; script fixo, sem shell livre |
| GET | `/api/v1/audit/verify` | Verifica cadeia local do tenant |
| PUT | `/api/v1/notifications/settings` | Owner; opt-in de alertas SMTP |
| POST | `/api/v1/environments/{id}/source-key` | Owner; chave `source.read`, 30 dias |
| DELETE | `/api/v1/source-keys/{hash}` | Owner; revogação imediata |
| GET | `/api/v1/projects/{id}/source/manifest` | Owner ou chave `source_reader` daquele ambiente |
| GET | `/api/v1/projects/{id}/source/file?path=...` | Código permitido, tamanho limitado, raiz fixa |
| POST | `/api/v1/source-connections` | Owner; conecta gateway e protege token local |
| GET | `/api/v1/license/activation-request` | Owner; dados técnicos para emissão de licença |
| POST | `/api/v1/license/activate` | Owner; verifica licença e documento locais |

Para uma chave de código, o cliente usa o ID do ambiente do gateway, não o ID de outro projeto nem o tenant informado livremente. Uma chave não pode acessar `/overview`, executar shell ou elevar-se a owner. Respostas 404 escondem recursos de outro tenant; escopos incompatíveis retornam 403; ausência/revogação de credencial retorna 401. Conflitos de política/licença retornam 409.

Não existem endpoints genéricos de SQL, senha de root, deploy de comandos do modelo, limpeza de logs ou alteração de políticas pela IA. O OpenAPI serve como contrato executável; os exemplos dos documentos originais não implementados não são apresentados como rotas existentes.


Rotas adicionais de sistemas e inteligência:

- `POST /api/v1/systems`: cria sistema do tenant.
- `PUT /api/v1/environments/{id}/system/{system_id}`: associa fonte ao sistema, com validação do tenant nos dois recursos.
- `PUT /api/v1/systems/{id}/security-profile`: tecnologias e versões declaradas.
- `POST /api/v1/security/threat-review`: solicita uma revisão global por fontes oficiais.

O overview inclui sistemas, perfis e relatórios do tenant. As abas são visões de sistemas do mesmo proprietário; a autorização entre empresas continua no backend.
