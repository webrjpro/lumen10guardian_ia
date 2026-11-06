# Configuração de conexões — somente referências e exemplos

Os valores reais pertencem ao `.env` ou arquivo privado `credenciais.md` do projeto cadastrado. Este arquivo de documentação não contém acessos reais.

```dotenv
SSH_HOST=servidor.exemplo.com
SSH_USER=guardian
SSH_PORT=22
SSH_KEY_PATH=C:/Users/SEU_USUARIO/.ssh/guardian_ed25519
SMTP_HOST=smtp.seu-provedor.com
SMTP_PORT=587
SMTP_USER=usuario-smtp
SMTP_PASSWORD=SUBSTITUIR_SOMENTE_NO_ARQUIVO_PRIVADO
APP_URL=https://aplicacao.exemplo.com
```

O painel de e-mail guarda remetente, destinatários e estado habilitado no banco do tenant; a senha SMTP permanece no arquivo privado e é usada apenas pelo transporte. O leitor não exporta todas as variáveis do `.env` para o processo e não interpreta shell ou interpolação.

Chaves de código `source.read` são separadas de tokens de agente, sessão humana e licença. Guarde cada uma em local protegido e revogue quando não forem mais necessárias. A chave privada do emissor de licenças não pertence ao cliente e nunca acompanha a distribuição.
