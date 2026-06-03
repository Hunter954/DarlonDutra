# Landing Page Darlon Dutra 1400

Landing page em Python Flask com identidade visual preto/amarelo, foto do candidato, logo do partido, formulário de apoio, galeria com upload de imagens e banco PostgreSQL.

## Rodar local

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Acesse `http://localhost:5000`.

## Admin

Acesse `/admin?key=SUA_SENHA` usando o valor definido em `ADMIN_PASSWORD`.

## Railway

1. Crie um projeto no Railway e conecte o repositório GitHub.
2. Adicione um serviço PostgreSQL.
3. Crie um Volume e monte em `/app/uploads`.
4. Configure as variáveis abaixo.
5. Deploy automático pelo Procfile: `web: gunicorn run:app`.

## Variáveis de ambiente

```env
SECRET_KEY=gere-uma-chave-segura
DATABASE_URL=${{Postgres.DATABASE_URL}}
UPLOAD_FOLDER=/app/uploads
ADMIN_PASSWORD=senha-forte-admin
CAMPAIGN_NUMBER=1400
CANDIDATE_NAME=Darlon Dutra
CANDIDATE_ROLE=Deputado Federal
CAMPAIGN_CNPJ=00.000.000/0000-00
LEGAL_NOTICE=De acordo com a legislação eleitoral vigente.
INSTAGRAM_URL=https://www.instagram.com/darlondutra/
PARANA_POP_URL=https://www.paranapop.com.br/
PARANA_POP_INSTAGRAM=https://www.instagram.com/parana.pop/
```

No Railway, o nome exato da referência do Postgres pode variar. Se a variável automática já vier como `DATABASE_URL`, use ela diretamente.

## Correção Railway / Railpack

Se o build falhar com `No GitHub artifact attestations found for python@3.11.9`, este projeto já inclui `mise.toml` desativando a verificação de attestation do Python no Railpack.

Como reforço, você também pode adicionar no Railway:

```env
MISE_PYTHON_GITHUB_ATTESTATIONS=false
```


## Apoio com Instagram

A nova seção `Eu apoio` salva o @ do Instagram em uma tabela própria (`social_support`) e tenta buscar a foto pública do perfil. Como o Instagram pode bloquear ou alterar a página, existe fallback automático para avatar externo por username.

Variável opcional no Railway:

```env
SOCIAL_SUPPORT_BASE_COUNT=4000
```

Ela define o número inicial exibido no contador de apoiadores. Os novos apoios entram somando em cima desse valor.
