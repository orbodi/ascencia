# Procédure — Mise en place UAT DC1 → DC2, réplication et bascule de site

Document **séquentiel** : les étapes s’exécutent dans l’ordre. Ne passez pas à la suivante si la vérification échoue. Rien n’est supposé déjà installé ni configuré : chaque composant (paquet, rôle, fichier, SSH, sudoers, extension) est créé ici.

| Champ | Valeur |
|---|---|
| Type | Procédure d’installation et d’intervention |
| Environnement | UAT MOSIP — EPAS 12 |
| Objet | Copier la BD UAT de DC1 vers DC2, recetter le site applicatif DC2, poser la streaming replication et `repmgr` (failover **manuel**), poser `pg_failover_slots` pour le BI, valider un failover / failback **de site** (apps + BD + BI) |
| Périmètre BD | `dc1-uat` (`172.16.34.20`) / `dc2-uat` (`172.17.34.20`) |
| Périmètre apps | Site applicatif DC1 et site applicatif DC2 |
| Hors périmètre | `repmgrd`, witness, VIP / PgBouncer, EFM |

| Convention | Signification |
|---|---|
| **[DC1]** | Serveur BD `172.16.34.20` |
| **[DC2]** | Serveur BD `172.17.34.20` |
| **[INFRA]** | Équipe Infrastructure / Veeam |
| **[APPLI]** | Équipe applicative MOSIP du **site** indiqué |
| **[BI]** | Exploitants des flux CDC vers le BI |

Commandes système en `root`. Commandes PostgreSQL via `sudo -iu enterprisedb`. Port réel **5432** (le profil `enterprisedb` exporte `PGPORT=5444` : toujours `-p 5432` et `port=5432` dans les `conninfo`).

---

## Topologie cible (après la phase 4)

| node_id | node_name | IP | Rôle nominal |
|---|---|---|---|
| 1 | `dc1-uat` | `172.16.34.20` | primary — apps DC1 + BI DC1 **actifs** |
| 2 | `dc2-uat` | `172.17.34.20` | standby — apps DC2 + BI DC2 **inactifs** |

| Élément | Valeur |
|---|---|
| Compte OS | `enterprisedb` — home `/var/lib/edb` (pas `/home/enterprisedb`) |
| Binaires | `/usr/edb/as12/bin` |
| Data directory | `/data/mosip/edb/as12/data` |
| Service | `edb-as-12` |
| Config `repmgr` | `/etc/repmgr/12/repmgr.conf` |
| Paquet `repmgr` | `edb-as12-repmgr` depuis le dépôt `edb-local` |
| Slot physique | `dc2_slot` |

```text
  Site DC1 (actif)                         Site DC2 (attente)
  Applications + BI  ──►  BD primary       Applications + BI INACTIFS
                               │           BD standby
                               └──── streaming async ────►
                                    slots logiques recopiés
                                    (pg_failover_slots)
```

Règle : un seul site écrit. Jamais les applications DC1 et DC2, ni les deux BI, en parallèle.

Un restore de VM démarre en **primary indépendant**. La réplication physique ne s’active qu’à la phase 4, qui **reconstruit** la data dir DC2. Tout ce qui est écrit sur DC2 aux phases 2 et 3 est perdu.

---

## Phase 0 — Prérequis

### Étape 0.1 — Fenêtre et interlocuteurs

Réunir Infra, DBA, Applicatif DC1, Applicatif DC2, BI. Confirmer une fenêtre pour chaque phase, en particulier le gel entre les phases 3 et 4 et la bascule de la phase 5.

### Étape 0.2 — Inventaire cutover **[APPLI] [BI]**

Pour **chaque** site (DC1 et DC2), lister et faire valider :

- frontaux, API, batchs, crontab / timers systemd
- connecteurs CDC / BI : **nom de slot**, plugin, publication, outil consommateur

Sans cet inventaire, la phase 5 est inexécutable : `repmgr` ne bascule ni les applications ni le BI.

### Étape 0.3 — Contrôle de la source **[DC1]**

DC1 est l’UAT en service, instance EPAS démarrée. C’est le seul prérequis « déjà là » : une base source à copier.

```bash
systemctl is-active edb-as-12
df -h /data/mosip/edb/as12 /data/mosip/edb/as12/data/pg_wal
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT current_setting('data_directory'), current_setting('port'), pg_is_in_recovery();"
```

