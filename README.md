# Ascencia Keyce — génération et publication intelligente des emplois du temps

Projet associé au thème : **« Conception et mise en œuvre d’un système intelligent pour la génération et la publication automatique des emplois du temps universitaires basé sur l’intelligence artificielle : cas d’Ascencia Keyce »**.

Le prototype combine un moteur déterministe de contraintes, un score heuristique d’équilibrage et un agent IA Gemini/LangGraph. Il génère un brouillon hebdomadaire, en explique le rapport, impose une validation humaine et publie une version traçable. Il gère également les indisponibilités, les reports, l’export PDF et les notifications.

La version renforcée propose aussi un **cycle autonome configurable** : génération du brouillon, campagne de confirmation, relances limitées, régénération après une nouvelle indisponibilité, publication après confirmation et diffusion des fichiers. Il est désactivé par défaut ; voir [GUIDE_AUTONOMIE_WHATSAPP.md](GUIDE_AUTONOMIE_WHATSAPP.md).

La version actuelle couvre aussi la confirmation des enseignants par e-mail ou WhatsApp, la conservation Excel, la création d’un PDF par groupe et la diffusion traçable. Consulter [GUIDE_MISE_EN_PLACE_FLUX_COMPLET.md](GUIDE_MISE_EN_PLACE_FLUX_COMPLET.md) pour la configuration pas à pas.

Voir `spec.txt` pour le périmètre POC.

## Démarrage (Docker Compose)

```powershell
copy .env.example .env
# Éditer GEMINI_API_KEY dans .env

docker compose up -d --build
docker compose run --rm app python -m alembic upgrade head
docker compose run --rm app python -m scripts.seed
```

- API / Swagger : http://localhost:8000/docs  
- Health : http://localhost:8000/health  
- État du cycle autonome : `GET /admin/autonomy` (authentification administrateur)
- Exécution immédiate : `POST /admin/autonomy/run`

Le jeu de démonstration utilise des identités marquées « Démo », des adresses `example.test` et la semaine courante. Il ne constitue pas une collecte de terrain.

Voir `GUIDE_DEMONSTRATION.md` pour dérouler le scénario complet.

### Commandes utiles

```powershell
docker compose logs -f app
docker compose down
pytest -q   # tests en local (venv)
```

### Chat (Swagger ou curl)

Header : `X-API-Token: change-me`

```json
{
  "message": "Je serai absent le 2026-08-05",
  "teacher_id": 1,
  "external_user_id": "alice",
  "channel": "api"
}
```

## Étapes faites

1. Arborescence + config + Docker + `GET /health`
2. Modèles SQLAlchemy + Alembic + seed démo
3. Outils planning + tests
4. Agent LangGraph + `POST /agent/chat`
5. Rappels confirmation présence (mock WhatsApp) + annulation/report
6. Export PDF enseignant / groupe
7. Webhook WhatsApp Cloud API

### WhatsApp (test réel)

1. Dans `.env` :
```env
WHATSAPP_MOCK=false
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_TOKEN=EAAB...
WHATSAPP_PHONE_NUMBER_ID=xxxxxxxxxx
WHATSAPP_VERIFY_TOKEN=geminia-verify
WHATSAPP_APP_SECRET=...

WHATSAPP_ADMINS=[{"nom":"Admin","prenom":"Demo","numero":"33600000000","role":"admin"}]
WHATSAPP_TEACHERS=[{"nom":"Martin","prenom":"Alice","numero":"33610000001","role":"teacher"}]
```

2. Exposez l'API (ngrok) :
```powershell
ngrok http 8000
```

3. Meta Developer → WhatsApp → Configuration → Webhook :
- Callback URL : `https://<ngrok>/webhook/whatsapp`
- Verify token : `geminia-verify`
- Abonnements : `messages`

4. Associez les numéros dans `WHATSAPP_ADMINS` / `WHATSAPP_TEACHERS`  
   (pour un prof, `prenom`+`nom` doit correspondre au seed, ex. `Alice Martin`).

5. Test envoi sortant :
```
POST /whatsapp/test-send
{ "to": "336xxxxxxxx", "message": "Hello Geminia" }
```

6. Envoyez un message WhatsApp au numéro business → l'agent répond.

Le téléphone ou WhatsApp Business Desktop sert à recevoir et répondre aux tests. Les envois automatiques passent par la Cloud API Meta. Hors fenêtre client de 24 h, utilisez un modèle Meta approuvé.

### Outil WhatsApp sans secret dans le code

```powershell
# Test à blanc recommandé au début (.env : WHATSAPP_MOCK=true)
python -m scripts.whatsapp_cli template --to 22890000000 --name hello_world --language en_US

# Texte libre uniquement dans la fenêtre client de 24 h
python -m scripts.whatsapp_cli text --to 22890000000 --message "Bonjour depuis Ascencia"

# Document
python -m scripts.whatsapp_cli document --to 22890000000 --file exports/planning.pdf --caption "Votre planning"
```

### E-mail et formulaire de disponibilités

Configurez le lien du formulaire dans **Configuration IA**. L'agent doit d'abord présenter un aperçu, puis attendre une confirmation explicite avant d'envoyer.

```env
EMAIL_MOCK=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=planning@example.com
SMTP_USE_TLS=true
AVAILABILITY_FORM_URL=https://forms.example.com/disponibilites
```

Passez `EMAIL_MOCK=false` seulement après un test de configuration. Les mots de passe SMTP restent exclusivement dans `.env`.

### Export PDF

```
GET /schedule/export/pdf/teacher/1?week_start=2026-08-03
GET /schedule/export/pdf/group/1?week_start=2026-08-03
```

Header : `X-API-Token: change-me`  
Fichiers aussi écrits dans `exports/`.

### Rappels & annulation

```powershell
# Envoie les rappels pour une date (démo)
curl -X POST http://localhost:8000/reminders/send `
  -H "Content-Type: application/json" `
  -H "X-API-Token: change-me" `
  -d "{\"on_date\":\"2026-08-03\"}"
```

Puis le prof répond via `/agent/chat` (`teacher_id: 1`) :
- `Je confirme la séance #3`
- `J'annule la séance #3`
