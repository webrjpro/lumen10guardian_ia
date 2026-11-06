# Autoria e autorização de uso

O desenvolvedor/titular informado pelo solicitante é **Carlos Antonio de Oliveira Piquet**. O aviso de direitos reservados está em `LICENSE.md`. CPF e filiação foram preservados no arquivo privado `%LOCALAPPDATA%\Lumen10Guardian\legal\DADOS_DECLARADOS_DO_AUTOR.md`, fora da distribuição e dos prompts.

Foi preparada uma minuta privada e preenchível em `output/pdf/Termo_Autorizacao_Guardian.pdf`, na raiz deste workspace. Ela tem duas páginas e oito campos de formulário, conferidos na estrutura e na renderização. O documento contém os dados declarados do autor e não está assinado. Identidade, titularidade e reconhecimento cartorial não foram verificados pelo software. Preencha usuário, projeto, instalação, escopo, prazo e data e revise o instrumento antes de assinar e contratar.

## Assinatura pelo gov.br ou cartório

O serviço oficial permite assinatura com conta gov.br prata ou ouro. Preencha o arquivo final, assine pelo fluxo oficial, confira pelo VALIDAR/ITI e preserve o PDF original assinado. A licença deste produto admite esse caminho de autorização, após conferência pelo emissor. [Assinar pelo gov.br](https://www.gov.br/pt-br/servicos/assinatura-eletronica), [VALIDAR/ITI](https://www.gov.br/pt-br/servicos/realizar-validacao-de-assinaturas-eletronicas-validar).

Reconhecimento em cartório é outro procedimento, inclusive quando eletrônico pelo e-Not Assina. Não o confunda com a licença técnica do Guardian. Nenhum certificado notarial, gov.br ou ICP-Brasil foi emitido pelo código. Formalidades adicionais devem ser avaliadas para o contrato concreto. [Manual e-Not Assina](https://suporte.notariado.org.br/support/solutions/articles/43000659316-e-not-assina-manual-para-clientes).

Não altere o PDF depois de assinado: a assinatura e o hash devem corresponder ao arquivo final. A minuta começa com publicação em produção **não autorizada**; uma ampliação exige escopo específico e validações operacionais.

## Como a licença funciona

A chave privada Ed25519 do emissor fica no perfil privado do autor, protegida por DPAPI nesta máquina. A chave pública acompanha `guardian/issuer-public.pem`. A ferramenta de emissão está em `ferramentas_do_autor`, fora da pasta distribuível. Não copie a privada, o perfil Codex ou os documentos pessoais para clientes.

A licença assinada vincula produto, instalação, fingerprint de máquina/usuário, tenant, capacidades e validade. Licença comercial também vincula hash do PDF final e referência de conferência. O software confere a assinatura do emissor e a integridade do documento; a conferência real do gov.br/cartório é feita pelo emissor, não por uma integração automática com o ITI ou tabelião.

Nesta máquina foi emitida uma licença **author-development**, destinada à implementação local solicitada pelo autor. Ela não atesta ato cartorial e não concede uso comercial a terceiros. Em outra máquina, o painel abre para configuração, mas a operação requer licença válida.

## Ativar outra instalação

1. Instale o Guardian e abra **Licença e autoria → Gerar solicitação**.
2. Entregue ao titular o ID da instalação, fingerprint e tenant junto ao instrumento final assinado.
3. O titular confere as assinaturas, signatários e escopo e emite o JSON de licença com sua chave privada.
4. Em **Ativar licença**, informe o caminho local do JSON e do PDF final. Alternativamente:

```powershell
.\lumen10_guardian_ia\.venv\Scripts\python.exe -m guardian activate --license 'C:\Licencas\license.json' --document 'C:\Licencas\autorizacao-assinada.pdf'
```

Para o emissor, depois da conferência real:

```powershell
.\lumen10_guardian_ia\.venv\Scripts\python.exe .\ferramentas_do_autor\emissor.py issue `
  --installation 'ID_DA_SOLICITACAO' --device-fingerprint 'HASH_DA_SOLICITACAO' `
  --tenant 'TENANT_DA_SOLICITACAO' --document 'C:\Privado\termo-final.pdf' `
  --authorization-method govbr --verification-reference 'REFERENCIA_CONFERIDA_NO_VALIDAR' `
  --attest-document-checked --days 365 --output 'C:\Privado\licenca-cliente.json'
```

Use `--authorization-method notary` para um reconhecimento cartorial efetivamente conferido. A declaração de conferência não é uma verificação automática da autenticidade do PDF: não emita licença com esse parâmetro sem realizar a conferência oficial correspondente.

## Limites da proteção

Ausência de licença, assinatura adulterada, expiração, dispositivo diferente ou tenant fora do escopo bloqueiam novas operações. O PDF vinculado deve continuar íntegro. A licença é offline e não consulta revogação remota automaticamente.

Um administrador local com acesso ao código pode alterar o verificador; não há proteção absoluta contra esse adversário. Uma oferta comercial amadurecida também requer instaladores/binários assinados, proteção de atualizações, revogação distribuída, infraestrutura e revisão contratual. Bibliotecas de terceiros mantêm suas licenças próprias.