Attendu : `active`, `pg_is_in_recovery() = f`, port `5432`, data dir `/data/mosip/edb/as12/data`.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT slot_name, slot_type, plugin, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retenus FROM pg_replication_slots ORDER BY 5 DESC;"
```

Noter les slots logiques BI : ils devront réapparaître à l’identique sur DC2 à l’étape 4.13. Un slot `active = f` dont `retenus` croît doit être traité **avant** de créer `dc2_slot` (sous EPAS 12 la rétention n’est pas bornée).

### Étape 0.4 — Sauvegarde de sécurité **[INFRA]**

Sauvegarde Veeam de DC1, **indépendante** du job de copie vers DC2, restaurable. Noter l’identifiant du job.

**Go phase 1** : 0.1 à 0.4 OK.

---

## Phase 1 — Backup / restore des VM BD, remap IP

Objectif : copie disque des VM BD de DC1 sur l’infra DC2, adressée `172.17.34.20`, **sans** démarrer EPAS.

### Étape 1.1 — Sauvegarde **[INFRA]**

Exécuter le job Veeam des VM de base de données DC1. Consigner :

- identifiant du job et du point de restauration
- horodatage exact
- mode (crash-consistent ou application-aware)

Un restore crash-consistent est acceptable : EPAS rejouera les WAL au premier start (phase 2).

### Étape 1.2 — Restauration isolée **[INFRA]**

Restaurer les VM sur DC2 **réseau isolé** ou interfaces déconnectées.

Deux VM avec la même IP (`172.16.34.20`) sur le même réseau = collision et écritures imprévisibles. Ne pas raccorder au LAN avant l’étape 1.4.

### Étape 1.3 — Neutraliser le start automatique **[DC2] [INFRA]**

Dès que la VM est accessible (console si besoin) :

```bash
systemctl stop edb-as-12
systemctl disable edb-as-12
systemctl is-enabled edb-as-12
```

Attendu : `disabled`. Le premier start est l’étape 2.4. Un start automatique au restore crée une timeline divergente et peut écrire dans les archives de DC1.

### Étape 1.4 — Remap IP **[INFRA]**

Passer l’adresse à `172.17.34.20`, puis raccorder au réseau DC2.

```bash
hostname -I
ip -br addr
ping -c 2 172.16.34.20
timedatectl
```

Attendu : `172.17.34.20` up, ping DC1 OK, horloge synchronisée. Travailler ensuite **exclusivement en IP**.

### Étape 1.5 — Recenser les références à DC1 **[INFRA] → DBA**

```bash
grep -rnE '172\.16\.34\.20' /etc/ 2>/dev/null
ls -l /etc/repmgr/12/ 2>/dev/null
crontab -l -u root 2>/dev/null
crontab -l -u enterprisedb 2>/dev/null
```

Transmettre le résultat au DBA pour les étapes 2.2 et 2.3.

**Go phase 2** : VM adressée, `edb-as-12` arrêté et `disabled`, pas de collision IP.

---

## Phase 2 — Mise en service de la BD DC2 (instance indépendante)

Objectif : démarrer la copie et prouver que les bases MOSIP sont saines. DC2 est un **primary autonome**. Aucune réplication, aucun `repmgr`.

### Étape 2.1 — Mode de démarrage **[DC2]**

Instance **arrêtée**.

```bash
ls -l /data/mosip/edb/as12/data/standby.signal \
      /data/mosip/edb/as12/data/recovery.signal \
      /data/mosip/edb/as12/data/recovery.conf 2>/dev/null
```

Attendu : aucun de ces fichiers. Si `recovery.conf` existe, le **supprimer** (il empêche le start en PostgreSQL 12). Si `standby.signal` existe, le supprimer : la recette de la phase 3 exige un primary, pas un replica.

### Étape 2.2 — Isoler l’archivage **[DC2]**

```bash
grep -nE '^\s*archive_(mode|command)' /data/mosip/edb/as12/data/postgresql.conf
grep -nE 'archive_(mode|command)' /data/mosip/edb/as12/data/postgresql.auto.conf 2>/dev/null
```

Si `archive_command` pointe vers une destination **partagée avec DC1**, rediriger vers un chemin local DC2, ou poser `archive_mode = off`. Sinon la copie écrit des WAL d’une autre timeline dans les archives de DC1.

Créer le répertoire local si l’archivage est conservé :

```bash
mkdir -p /data/mosip/edb/as12/archive_dc2
chown enterprisedb:enterprisedb /data/mosip/edb/as12/archive_dc2
```

```conf
archive_mode = on
archive_command = 'test ! -f /data/mosip/edb/as12/archive_dc2/%f && cp %p /data/mosip/edb/as12/archive_dc2/%f'
```

### Étape 2.3 — Écarter tout fichier `repmgr` recopié par la VM **[DC2]**

La VM peut contenir un `repmgr.conf` copié depuis DC1 (`node_id=1`). Il ne doit pas servir.

```bash
ls -l /etc/repmgr/12/repmgr.conf 2>/dev/null \
  && mv /etc/repmgr/12/repmgr.conf /etc/repmgr/12/repmgr.conf.restore-vm
