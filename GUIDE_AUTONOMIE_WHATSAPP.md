# Guide — autonomie et WhatsApp réel

Ce guide active le cycle complet décrit dans le mémoire sans placer de secret dans le code.

## 1. Ce que fait le mode autonome

À chaque passage, le système avance d'une seule étape traçable :

1. il génère le brouillon de la semaine ciblée ;
2. il crée et envoie la campagne de confirmation aux enseignants ;
3. il relance uniquement les réponses encore en attente, avec une limite configurable ;
4. il archive et régénère le brouillon lorsqu'une disponibilité change ;
5. il vérifie à nouveau les contraintes avant publication ;
6. si toutes les confirmations sont obtenues, il publie puis produit l'Excel et les PDF ;
7. il diffuse les PDF par WhatsApp et journalise chaque résultat.

Le traitement est idempotent : relancer le cycle ne recrée pas une version déjà publiée.

## 2. Configuration sûre pour la démonstration

Dans `.env` :

```env
GEMINI_API_KEY=votre_cle_locale
AUTONOMOUS_MODE_ENABLED=true
AUTONOMOUS_PUBLISH_ENABLED=false
AUTONOMOUS_TARGET_WEEK_OFFSET=1
AUTONOMOUS_POLL_SECONDS=300
AUTONOMOUS_REMINDER_HOURS=24
AUTONOMOUS_MAX_REMINDERS=3
AUTONOMOUS_CHANNELS=email,whatsapp
EMAIL_MOCK=true
WHATSAPP_MOCK=true
```

Cette configuration exécute tout le cycle jusqu'à l'état « prêt à publier », sans envoyer de message réel et sans publier automatiquement.

## 3. Activation de la publication autonome

Après validation complète du scénario en mode simulé :

```env
AUTONOMOUS_PUBLISH_ENABLED=true
```

La publication automatique reste conditionnée aux confirmations de tous les enseignants concernés. Une disponibilité partielle ou une indisponibilité force une nouvelle génération et une nouvelle campagne.

## 4. Activation de WhatsApp Cloud réel

Créer une application Meta avec WhatsApp Business Cloud, puis renseigner uniquement dans `.env` :

```env
WHATSAPP_MOCK=false
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_TOKEN=votre_jeton_meta
WHATSAPP_PHONE_NUMBER_ID=votre_identifiant_numero
WHATSAPP_VERIFY_TOKEN=une_valeur_secrete
WHATSAPP_APP_SECRET=votre_secret_application
WHATSAPP_PRESENCE_TEMPLATE_NAME=nom_du_modele_approuve
PUBLIC_BASE_URL=https://votre-domaine-public.tld
```

Configurer le webhook Meta sur :

```text
https://votre-domaine-public.tld/webhook/whatsapp
```

Tester d'abord un modèle approuvé :

```text
POST /whatsapp/test-template
```

Puis tester un message dans la fenêtre autorisée :

```text
POST /whatsapp/test-send
```

Ces deux routes exigent le jeton technique de l'API.

## 5. Limitation des groupes WhatsApp

Le client Meta Cloud standard du projet envoie à des destinataires individuels. Dans la fiche de chaque groupe étudiant, renseigner `distribution_recipients` avec les numéros autorisés. Le système leur enverra le même PDF et conservera le statut de chaque livraison.

Ne pas présenter `whatsapp_group_id` comme une garantie d'envoi dans une discussion de groupe réelle. Il sert uniquement au mode de démonstration tant qu'un accès Meta compatible avec les groupes n'a pas été obtenu.

## 6. Déclenchement et supervision

Le processus tourne automatiquement si `AUTONOMOUS_MODE_ENABLED=true`. Un administrateur peut aussi :

- consulter `GET /admin/autonomy` ;
- déclencher immédiatement `POST /admin/autonomy/run` ;
- demander à l'agent : « Lance le cycle autonome pour la semaine du AAAA-MM-JJ ».

Chaque action importante est enregistrée dans le journal d'audit. Les échecs de livraison restent visibles pour une relance contrôlée.

Le verrou fourni protège une instance de l'application. Pour un déploiement avec plusieurs processus ou plusieurs serveurs, ajouter un verrou distribué PostgreSQL ou Redis avant d'activer la publication autonome.
