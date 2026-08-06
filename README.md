# Geminia — POC emplois du temps universitaires

Assistant IA (Gemini + LangGraph) pour gérer les indisponibilités enseignants, proposer des reports, valider, exporter en PDF et notifier via WhatsApp.

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

Scénario seed : **Alice Martin** (`teacher_id=1`) absente le **2026-08-05**.

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