systemctl disable --now repmgrd 2>/dev/null || true
systemctl disable --now edb-as12-repmgrd 2>/dev/null || true
```

Ne lancer **aucune** commande `repmgr` avant l’étape 4.8.

### Étape 2.4 — Premier démarrage **[DC2]**

```bash
systemctl start edb-as-12
systemctl status edb-as-12 --no-pager | head -5
journalctl -u edb-as-12 -n 60 --no-pager
```

Attendu dans le journal : rejeu WAL (`database system was not properly shut down; automatic recovery in progress`) puis `database system is ready to accept connections`. En cas d’échec : s’arrêter, la cause est dans ce journal.

### Étape 2.5 — Identité de l’instance **[DC2]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT version();"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT current_setting('port'), current_setting('data_directory'), inet_server_addr();"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT pg_is_in_recovery() AS en_restauration, timeline_id FROM pg_control_checkpoint();"
```

Attendu : port `5432`, data dir `/data/mosip/edb/as12/data`, `inet_server_addr() = 172.17.34.20`, `pg_is_in_recovery() = f`. Noter `timeline_id`.

### Étape 2.6 — Inventaire des bases **[DC2]** puis comparaison **[DC1]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE datistemplate = false ORDER BY pg_database_size(datname) DESC;"
```

Exécuter la **même** requête sur DC1. Toutes les bases MOSIP doivent être présentes. Un écart de taille est normal ; une base absente ne l’est pas.

Avec l’applicatif : comptages sur les tables de référence convenues. Écart inexpliqué → ne pas enchaîner.

### Étape 2.7 — Slots recopiés, espace, HBA **[DC2]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT slot_name, slot_type, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retenus FROM pg_replication_slots ORDER BY 4 DESC;"
df -h /data/mosip/edb/as12/data/pg_wal
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT * FROM pg_hba_file_rules WHERE error IS NOT NULL;"
```

Ne **pas** supprimer les slots logiques BI sans l’équipe BI. Surveiller `pg_wal` pendant les phases 2 et 3. `pg_hba_file_rules` : aucune ligne d’erreur.

**Go phase 3** : instance DC2 démarrée, bases OK, archives isolées.

---

## Phase 3 — Déploiement et recette du site applicatif DC2

Objectif : prouver que la stack MOSIP du **site DC2** fonctionne contre la BD locale. Les deux sites restent étanches.

### Étape 3.1 — Accès réseau BD **[DC2] [APPLI]**

Ajouter dans `/data/mosip/edb/as12/data/pg_hba.conf` les réseaux applicatifs DC2 (la copie ne contient que les règles de DC1).

```bash
cp -a /data/mosip/edb/as12/data/pg_hba.conf /data/mosip/edb/as12/data/pg_hba.conf.bak.$(date +%Y%m%d)
```

Exemple de ligne à adapter aux sous-réseaux réels du site DC2 :

```text
host  all  all  <RESEAU_APPS_DC2>/24  scram-sha-256
```

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/pg_ctl reload -D /data/mosip/edb/as12/data
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT * FROM pg_hba_file_rules WHERE error IS NOT NULL;"
```

Aucune ligne d’erreur. Une syntaxe invalide est ignorée au reload mais bloquera le prochain start.

### Étape 3.2 — Déploiement **[APPLI site DC2]**

Installer et démarrer les composants du site DC2. Chaînes de connexion → `172.17.34.20:5432` **uniquement**.

Contrôles :

- aucune application DC2 vers `172.16.34.20`
- aucune application DC1 vers `172.17.34.20`
- **ne pas** brancher les connecteurs CDC / BI DC2 sur les slots recopiés de DC1

### Étape 3.3 — Recette **[APPLI] [client]**

Exécuter le jeu de tests UAT (authentification, parcours métier, batchs). Consigner les résultats.

Les scénarios doivent être **rejouables**. Aucune donnée de référence ne doit exister uniquement sur DC2.

### Étape 3.4 — Contrôle des sessions **[DC2]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT datname, usename, client_addr, count(*) FROM pg_stat_activity WHERE backend_type = 'client backend' AND client_addr IS NOT NULL GROUP BY 1,2,3 ORDER BY 4 DESC;"
```

Sessions applicatives sur DC2 uniquement.

**Go gel** : recette DC2 prononcée et documentée.

---

## Gel — arrêt du site DC2 avant reconstruction

La phase 4 **détruit** la data dir DC2 (`standby clone`). DC1 n’est pas détruit.

### Étape G.1 — Arrêt applicatif et BI **[APPLI DC2] [BI DC2]**

Arrêter tous les composants de l’inventaire 0.2 côté DC2 (applications, batchs, connecteurs BI). Désactiver leur démarrage automatique.

