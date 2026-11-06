# Código por chave e endereço público

## Conectar outro código-fonte

Uma chave autentica permissões em um conector existente; ela não cria, sozinha, acesso ao disco de um servidor. Instale um Guardian autorizado junto ao código, cadastre a pasta como ambiente de projeto e use **Ambientes → Gerar chave de código**. O token `source.read` é exibido uma vez, vale 30 dias, pertence àquele tenant/ambiente e pode ser revogado.

No outro Guardian, use **Ambientes → Conectar código por chave**. Informe o endereço HTTPS do conector (ou túnel por loopback), ID do ambiente e token. O token é protegido localmente e não é enviado ao modelo. O gateway fornece inventário e leitura de fontes permitidos dentro da raiz fixa. Há limites de arquivos e tamanho, bloqueio de traversal e de links que escapam da raiz.

São aceitas extensões de código como PHP, Python, JS/TS, Java, C#, Go, Ruby, C/C++ e outras declaradas no conector. `.env`, credenciais, diretórios internos e dados de alunos não são publicados como código. Credenciais são usadas localmente pelos adaptadores autorizados. Uma chave de leitura não autoriza shell, edição, banco ou implantação. O contexto inicial da IA é limitado; o acesso ao repositório não significa carregar todos os arquivos em cada prompt.

Para revogar, use o botão da criação ou `DELETE /api/v1/source-keys/{credential_id}` autenticado como owner. Tokens de ingestão do coletor são diferentes e não dão acesso ao código.

## /guardiania e painel remoto

Um caminho como `https://www.lumen10.com.br/guardiania` é viável como arquitetura, mas **não foi publicado**. O painel atual foi validado para loopback e extensão VS Code. URLs de assets/API, base path, autenticação pública e cookies ainda precisam de adaptação e validação para um subdiretório remoto.

Não copie a pasta para a raiz pública do Moodle. O Guardian deve operar como processo separado. Para um painel público, será necessário TLS, autenticação empresarial/MFA, cookies seguros, controle de origem, monitor independente e uma implantação validada. Um subdomínio separado também é uma opção de arquitetura; nenhum DNS foi criado.

Somente a API de leitura por token poderia ser encaminhada sob `/guardiania/api/v1/projects/` por um proxy revisado. O arquivo `infra/nginx-source-gateway.example.conf` é um exemplo comentado, não aplicado. Ele não publica o painel administrativo. A chave pertence ao header Authorization, nunca à URL ou ao log.

## O arquivo de acesso fornecido

Foram identificados acessos de SSH, MariaDB, R2 e SMTP sem reproduzir os valores nos documentos distribuíveis. O leitor reconhece os campos explícitos de SSH/SMTP e alguns rótulos do documento. SSH depende de uma chave válida nesta máquina e de host previamente conferido; a anotação atual não forneceu esse caminho válido. A senha root não foi usada como fallback silencioso.

SMTP possui outbox, configuração por tenant, TLS e retries. É preciso configurar remetente verificado e destinatários no painel e habilitar o envio; os testes não enviaram e-mail real. Banco e R2 não foram acionados nem modificados. Um futuro armazenamento de backups deve ser privado, criptografado, verificável e com recuperação testada; não se deve presumir que um bucket público existente é adequado.

Cada sistema pode agrupar URL, coletor e fontes locais/remotas. Use **Novo sistema**, selecione sua aba e cadastre os ambientes; para fontes existentes, use o botão **Sistema**. A investigação recebe o contexto limitado dos projetos associados, enquanto dados, incidentes, gráficos e alterações continuam vinculados à organização e ao ambiente corretos.
