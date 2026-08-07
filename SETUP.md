# Setup Ascencia

## 1. Config (une fois)

```powershell
copy .env.example .env
# Éditer GEMINI_API_KEY (et éventuellement ADMIN_PASSWORD)
```

## 2. Démarrer — une seule commande

```powershell
docker compose up -d --build
```

Cela fait tout :
- build du front React dans l'image
- démarrage Postgres
- migrations Alembic
- seed (admin + données démo)
- API + back-office

## 3. Ouvrir

http://localhost:8000/backoffice/

Login : `admin` / `admin123`

## Option dév front (hot reload UI)

```powershell
docker compose --profile dev up frontend
```

→ http://localhost:5173/backoffice/