### Étape G.2 — Vérifier l’absence de session **[DC2]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT datname, usename, client_addr FROM pg_stat_activity WHERE backend_type = 'client backend' AND client_addr IS NOT NULL;"
```

Attendu : **aucune** ligne. Si une session reste, l’identifier et l’arrêter ; ne pas continuer.

### Étape G.3 — Accord écrit

Client + DBA + Applicatif + BI : autorisation de reconstruire DC2. Fenêtre phase 4 confirmée. Sauvegarde DC1 (étape 0.4) toujours restaurable.

**Go phase 4.**

---

## Phase 4 — Replica DC1 → DC2, installation `repmgr`, slots BI

Objectif : installer `repmgr` et `pg_failover_slots`, enregistrer le cluster, cloner DC2 en standby lecture seule, vérifier que les slots logiques BI sont recopiés.

### Étape 4.1 — Installer le paquet `repmgr` **[DC1] [DC2]**

```bash
dnf install -y edb-as12-repmgr --disablerepo="*" --enablerepo="edb-local"
rpm -q edb-as12-repmgr
/usr/edb/as12/bin/repmgr --version
```

Le paquet pose un `/etc/repmgr/12/repmgr.conf` **exemple** (tous les paramètres commentés). Il sera écrasé à l’étape 4.8. Ne pas lancer `cluster show` avant.

### Étape 4.2 — Désactiver le démon de bascule automatique **[DC1] [DC2]**

Deux nœuds sans témoin : la bascule automatique expose au split-brain.

```bash
systemctl disable --now repmgrd 2>/dev/null || true
systemctl disable --now edb-as12-repmgrd 2>/dev/null || true
```

La configuration portera `failover=manual`.

### Étape 4.3 — Paramètres WAL, `repmgr` et `pg_failover_slots` **[DC1]**

À faire **avant** le clone : le standby héritera de la data dir.

Dans `/data/mosip/edb/as12/data/postgresql.conf` (conserver les modules déjà listés dans `shared_preload_libraries`, séparés par des virgules) :

```conf
listen_addresses = '*'
port = 5432
shared_preload_libraries = 'repmgr,pg_failover_slots'
wal_level = logical
hot_standby = on
max_wal_senders = 16
max_replication_slots = 16
wal_keep_segments = 256
wal_log_hints = on
hot_standby_feedback = on
pg_failover_slots.synchronize_slot_names = '*'
pg_failover_slots.standby_slot_names = 'dc2_slot'
```

`shared_preload_libraries` et `wal_level` exigent un **redémarrage** :

```bash
systemctl restart edb-as-12
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT name, setting FROM pg_settings WHERE name IN ('shared_preload_libraries','wal_level','wal_log_hints','hot_standby','max_wal_senders','max_replication_slots') OR name LIKE 'pg_failover_slots%';"
```

Attendu : `repmgr` et `pg_failover_slots` dans `shared_preload_libraries`, `wal_level = logical`, `wal_log_hints = on`.

Installer l’extension :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "CREATE EXTENSION IF NOT EXISTS pg_failover_slots;"
```

`standby_slot_names` : les consommateurs CDC sur DC1 n’avancent pas au-delà du replica. Au failover, le BI DC2 reprend **sans trou ni doublon**.

Noter les slots logiques à synchroniser :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT slot_name, slot_type, plugin, active FROM pg_replication_slots ORDER BY 2, 1;"
```

### Étape 4.4 — Créer le rôle et la base `repmgr` **[DC1]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "CREATE USER repmgr WITH REPLICATION LOGIN SUPERUSER PASSWORD '<MOT_DE_PASSE>';"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "CREATE DATABASE repmgr OWNER repmgr;"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "ALTER USER repmgr SET search_path TO repmgr, \"\$user\", public;"
```

Une commande `psql -c` par ligne (le collage multi-lignes fusionne parfois les instructions).

`SUPERUSER` est requis pour installer l’extension `repmgr` et pour `pg_promote()` sous PostgreSQL 12.

### Étape 4.5 — `pg_hba.conf` **[DC1] [DC2]**

Les **deux** nœuds, les **deux** lignes. Sans la ligne `replication` sur chaque nœud, le switchover inverse échoue.

Adapter `scram-sha-256` si `SHOW password_encryption` vaut `md5`.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SHOW password_encryption;"
cp -a /data/mosip/edb/as12/data/pg_hba.conf /data/mosip/edb/as12/data/pg_hba.conf.bak.$(date +%Y%m%d)
```

```text
# DC1 — /data/mosip/edb/as12/data/pg_hba.conf
host  replication  repmgr  172.17.34.20/32  scram-sha-256
host  repmgr       repmgr  172.17.34.20/32  scram-sha-256

# DC2 — même chemin (instance encore autonome)
host  replication  repmgr  172.16.34.20/32  scram-sha-256
host  repmgr       repmgr  172.16.34.20/32  scram-sha-256
```

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/pg_ctl reload -D /data/mosip/edb/as12/data
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT * FROM pg_hba_file_rules WHERE error IS NOT NULL;"
```

Aucune ligne d’erreur. Après le clone (étape 4.10), la data dir DC2 est celle de DC1 : **réécrire** les lignes HBA de DC2 (autorisation de `172.16.34.20`) puis reload.

### Étape 4.6 — Fichier `.pgpass` **[DC1] [DC2]**

Créer `/var/lib/edb/.pgpass`. Les lignes `replication` sont **obligatoires** (sinon `fe_sendauth: no password supplied` au switchover).

