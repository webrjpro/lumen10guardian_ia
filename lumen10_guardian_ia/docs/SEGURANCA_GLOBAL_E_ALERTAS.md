# Incidentes locais e inteligência de segurança global

## IA somente quando necessária, com duas revisões programadas

O monitor determinístico coleta sinais continuamente sem chamar um modelo para cada medição. Incidentes com IA automática habilitada acionam o gerente e um especialista; pedidos explícitos do operador também podem acionar uma análise. A revisão genérica automática a cada três horas foi removida conforme a orientação posterior do proprietário.

A exceção programada são **duas revisões de segurança global por dia, às 08h e 20h de America/Sao_Paulo**. Esse fuso e essas janelas estão explícitos no módulo `threat_intelligence.py`. A nova instalação inicia na próxima janela; o botão **Segurança global → Analisar agora** permite solicitar antes. Reinícios preservam a última janela processada. Se a máquina ficar desligada, o sistema não trabalha nesse período e retoma a última janela vencida, sem uma rajada de todas as execuções perdidas.

Cada revisão é um job com gerente e especialista de segurança: portanto duas revisões podem usar quatro sessões de IA por dia, além de incidentes, pedidos e eventuais retries. O limite diário de reservas de análise é 32 por tenant, com até três tentativas por job. Falta de conectividade, conta, limite ou licença é registrada, não interpretada como sistema seguro.

## Fontes e correspondência

O conector consulta o catálogo CISA KEV, com espelho oficial mantido pela CISA como fallback, e os releases oficiais de segurança do PHP por branch suportada. Não precisa de chave de API de IA ou de uma chave para esses feeds públicos. [CISA KEV e espelho oficial](https://github.com/CISAGov/kev-data), [releases PHP](https://www.php.net/releases/).

Na validação desta entrega houve consulta real aos feeds e identificação de registros de segurança. Isso não foi usado como prova de que a produção da Lumen10 está vulnerável. A versão efetiva do PHP instalado e o pacote da distribuição não foram confirmados por SSH.

Na aba do sistema, configure **Segurança global → Tecnologias do sistema**. Declare tecnologias e versões conhecidas; não invente valores. Sem inventário, a revisão usa um conjunto explícito de tecnologias web comuns e informa a incerteza. Correspondência de produto/tecnologia é potencial: backports, configuração, exposição e versões afetadas precisam ser conferidos antes de concluir impacto. KEV não contém todas as vulnerabilidades do mundo, e o conector não representa uma certificação de segurança completa.

O modelo analisa os boletins como dados não confiáveis e gera um relatório estruturado. Nem notícias, nem instruções nos feeds podem autorizar comandos, correção direta de produção ou redução das políticas. Uma atualização PHP exige compatibilidade, homologação, testes e recuperação do projeto concreto.

## E-mail e deduplicação

Novos avisos entram na outbox para o responsável configurado. O resumo inclui tipo de aviso, correspondência potencial, incertezas e links para fontes oficiais. Avisos já conhecidos não geram um e-mail novo a cada rodada; mudança no escopo/inventário pode tornar um aviso novo para aquela configuração. Falha de fonte gera aviso de cobertura parcial.

Avisos de incidentes locais incluem severidade no assunto: P0 emergência, P1 alta, P2 média e P3 baixa. Warnings/notices/deprecações do coletor são P3; erros e falhas têm classificação própria. Isso depende de configurar os logs relevantes e o coletor no servidor. Dois timestamps do mesmo erro são normalizados para evitar um incidente/e-mail por linha repetida.

Um “bug fantasma” sem sinal observável não pode ser prometido como detectável: são necessários logs, telemetria, testes funcionais ou reprodução. O sistema registra essa incerteza e não declara correção sem evidência.

No painel **Alertas por e-mail**, escolha a pasta com SMTP, remetente verificado e destinatários e habilite o canal. O envio está desabilitado na entrega, porque os destinatários e o remetente verificado ainda não foram definidos. Nenhum teste enviou mensagem real. Habilitar o canal inclui avisos pendentes; “sent” significa aceitação pelo SMTP, não prova de leitura.
