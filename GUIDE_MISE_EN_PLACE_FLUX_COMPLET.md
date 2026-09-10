# Mise en place du flux complet

Ce guide décrit le fonctionnement réellement implémenté : création d’un préplanning, collecte des disponibilités, régénération sous contraintes, validation administrative, création de l’Excel et diffusion des PDF.

## 1. Préparer les données

Dans le back-office, renseigner les enseignants avec une adresse électronique et un numéro WhatsApp au format international, par exemple `22890123456`. Pour chaque groupe, ouvrir **Groupes**, cliquer sur **Modifier**, puis ajouter un ou plusieurs destinataires WhatsApp. Ces destinataires reçoivent le PDF du groupe après publication.

Les cours doivent être associés à un enseignant et à un groupe. Leur semestre, leur priorité, leur volume total et leur éventuel prérequis pédagogique doivent être renseignés. Le moteur refuse par exemple de placer Python tant que le cours d’algorithmique déclaré comme prérequis n’est pas achevé. Il limite aussi la charge quotidienne d’un groupe à huit heures par défaut. Les salles, créneaux et indisponibilités doivent également être renseignés avant la génération.

## 2. Tester sans envoyer de vrais messages

Conserver les paramètres suivants dans `.env` :

```env
DEMO_MODE=true
EMAIL_MOCK=true
WHATSAPP_MOCK=true
PUBLIC_BASE_URL=http://localhost:8000
PRESENCE_RESPONSE_HOURS=48
```

Les envois sont alors simulés, mais le traitement, les statuts, l’Excel, les PDF et les journaux sont produits comme en situation réelle.

## 3. Activer les e-mails réels

```env
EMAIL_MOCK=false
SMTP_HOST=smtp.votre-fournisseur.tld
SMTP_PORT=587
SMTP_USERNAME=votre_compte
SMTP_PASSWORD=votre_mot_de_passe_application
SMTP_FROM_EMAIL=planning@votre-domaine.tld
SMTP_USE_TLS=true
PUBLIC_BASE_URL=https://votre-domaine-public.tld
```

`PUBLIC_BASE_URL` doit être accessible depuis Internet afin que l’enseignant puisse ouvrir le lien reçu. Le clic affiche d’abord une page de contrôle ; la réponse n’est enregistrée qu’après validation du bouton, ce qui évite qu’un analyseur automatique d’e-mail confirme à la place de l’enseignant.

## 4. Activer WhatsApp Business Cloud

Créer une application Meta, rattacher un compte WhatsApp Business et renseigner :

```env
WHATSAPP_MOCK=false
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_TOKEN=votre_jeton
WHATSAPP_PHONE_NUMBER_ID=votre_phone_number_id
WHATSAPP_VERIFY_TOKEN=une_valeur_secrete
WHATSAPP_APP_SECRET=votre_app_secret
WHATSAPP_PRESENCE_TEMPLATE_NAME=nom_du_modele_valide
```

Configurer le webhook Meta vers `https://votre-domaine.tld/webhooks/whatsapp` avec le même `WHATSAPP_VERIFY_TOKEN`. Le modèle de confirmation, lorsqu’il est utilisé hors de la fenêtre de conversation, doit être approuvé par Meta. Il reçoit le nom de l’enseignant, la version du planning et le code de réponse.

L’enseignant répond de façon simple :

```text
CONFIRME CODE
DISPONIBLE CODE : lundi 08h-12h; mardi 14h-18h
INDISPONIBLE CODE : motif
```

Le système vérifie le code et le numéro expéditeur. Une disponibilité partielle est interprétée par jour et plage horaire ; tous les créneaux situés en dehors de ces plages deviennent des contraintes bloquantes. Une indisponibilité totale bloque toute la semaine. La campagne passe alors en **à réviser** afin qu’une nouvelle version soit calculée.

## 5. Générer et publier

Dans **Génération & publication** :

1. choisir la semaine et générer un préplanning à partir des matières, volumes restants, enseignants, groupes, salles et créneaux ;
2. contrôler les séances proposées ;
3. créer la campagne de confirmation ;
4. envoyer ou relancer les demandes ;
5. si des créneaux partiels ou des indisponibilités sont reçus, générer une nouvelle version ;
6. faire valider cette version par les enseignants concernés ;
7. cliquer sur **Publier et diffuser**.

Le préplanning n’est pas présenté comme un résultat définitif : il sert à cadrer la semaine et à déterminer les personnes à contacter. La version finale est celle recalculée après intégration des réponses.

L’import direct des fichiers Excel pédagogiques et les appels téléphoniques automatisés constituent des extensions distinctes. Ils ne sont pas simulés comme s’ils étaient déjà opérationnels : le prototype actuel utilise les données administrées dans l’application, WhatsApp et l’e-mail.

La publication ajoute les nouvelles séances au planning, conserve une version figée, crée un classeur Excel global, génère un PDF par groupe et lance la diffusion WhatsApp. Les échecs restent visibles et le bouton **Relancer la diffusion PDF** permet de réessayer sans recréer le planning.

## 6. Limite WhatsApp à connaître

Le canal WhatsApp Cloud standard envoie les documents aux numéros individuels configurés pour chaque groupe. Il ne faut pas présenter un identifiant arbitraire de discussion de groupe comme s’il était accepté par cette API. L’envoi direct dans une véritable discussion de groupe exige un accès Meta compatible avec l’API de groupes, selon l’éligibilité du compte. Pour une démonstration fiable, utiliser la liste de destinataires ; chaque membre reçoit le même PDF du groupe.

## 7. Contrôles avant la soutenance

- utiliser des données fictives clairement signalées comme telles ;
- vérifier qu’un conflit de salle, d’enseignant ou de groupe est refusé ;
- montrer qu’une indisponibilité bloque la publication ;
- confirmer tous les enseignants, puis publier ;
- télécharger l’Excel et ouvrir les feuilles **Synthèse**, **Planning complet** et celles des groupes ;
- montrer l’historique des tentatives de diffusion ;
- conserver `WHATSAPP_MOCK=true` et `EMAIL_MOCK=true` si les comptes réels ne sont pas encore validés.

## 8. Mode autonome

Le cycle autonome est maintenant disponible sans supprimer les contrôles de sécurité. Il peut générer, contacter, relancer, régénérer, publier et diffuser dès que les confirmations requises sont réunies. La configuration complète et la procédure de test sont décrites dans `GUIDE_AUTONOMIE_WHATSAPP.md`.