```text
172.16.34.20:5432:repmgr:repmgr:<MOT_DE_PASSE>
172.17.34.20:5432:repmgr:repmgr:<MOT_DE_PASSE>
172.16.34.20:5432:replication:repmgr:<MOT_DE_PASSE>
172.17.34.20:5432:replication:repmgr:<MOT_DE_PASSE>
```

```bash
chown enterprisedb:enterprisedb /var/lib/edb/.pgpass
chmod 0600 /var/lib/edb/.pgpass
sudo -iu enterprisedb /usr/edb/as12/bin/psql -h 172.16.34.20 -p 5432 -U repmgr -d repmgr -c 'SELECT current_user;'
```

Le test doit réussir **sans invite** de mot de passe. Pour relire sans exposer le secret :

```bash
awk -F: '{print $1":"$2":"$3":"$4":***"}' /var/lib/edb/.pgpass
```

### Étape 4.7 — sudoers **[DC1] [DC2]**

`repmgr` arrête et démarre l’instance via systemd. Sans sudoers, il appelle `pg_ctl` et systemd perd le suivi du service.

```bash
cat > /etc/sudoers.d/repmgr <<'EOF'
Defaults:enterprisedb !requiretty
enterprisedb ALL=(root) NOPASSWD: /usr/bin/systemctl start edb-as-12, /usr/bin/systemctl stop edb-as-12, /usr/bin/systemctl restart edb-as-12, /usr/bin/systemctl reload edb-as-12, /usr/bin/systemctl status edb-as-12
EOF
chmod 440 /etc/sudoers.d/repmgr
visudo -cf /etc/sudoers.d/repmgr
sudo -iu enterprisedb sudo -n systemctl status edb-as-12 --no-pager | head -3
```

Le service s’affiche **sans** demande de mot de passe.

### Étape 4.8 — SSH sans mot de passe **[DC1] [DC2]**

Le switchover exécute des commandes à distance sous `enterprisedb`. À faire **dans les deux sens**.

```bash
sudo -iu enterprisedb ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519
```

Échanger les clés publiques (`id_ed25519.pub` → `authorized_keys` de l’autre nœud). Droits : `~/.ssh` en `700`, `authorized_keys` en `600`.

```bash
sudo -iu enterprisedb ssh -o BatchMode=yes -o ConnectTimeout=10 172.16.34.20 true && echo SSH_OK || echo SSH_ECHEC
sudo -iu enterprisedb ssh -o BatchMode=yes -o ConnectTimeout=10 172.17.34.20 true && echo SSH_OK || echo SSH_ECHEC
sudo -iu enterprisedb ssh -o BatchMode=yes 172.16.34.20 /usr/edb/as12/bin/pg_ctl --version
sudo -iu enterprisedb ssh -o BatchMode=yes 172.17.34.20 /usr/edb/as12/bin/pg_ctl --version
```

Les deux directions répondent `SSH_OK`. Un seul sens fonctionnel suffit à faire échouer le failback.

### Étape 4.9 — Écrire `repmgr.conf` **[DC1] [DC2]**

Chemin **absolu** `/etc/repmgr/12/repmgr.conf` (stocké dans les métadonnées, réutilisé en SSH).

```bash
mkdir -p /var/log/edb/as12
touch /var/log/edb/as12/repmgr.log
chown enterprisedb:enterprisedb /var/log/edb/as12/repmgr.log
```

**DC1** :

```conf
node_id=1
node_name='dc1-uat'
conninfo='host=172.16.34.20 user=repmgr dbname=repmgr port=5432 connect_timeout=2'
data_directory='/data/mosip/edb/as12/data'
config_directory='/data/mosip/edb/as12/data'
pg_bindir='/usr/edb/as12/bin'
repmgr_bindir='/usr/edb/as12/bin'
use_replication_slots=yes
failover=manual
log_level='INFO'
log_file='/var/log/edb/as12/repmgr.log'
ssh_options='-q -o ConnectTimeout=10'
service_start_command='sudo systemctl start edb-as-12'
service_stop_command='sudo systemctl stop edb-as-12'
service_restart_command='sudo systemctl restart edb-as-12'
service_reload_command='sudo systemctl reload edb-as-12'
```

**DC2** : le même fichier avec `node_id=2`, `node_name='dc2-uat'`, `host=172.17.34.20`.

Quatre règles :

1. `node_id`, `node_name`, `conninfo` et `data_directory` **actifs** (pas commentés), sinon `required parameter was not found`.
2. Toujours `port=5432` dans `conninfo` (sinon les appels distants tentent 5444).
3. `node_name` stable : `dc1-uat` / `dc2-uat`, jamais `primary` ni `standby`.
4. Les `service_*_command` passent par systemd.

```bash
chown enterprisedb:enterprisedb /etc/repmgr/12/repmgr.conf
chmod 640 /etc/repmgr/12/repmgr.conf
```

### Étape 4.10 — Enregistrer le primary **[DC1]**

Cette commande installe l’extension `repmgr` et crée `repmgr.nodes`. Elle précède tout clone.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf primary register --dry-run
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf primary register
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

Attendu : un nœud `dc1-uat`, rôle `primary`, statut `* running`.

### Étape 4.11 — Cloner le standby **[DC2]** — destructif

Les applications et le BI DC2 sont arrêtés (gel). Cette étape **efface** la data dir de la recette phase 3.

```bash
systemctl stop edb-as-12
df -h /data/mosip/edb/as12
mv /data/mosip/edb/as12/data /data/mosip/edb/as12/data.bak.$(date +%Y%m%d%H%M)
mkdir -p /data/mosip/edb/as12/data
chown enterprisedb:enterprisedb /data/mosip/edb/as12/data
chmod 700 /data/mosip/edb/as12/data
```

Conserver `data.bak.*` jusqu’à la fin de la phase 5 (rollback).

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -h 172.16.34.20 -U repmgr -d repmgr -p 5432 \
  -f /etc/repmgr/12/repmgr.conf standby clone --dry-run

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -h 172.16.34.20 -U repmgr -d repmgr -p 5432 \
  -f /etc/repmgr/12/repmgr.conf standby clone
```

Le clone écrit `standby.signal` et `primary_conninfo`. Ne pas les supprimer.

```bash
ls -l /data/mosip/edb/as12/data/standby.signal
grep -nE 'primary_conninfo|primary_slot_name' /data/mosip/edb/as12/data/postgresql.auto.conf
ls /data/mosip/edb/as12/data/recovery.conf 2>/dev/null && echo "A SUPPRIMER"
```

Compléter si besoin :

```conf
primary_conninfo = 'host=172.16.34.20 port=5432 user=repmgr application_name=dc2-uat'
primary_slot_name = 'dc2_slot'
```

Sous EPAS 12, `primary_conninfo` n’est lu **qu’au démarrage**.

Réécrire les lignes `pg_hba` de DC2 (étape 4.5) : le clone a ramené le HBA de DC1.

Réécrire `/etc/repmgr/12/repmgr.conf` de DC2 (étape 4.9) si le clone ou le paquet l’a écrasé.

```bash
systemctl start edb-as-12
journalctl -u edb-as-12 -n 40 --no-pager
```

Attendu : `entering standby mode`, puis streaming depuis le primary.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby register
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

### Étape 4.12 — Forcer le port dans les métadonnées **[DC1]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d repmgr -c \
  "SELECT node_id, node_name, conninfo FROM repmgr.nodes;"
```

Si `port=5432` est absent des `conninfo` :

```sql
UPDATE repmgr.nodes
SET conninfo = 'host=172.16.34.20 user=repmgr dbname=repmgr port=5432 connect_timeout=2'
WHERE node_id = 1;
UPDATE repmgr.nodes
SET conninfo = 'host=172.17.34.20 user=repmgr dbname=repmgr port=5432 connect_timeout=2'
WHERE node_id = 2;
```

### Étape 4.13 — Validation du cluster **[DC1] [DC2]**

Lancer **depuis les deux nœuds**. Il n’existe pas de commande `cluster check` en `repmgr` 5.3.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf node check
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster crosscheck
```

Attendu `cluster show` : `dc1-uat` primary `* running`, `dc2-uat` standby `running`, **même timeline**.  
Attendu `node check` sur DC2 : lag **0 s**.

```bash
# DC2
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT pg_is_in_recovery();"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "CREATE TABLE ecriture_interdite(id int);"
```

`pg_is_in_recovery() = t`. Le `CREATE` est **refusé** (`cannot execute ... in a read-only transaction`).

```bash
# DC1
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT application_name, client_addr, state, sync_state, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)) AS retard FROM pg_stat_replication;"
```

Une ligne `dc2-uat` depuis `172.17.34.20`, `state = streaming`, `sync_state = async`, retard faible.

### Étape 4.14 — Test de propagation **[DC1] puis [DC2]**

Dans la base `postgres` uniquement, **jamais** dans les bases MOSIP.

```bash
# DC1
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "CREATE TABLE test_replication(id int, ts timestamptz DEFAULT now()); INSERT INTO test_replication(id) VALUES (1);"
```

```bash
# DC2, quelques secondes plus tard
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT * FROM test_replication;"
```

La ligne doit apparaître. Nettoyage **depuis DC1** :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "DROP TABLE test_replication;"
```

### Étape 4.15 — Slots BI **[DC1] [DC2]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT slot_name, plugin, active, restart_lsn, confirmed_flush_lsn FROM pg_replication_slots WHERE slot_type = 'logical' ORDER BY 1;"
```

Les **mêmes** `slot_name` des deux côtés. Sur DC2 : en général `active = f`.  
Liste vide sur DC2 alors que DC1 a des slots logiques → **ne pas** passer en phase 5.

Connecteurs BI : uniquement sur DC1. Interdit : `pg_create_logical_replication_slot` sur DC2.

Applications DC2 : **restent arrêtées**.

**Go phase 5** : replica OK, `repmgr` OK, slots BI identiques, site DC2 arrêté.

---

## Phase 5 — Failover et failback de site

Objectif : basculer **tout le site** (BD + applications MOSIP + BI), puis revenir. `repmgr` ne bascule que la BD.

Ne **jamais** arrêter le primary à la main avant un `standby switchover`.

### Étape 5.1 — Contrôles d’entrée **[DC1] [DC2]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf node check
```

Lag ≈ 0. Inventaire 0.2 sous la main. Équipes applications DC1, applications DC2 et BI présentes.

### Étape 5.2 — Arrêter le site DC1 **[BI] puis [APPLI DC1]**

1. Arrêter **tous** les connecteurs BI DC1. Plus aucune consommation de slot.
2. Arrêter **toutes** les applications MOSIP DC1 (front, API, batchs, timers).

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT datname, usename, client_addr FROM pg_stat_activity WHERE backend_type = 'client backend' AND client_addr IS NOT NULL;"
```

Attendu : vide (hors session DBA). Noter l’heure de début d’indisponibilité.

### Étape 5.3 — Simulation du switchover **[DC2]**

À lancer **sur le standby à promouvoir** :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby switchover --dry-run
```

Dernière ligne attendue : `prerequisites for executing STANDBY SWITCHOVER are met`.  
Échec → corriger (SSH, `.pgpass`, `pg_hba`, `port=5432`) ; ne pas enchaîner.

### Étape 5.4 — Switchover réel **[DC2]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby switchover
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT pg_is_in_recovery(), timeline_id FROM pg_control_checkpoint();"
```

Attendu : `dc2-uat` primary `* running`, `dc1-uat` standby, `pg_is_in_recovery() = f` sur DC2, timeline incrémentée.

Déroulement : contrôles SSH / lag / replication → `sudo systemctl stop edb-as-12` sur l’ancien primary → `pg_promote` → réintégration de l’ancien primary en standby. Durée typique : 10 à 30 secondes.

### Étape 5.5 — Vérifier les slots BI **avant** de démarrer le BI DC2 **[DC2]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT slot_name, plugin, active, restart_lsn, confirmed_flush_lsn FROM pg_replication_slots WHERE slot_type = 'logical' ORDER BY 1;"
```

Attendu : **mêmes** slots qu’avant la bascule, `confirmed_flush_lsn` renseigné, `active = f`.  
Liste vide → **stop**. Ne pas démarrer le BI DC2. Ne pas exécuter `pg_create_logical_replication_slot`.

### Étape 5.6 — Allumer le site DC2 **[APPLI DC2] puis [BI DC2]**

1. Démarrer les applications MOSIP DC2, connexion `172.17.34.20:5432`.
2. Démarrer le BI DC2 sur les **mêmes noms de slots** (même plugin / publication). C’est une **reprise** à `confirmed_flush_lsn`, pas un nouveau flux. Les deux BI ne tournent jamais ensemble.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT slot_name, active, confirmed_flush_lsn FROM pg_replication_slots WHERE slot_type = 'logical' ORDER BY 1;"
```

Attendu : `active = t`, `confirmed_flush_lsn` qui **avance**. S’il reste figé : mauvais slot ou slot neuf (le BI ferait un snapshot : l’arrêter).

### Étape 5.7 — Recette site DC2 **[APPLI] [BI] [client]**

Jeu de tests métier + continuité BI (pas de re-snapshot). Consigner l’heure de fin et la durée d’indisponibilité.

### Étape 5.8 — Failback (retour site DC1)

Même enchaînement **inverse**.

1. **[BI DC2]** Arrêter le BI DC2.
2. **[APPLI DC2]** Arrêter les applications DC2.
3. Contrôler l’absence de session sur DC2.
4. **Sur le standby actuel (DC1)** :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby switchover --dry-run
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby switchover
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

5. Vérifier les slots logiques sur DC1 promu (même requête qu’étape 5.5).
6. Démarrer les applications DC1 → `172.16.34.20:5432`.
7. Démarrer le BI DC1, **mêmes slots**.
8. Recette site DC1. Consigner la durée du retour.

Attendu `cluster show` : `dc1-uat` primary, `dc2-uat` standby, même timeline, lag 0.

### Étape 5.9 — Test incident (si demandé par le client)

Fenêtre dédiée, **après** un failback réussi.

1. Isoler DC1 : `systemctl stop edb-as-12` et, si besoin, coupure réseau / stockage. **Avant** toute promotion.
2. Sur DC2 :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby promote --dry-run
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby promote
```

3. Cutover applications / BI DC2 comme 5.5 à 5.7 (perte possible : réplication asynchrone).
4. Réintégrer DC1, instance **arrêtée** :

```bash
systemctl stop edb-as-12
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf node rejoin \
  -d 'host=172.17.34.20 user=repmgr dbname=repmgr port=5432 connect_timeout=2' \
  --dry-run --verbose

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf node rejoin \
  -d 'host=172.17.34.20 user=repmgr dbname=repmgr port=5432 connect_timeout=2' \
  --verbose
```

Échec du rejoin → vider la data dir et refaire un `standby clone` depuis le nouveau primary, puis `standby register --force`.  
Deux `primary` dans `cluster show` → arrêter **immédiatement** l’ancien. Ne pas fusionner les écritures.

5. Failback vers DC1 comme l’étape 5.8.

**Go phase 6** : topologie nominale rétablie, procès-verbal de test signé.

---

## Phase 6 — Site DC2 en attente

Objectif : DC2 prêt, sans écriture parasite.

### Étape 6.1 — Applications et BI DC2 **[APPLI] [BI]**

Arrêter les composants DC2. **Désactiver** le démarrage automatique (un reboot de VM est le premier vecteur d’écriture sur le standby).

### Étape 6.2 — La BD DC2 reste démarrée **[DC2]**

Ne **pas** arrêter `edb-as-12` sur DC2. L’arrêt lâche le slot `dc2_slot` : sous EPAS 12 les WAL s’accumulent sur DC1 sans borne.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT pg_is_in_recovery();"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c \
  "SELECT datname, usename, client_addr FROM pg_stat_activity WHERE backend_type = 'client backend' AND client_addr IS NOT NULL;"
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

Attendu : recovery `t`, aucune session applicative, `dc2-uat` standby `running`.

### Étape 6.3 — Site actif = DC1 **[APPLI] [BI]**

Applications MOSIP et BI uniquement sur DC1 → `172.16.34.20:5432`.

### Étape 6.4 — Nettoyage et supervision **[DC2] [DC1]**

Après validation de la phase 5, supprimer `/data/mosip/edb/as12/data.bak.*` si l’espace manque.

Supervision à laisser en place sur DC1 :

```sql
SELECT application_name, state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS retard_octets
FROM pg_stat_replication;

SELECT slot_name, slot_type, active,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retenus
FROM pg_replication_slots
ORDER BY 4 DESC;
```

Alerter si aucun standby n’est connecté, ou si un slot `active = f` voit `retenus` croître.

---

## Rollback par phase

| Si échec à | Faire |
|---|---|
| Phase 1 ou 2 | Supprimer ou re-restaurer les VM DC2. DC1 intact |
| Phase 3 | Corriger le déploiement applications ; la BD DC2 reste autonome |
| Phase 4, avant start du standby | Remettre `data.bak.*` à la place de `data` |
| Phase 4, clone échoué | Reprendre l’étape 4.11 |
| Phase 5, après switchover | Étape 5.8 (switchover inverse + cutover inverse) |
| Phase 5, après promote | `node rejoin` ou nouveau clone |
| Phase 6 | Redémarrer applications / BI sur le site du primary |

---

## Erreurs fréquentes

| Symptôme | Cause | Que faire |
|---|---|---|
| `required parameter was not found` | Fichier d’exemple du paquet | Réécrire `repmgr.conf` (étape 4.9) |
| `Connection refused` port **5444** | `PGPORT=5444` et `conninfo` sans port | `port=5432` dans le fichier **et** dans `repmgr.nodes` |
| `aucune entrée pg_hba` pour la réplication | Ligne `replication` absente sur le nœud cible | Étape 4.5 sur **les deux** nœuds, reload |
| `fe_sendauth: no password supplied` | `.pgpass` sans database `replication` | Étape 4.6 |
| `unable to connect via SSH` | Clé `enterprisedb` absente ou un seul sens | Étape 4.8 |
| `unknown ... cluster check` | Commande inexistante en 5.3 | Utiliser `node check` |
| `directory exists and is not empty` | Data dir DC2 non vide au clone | Déplacer le répertoire (étape 4.11) |
| Slots logiques absents après promote | `pg_failover_slots` non chargé avant le clone | Ne pas démarrer le BI DC2 ; reprendre 4.3 puis 4.11 |
| BI DC2 en snapshot | Nouveau slot créé sur DC2 | Reprendre les slots existants |
| Deux `primary` dans `cluster show` | Promote sans isolement | Arrêter **immédiatement** l’ancien primary |

---

## Journal d’exécution

| Étape | Date / heure | Opérateur | OK / KO | Observation |
|---|---|---|---|---|
| 0 Prérequis | | | | |
| 1 Restore VM + remap | | | | Point Veeam : |
| 2 Mise en service BD DC2 | | | | Timeline : |
| 3 Recette site DC2 | | | | |
| Gel | | | | |
| 4 Replica + repmgr + slots BI | | | | Lag : |
| 5.4 Switchover → DC2 | | | | Durée : |
| 5.7 Recette site DC2 | | | | BI reprise OK / KO |
| 5.8 Failback → DC1 | | | | Durée : |
| 6 Site DC2 inactif | | | | |
