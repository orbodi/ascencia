# Runbook repmgr — EPAS 12 (2 nœuds, failover manuel)

Cluster EDB Postgres Advanced Server 12 : **1 primary + 1 standby**, **sans witness**, **sans `repmgrd`**.

Le failover est **uniquement manuel** :

- maintenance : `repmgr standby switchover`
- incident : isolation de l’ancien primary, puis `repmgr standby promote` + `repmgr node rejoin`

Ne pas activer `repmgrd` sur cette topologie : deux nœuds sans witness exposent à un split-brain.

Documents liés :

- [`mise-en-place-streaming-replication-epas12.md`](mise-en-place-streaming-replication-epas12.md) — couche de réplication native, préalable à repmgr
- [`mise-en-place-cluster-repmgr-epas12.md`](mise-en-place-cluster-repmgr-epas12.md) — procédure d'installation pas à pas, à suivre dans l'ordre
- [`cr-repmgr-epas12-uat.md`](cr-repmgr-epas12-uat.md) — compte-rendu de l'intervention sur l'UAT
- [`procedure-bascule-uat-dc1-dc2.md`](procedure-bascule-uat-dc1-dc2.md) — procédure de restauration UAT DC1 → DC2, réplication et tests de bascule

---

## Cluster (constaté sur UAT)

| Rôle | Hostname OS | node_name repmgr | IP | node_id |
|---|---|---|---|---|
| Primary | `mosipdbuat01` | `dc1-uat` | `172.16.34.20` | 1 |
| Standby | (DC2, `application_name=dc2-uat`) | `dc2-uat` | `172.17.34.20` | 2 |

Réplication **déjà active** (`replicator` → `172.17.34.20`, async). Extension `repmgr 5.3` et table `repmgr.nodes` déjà peuplées. **Ne pas** faire `standby clone`.

Le `dnf install` a restauré l’échantillon `/etc/repmgr/12/repmgr.conf` : c’est ce fichier qu’il faut réécrire (chemin stocké dans `repmgr.nodes.config_file`).

À renseigner encore :

| Placeholder | Exemple | Description |
|---|---|---|
| `CLUSTER_CIDR` | `10.10.20.0/24` | Réseau interne autorisé dans `pg_hba.conf` |
| `REPMGR_PASSWORD` | *(secret)* | Mot de passe du rôle `repmgr` |

Utiliser les **mêmes noms d’hôte** dans `conninfo`, SSH et `/etc/hosts` (ou le DNS). Un mismatch casse `pg_hba` et le switchover.

---

## Chemins et identifiants EPAS 12

| Élément | RHEL / Rocky / Alma | Debian / Ubuntu |
|---|---|---|
| Utilisateur OS / DB | `enterprisedb` | `enterprisedb` |
| Port | `5432` (pas 5444) | `5432` |
| Binaires | `/usr/edb/as12/bin` | `/usr/lib/edb-as/12/bin` |
| Data directory | `/data/mosip/edb/as12/data` | `/var/lib/edb-as/12/main` |
| Home `enterprisedb` | `/var/lib/edb` | `/var/lib/edb` |
| Service systemd | `edb-as-12` | `edb-as@12-main` (vérifier `systemctl list-units 'edb-as*'`) |
| Paquet repmgr | `edb-as12-repmgr` | `edb-as12-repmgr` |
| Config repmgr | `/etc/repmgr/12/repmgr.conf` | `/etc/repmgr/12/repmgr.conf` |

Les commandes ci-dessous sont en **chemins RHEL**. Sur Debian, substituer `pg_bindir`, `data_directory` et le nom du service.

Variables utiles (session `enterprisedb` sur RHEL) :

```bash
export PATH=/usr/edb/as12/bin:$PATH
export PGDATA=/data/mosip/edb/as12/data
export PGPORT=5432
export PGUSER=enterprisedb
```

Le profil `enterprisedb` exporte par défaut `PGPORT=5444`. C'est la cause des erreurs `Connection refused` quand un `conninfo` ne précise pas le port.

---

## Architecture

```text
Applications  -->  dc1-uat  172.16.34.20:5432
                      |
                      |  streaming replication async (rôle repmgr)
                      v
                   dc2-uat  172.17.34.20:5432

DBA  -- SSH enterprisedb <-> enterprisedb --  les deux nœuds
DBA  -- CLI /usr/edb/as12/bin/repmgr
```

`repmgrd` n’est **pas** démarré. Aucun `promote_command` automatique.

---

## 1. Prérequis

Sur les deux nœuds :

- EPAS 12 installé. Sur le **primary**, l’instance est initialisée et `edb-as-12` est actif.
- Dépôt local EDB disponible : `edb-local` (`dnf repolist | grep edb-local`). Les autres dépôts sont volontairement ignorés à l’install.
- Firewall : TCP **5444** dans les deux sens + SSH **22** entre `mosipdbuat01` et `mosipdbuat02`.
- Horloge NTP/chrony correcte.
- Hostname et résolution (DNS ou `/etc/hosts`) cohérents.
- Le standby n’héberge **pas** de data dir à conserver : `standby clone` l’écrase.
- Sauvegarde récente du primary (pg_basebackup / Barman / snapshot) **avant** toute opération destructive.

Vérifications rapides :

```bash
systemctl is-active edb-as-12
ss -lntp | grep 5444
getent hosts mosipdbuat01
getent hosts mosipdbuat02
timedatectl
```

---

## 2. Installation du paquet

Sur **les deux** nœuds, en root. Commande de référence (reprise d’install comprise : idempotente si le paquet est déjà partiellement présent) :

```bash
dnf install -y edb-as12-repmgr --disablerepo="*" --enablerepo="edb-local"
```

`--disablerepo="*"` évite de tirer une autre version depuis BaseOS, EPEL ou le repo EDB public. Seul `edb-local` est utilisé.

Si un essai précédent a échoué (mauvais repo, timeout, transaction incomplète) :

```bash
dnf clean all
dnf repolist --enabled | grep edb-local
dnf install -y edb-as12-repmgr --disablerepo="*" --enablerepo="edb-local"
```

Vérifier :

```bash
rpm -q edb-as12-repmgr
/usr/edb/as12/bin/repmgr --version
ls -l /usr/edb/as12/share/extension/repmgr.control
```

Ne pas activer ni démarrer le service `repmgrd` s’il a été installé par le paquet :

```bash
systemctl stop repmgrd 2>/dev/null || true
systemctl disable repmgrd 2>/dev/null || true
systemctl stop edb-as12-repmgrd 2>/dev/null || true
systemctl disable edb-as12-repmgrd 2>/dev/null || true
```

---

## 3. Paramètres EPAS (primary)

Les paramètres WAL et `shared_preload_libraries` doivent être en place **avant** `primary register`. Le clone recopie la data dir : le standby les héritera.

### 3.1 `postgresql.conf`

Éditer `/var/lib/edb/as12/data/postgresql.conf` (ou un fichier `conf.d` inclus), **sans écraser** un `archive_command` déjà en production.

```conf
listen_addresses = '*'          # ou les IPs internes du cluster
port = 5444

shared_preload_libraries = 'repmgr'   # conserver les autres libs déjà présentes, séparées par des virgules

wal_level = replica
hot_standby = on
max_wal_senders = 10
max_replication_slots = 10
wal_keep_segments = 256         # PG12 / EPAS 12 (pas wal_keep_size, introduit en PG13)
wal_log_hints = on              # requis pour pg_rewind / node rejoin
hot_standby_feedback = on
```

Si `shared_preload_libraries` contient déjà des modules (`passwordcheck`, `edb_wait_states`, …) :

```conf
shared_preload_libraries = 'repmgr,passwordcheck'
```

`shared_preload_libraries` et `wal_level` exigent un **redémarrage**.

```bash
systemctl restart edb-as-12
sudo -iu enterprisedb psql -p 5444 -d edb -c "SHOW shared_preload_libraries;"
sudo -iu enterprisedb psql -p 5444 -d edb -c "SHOW wal_level;"
```

Attendu : `repmgr` dans la liste, `wal_level = replica` (ou `logical`).

### 3.2 Méthode d’auth

```bash
sudo -iu enterprisedb psql -p 5444 -d edb -c "SHOW password_encryption;"
```

- `scram-sha-256` → utiliser `scram-sha-256` dans `pg_hba.conf`
- `md5` → utiliser `md5` dans `pg_hba.conf`

Les exemples ci-dessous utilisent `scram-sha-256`. Adapter si besoin.

### 3.3 `pg_hba.conf`

Ajouter **uniquement** le réseau interne du cluster. Ne pas utiliser `trust` en production.

Fichier : `/var/lib/edb/as12/data/pg_hba.conf`

```text
# repmgr + streaming replication
host  replication  repmgr  CLUSTER_CIDR  scram-sha-256
host  repmgr       repmgr  CLUSTER_CIDR  scram-sha-256
```

Recharger (pas de restart) :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/pg_ctl reload -D /var/lib/edb/as12/data
# ou : systemctl reload edb-as-12
```

---

## 4. Rôle et base `repmgr` (primary uniquement)

```bash
sudo -iu enterprisedb psql -p 5444 -d edb <<'SQL'
CREATE USER repmgr WITH REPLICATION LOGIN SUPERUSER PASSWORD 'REPMGR_PASSWORD';
CREATE DATABASE repmgr OWNER repmgr;
ALTER USER repmgr SET search_path TO repmgr, "$user", public;
GRANT ALL ON DATABASE repmgr TO repmgr;
SQL
```

`SUPERUSER` est requis pour installer l’extension `repmgr` et, en PostgreSQL 12+, pour `pg_promote()` lors d’un promote.

### 4.1 `.pgpass`

Sur **les deux** nœuds, fichier `/var/lib/edb/.pgpass`. Les lignes `replication` sont **obligatoires** pour le switchover (`fe_sendauth: no password supplied` sinon) :

```text
172.16.34.20:5432:repmgr:repmgr:REPMGR_PASSWORD
172.17.34.20:5432:repmgr:repmgr:REPMGR_PASSWORD
172.16.34.20:5432:replication:repmgr:REPMGR_PASSWORD
172.17.34.20:5432:replication:repmgr:REPMGR_PASSWORD
```

Inclure aussi `localhost` et l’IP brute si `conninfo` ne passe pas par le FQDN :

```text
localhost:5444:repmgr:repmgr:REPMGR_PASSWORD
127.0.0.1:5444:repmgr:repmgr:REPMGR_PASSWORD
```

Droits :

```bash
chown enterprisedb:enterprisedb /home/enterprisedb/.pgpass
chmod 0600 /home/enterprisedb/.pgpass
```

Test depuis chaque nœud :

```bash
sudo -iu enterprisedb psql -h mosipdbuat01 -p 5444 -U repmgr -d repmgr -c 'SELECT current_user, inet_server_addr();'
sudo -iu enterprisedb psql -h mosipdbuat02 -p 5444 -U repmgr -d repmgr -c 'SELECT 1;'
```

Le second test échoue tant que le standby n’est pas cloné : c’est normal à cette étape. Le test vers le primary doit réussir **sans mot de passe interactif**.

---

## 5. `repmgr.conf`

Le fichier livré par le paquet (`/etc/repmgr/12/repmgr.conf`) est un **échantillon** : `node_id`, `node_name`, `conninfo` et `data_directory` sont commentés. Tant qu’ils ne sont pas renseignés, `repmgr` refuse de démarrer.

Chemin **absolu** obligatoire (stocké dans les métadonnées, utilisé en SSH au switchover).  
`node_name` = **hostname**, jamais `primary` / `standby` (les rôles changent).

```bash
mkdir -p /var/log/edb/as12
touch /var/log/edb/as12/repmgr.log
chown enterprisedb:enterprisedb /var/log/edb/as12/repmgr.log
```

Sauvegarder l’échantillon puis remplacer le fichier :

```bash
cp -a /etc/repmgr/12/repmgr.conf /etc/repmgr/12/repmgr.conf.sample
```

### 5.1 `dc1-uat` (`mosipdbuat01`, `172.16.34.20`) — `node_id=1`

`node_name` et `conninfo` **doivent** matcher `repmgr.nodes` (déjà enregistré). Pas de `port=` : l’instance écoute sur 5432 (défaut).

```conf
node_id=1
node_name='dc1-uat'
conninfo='host=172.16.34.20 user=repmgr dbname=repmgr port=5432 connect_timeout=2'
data_directory='/data/mosip/edb/as12/data'
config_directory='/data/mosip/edb/as12/data'
pg_bindir='/usr/edb/as12/bin'
repmgr_bindir='/usr/edb/as12/bin'

failover=manual
log_level='INFO'
log_file='/var/log/edb/as12/repmgr.log'
ssh_options='-q -o ConnectTimeout=10'

service_start_command='sudo systemctl start edb-as-12'
service_stop_command='sudo systemctl stop edb-as-12'
service_restart_command='sudo systemctl restart edb-as-12'
service_reload_command='sudo systemctl reload edb-as-12'
```

### 5.2 `dc2-uat` (`172.17.34.20`) — `node_id=2`

À coller **sur le standby** (même `data_directory` s’il est identique) :

```conf
node_id=2
node_name='dc2-uat'
conninfo='host=172.17.34.20 user=repmgr dbname=repmgr port=5432 connect_timeout=2'
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

Droits :

```bash
chown enterprisedb:enterprisedb /etc/repmgr/12/repmgr.conf
chmod 640 /etc/repmgr/12/repmgr.conf
```

### 5.3 sudoers (switchover via systemd)

Les `service_*_command` passent par `sudo systemctl`. Sans ça, le switchover appelle `pg_ctl` et systemd perd le suivi du service.

`/etc/sudoers.d/repmgr` sur **les deux** nœuds :

```text
Defaults:enterprisedb !requiretty
enterprisedb ALL=(root) NOPASSWD: /usr/bin/systemctl start edb-as-12, /usr/bin/systemctl stop edb-as-12, /usr/bin/systemctl restart edb-as-12, /usr/bin/systemctl reload edb-as-12, /usr/bin/systemctl status edb-as-12
```

```bash
chmod 440 /etc/sudoers.d/repmgr
visudo -cf /etc/sudoers.d/repmgr
```

Points critiques :

Si `cluster show` fonctionne mais le switchover `--dry-run` tente le port **5444** : le `conninfo` dans `repmgr.nodes` n’a pas de port, et le profil `enterprisedb` exporte `PGPORT=5444`. Mettre à jour les deux nœuds :

```sql
UPDATE repmgr.nodes
SET conninfo = 'host=172.16.34.20 user=repmgr dbname=repmgr port=5432 connect_timeout=2'
WHERE node_id = 1;
UPDATE repmgr.nodes
SET conninfo = 'host=172.17.34.20 user=repmgr dbname=repmgr port=5432 connect_timeout=2'
WHERE node_id = 2;
```
- `node_name` = `dc1-uat` / `dc2-uat` (déjà en base), pas le hostname OS.
- `failover=manual` : pas de `promote_command` / `follow_command`.
- Ne pas laisser les lignes `#node_id=` commentées : les 4 paramètres requis doivent être **actifs**.

---

## 6. SSH passwordless (`enterprisedb`)

Le switchover exécute `pg_ctl` à distance sur l’autre nœud. Sans SSH, il échoue.

Sur chaque nœud, en tant que `enterprisedb` :

```bash
sudo -iu enterprisedb
ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519
```

Échanger les clés (`ssh-copy-id` ou copie manuelle de `id_ed25519.pub` dans `authorized_keys` de l’autre nœud).

`~enterprisedb/.ssh/config` recommandé :

```text
Host mosipdbuat01 mosipdbuat02
  User enterprisedb
  IdentityFile ~/.ssh/id_ed25519
  StrictHostKeyChecking accept-new
```

Tests **dans les deux sens** :

```bash
sudo -iu enterprisedb ssh mosipdbuat01 true
sudo -iu enterprisedb ssh mosipdbuat02 true
sudo -iu enterprisedb ssh mosipdbuat01 /usr/edb/as12/bin/pg_ctl --version
sudo -iu enterprisedb ssh mosipdbuat02 /usr/edb/as12/bin/pg_ctl --version
```

Aucun prompt mot de passe. `~/.ssh` en `700`, `authorized_keys` en `600`.

---

## 7. Enregistrement du cluster

### 7.1 Enregistrer le primary

Sur `mosipdbuat01` :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf primary register --dry-run
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf primary register
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

Attendu : un nœud `primary`, rôle `primary`, statut `* running`.

### 7.2 Cloner le standby

Sur `mosipdbuat02` :

1. Arrêter EPAS s’il tourne.
2. S’assurer que `PGDATA` est vide **ou** que son contenu peut être détruit.
3. Cloner depuis le primary.

```bash
systemctl stop edb-as-12

# Si un ancien data dir existe et n'est pas à conserver :
# mv /var/lib/edb/as12/data /var/lib/edb/as12/data.bak.$(date +%Y%m%d%H%M)

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -h mosipdbuat01 -U repmgr -d repmgr -p 5444 \
  -f /etc/repmgr/12/repmgr.conf \
  standby clone --dry-run

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -h mosipdbuat01 -U repmgr -d repmgr -p 5444 \
  -f /etc/repmgr/12/repmgr.conf \
  standby clone
```

Si le data dir n’est pas vide et que c’est volontaire, `--force` écrase. Ne l’utiliser qu’après confirmation.

Démarrer puis enregistrer :

```bash
systemctl start edb-as-12
systemctl status edb-as-12 --no-pager

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby register
```

Le clone pose généralement `standby.signal` (PostgreSQL 12+) et un `primary_conninfo` dans `postgresql.auto.conf`. Ne pas les supprimer.

---

## 8. Vérifications

Exécuter depuis n’importe quel nœud (préférer le primary) :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster check
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf node check
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf node status
```

`cluster show` attendu :

```text
 ID | Name    | Role    | Status    | Upstream | Location | Connection string
----+---------+---------+-----------+----------+----------+-------------------
 1  | mosipdbuat01 | primary | * running |              | default  | host=mosipdbuat01 ...
 2  | mosipdbuat02 | standby |   running | mosipdbuat01 | default  | host=mosipdbuat02 ...
```

Côté SQL, **sur le primary** :

```sql
SELECT pid, application_name, client_addr, state, sync_state,
       replay_lsn, pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS lag_bytes
FROM pg_stat_replication;

SELECT slot_name, slot_type, active, restart_lsn
FROM pg_replication_slots;
```

**Sur le standby** :

```sql
SELECT pg_is_in_recovery();          -- doit être true
SELECT now() - pg_last_xact_replay_timestamp() AS replay_lag;
SELECT status, conninfo FROM pg_stat_wal_receiver;
```

Lecture seule applicative : `psql -h mosipdbuat02 -p 5444` doit répondre ; un `INSERT` doit échouer (`cannot execute ... in a read-only transaction`).

---

## 9. Exploitation manuelle

### 9.1 Switchover planifié (maintenance)

À lancer **sur le standby à promouvoir**, primary et standby **tous deux joignables**.

Checklist avant :

- [ ] Lag WAL acceptable (`cluster check` OK)
- [ ] SSH `enterprisedb` dans les deux sens
- [ ] Applications en freeze / fenêtre de maintenance
- [ ] Sauvegarde récente

```bash
# Sur mosipdbuat02
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -f /etc/repmgr/12/repmgr.conf \
  standby switchover --dry-run

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -f /etc/repmgr/12/repmgr.conf \
  standby switchover
```

Après succès :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

L’ancien standby est `primary` (`* running`). L’ancien primary est `standby`.

Pointer les applications vers le **nouveau** primary (`mosipdbuat02:5444` jusqu’au prochain switchover inverse).

Pour revenir à la topologie initiale, relancer un switchover depuis l’autre nœud (l’ancien primary, devenu standby).

### 9.2 Incident — primary inaccessible

**Ordre impératif** pour éviter un split-brain :

1. **Isoler** l’ancien primary s’il peut encore écrire (stop service, fence IP, coupure storage). Tant qu’il accepte des écritures, ne pas promouvoir.
2. Promouvoir le standby.
3. Basculer les applications.
4. Réintégrer l’ancien primary **uniquement** après qu’il soit arrêté et fencé.

Sur `mosipdbuat02` :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -f /etc/repmgr/12/repmgr.conf \
  standby promote --dry-run

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -f /etc/repmgr/12/repmgr.conf \
  standby promote
```

Vérifier `pg_is_in_recovery() = false` et `cluster show`.

### 9.3 Réintégration de l’ancien primary (`node rejoin`)

Sur l’**ancien** primary, instance **arrêtée** :

```bash
systemctl stop edb-as-12

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -f /etc/repmgr/12/repmgr.conf \
  node rejoin \
  -d 'host=mosipdbuat02 user=repmgr dbname=repmgr port=5444 connect_timeout=2' \
  --dry-run \
  --verbose

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr \
  -f /etc/repmgr/12/repmgr.conf \
  node rejoin \
  -d 'host=mosipdbuat02 user=repmgr dbname=repmgr port=5444 connect_timeout=2' \
  --verbose
```

`mosipdbuat02` est le nœud promu dans ce scénario (incident sur `mosipdbuat01`). `wal_log_hints = on` permet à repmgr d’utiliser `pg_rewind` si les timelines ont divergé.

Si `node rejoin` échoue (timeline trop divergente, WAL manquant) : arrêter, vider le data dir, refaire un `standby clone` depuis le nouveau primary, puis `standby register --force`.

Redémarrer si `node rejoin` ne l’a pas déjà fait :

```bash
systemctl start edb-as-12
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

---

## 10. Checklists

### Mise en place initiale

- [ ] `dnf install -y edb-as12-repmgr --disablerepo="*" --enablerepo="edb-local"` OK sur les deux nœuds
- [ ] `repmgrd` désactivé
- [ ] `shared_preload_libraries` contient `repmgr` + restart
- [ ] WAL : `replica`, senders/slots, `wal_log_hints`
- [ ] `pg_hba` replication + db `repmgr` sur `CLUSTER_CIDR`
- [ ] Rôle `repmgr` SUPERUSER + REPLICATION, base `repmgr`
- [ ] `.pgpass` `0600` sur les deux nœuds
- [ ] `/etc/repmgr/12/repmgr.conf` actif (pas l’échantillon commenté) : `node_id`, hostname, `port=5444`, `failover=manual`, `service_*_command` systemd
- [ ] `/etc/sudoers.d/repmgr` validé (`visudo -cf`)
- [ ] SSH `enterprisedb` bidirectionnel
- [ ] `primary register` OK
- [ ] `standby clone` + `standby register` OK
- [ ] `cluster show` / `pg_stat_replication` / `pg_is_in_recovery()`

### Avant switchover

- [ ] Fenêtre de maintenance validée
- [ ] `cluster check` sans erreur
- [ ] Lag WAL proche de 0
- [ ] `--dry-run` du switchover OK
- [ ] Plan de rollback (switchover inverse) communiqué

### Après promote d’incident

- [ ] Ancien primary isolé / arrêté
- [ ] Nouveau primary : `pg_is_in_recovery() = false`
- [ ] Applications reconnectées au nouveau primary
- [ ] Ancien primary réintégré via `node rejoin` ou re-clone
- [ ] `cluster show` cohérent (1 primary, 1 standby)

---

## 11. Erreurs fréquentes

| Symptôme | Cause probable | Action |
|---|---|---|
| `connection to database failed` / auth | `.pgpass` absent, droits ≠ `0600`, `pg_hba` | Corriger auth, tester `psql -h … -U repmgr` |
| Connexion sur le **5432** | `port=5444` oublié dans `conninfo` | Ajouter `port=5444` partout |
| `could not load library repmgr` / extension absente | Pas de restart après `shared_preload_libraries` | `systemctl restart edb-as-12` |
| `directory exists and is not empty` au clone | Data dir standby déjà peuplé | Déplacer le dir, ou `--force` si destruction validée |
| Switchover : `unable to connect via SSH` | Pas de clé `enterprisedb`, `pg_bindir` faux | SSH `true` + `pg_ctl --version` à distance |
| Switchover : shutdown timeout | Checkpoints longs, I/O | Augmenter `shutdown_timeout` dans `repmgr.conf` si besoin, rerun `--dry-run` |
| Standby `pg_is_in_recovery() = false` après clone | Clone incomplet / `standby.signal` manquant | Ne pas ouvrir en écriture ; re-cloner |
| `node rejoin` rewind failed | WAL trop ancien, `wal_log_hints` off | Re-clone complet depuis le nouveau primary |
| Deux primary dans `cluster show` | Promote sans fence | Arrêter **immédiatement** l’ancien primary ; ne pas réconcilier à la main les écritures divergentes |

Option utile si le stop du primary est trop lent :

```conf
shutdown_timeout=60
```

---

## 12. Commandes de diagnostic (copie rapide)

```bash
REPMGR="/usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf"

sudo -iu enterprisedb $REPMGR cluster show
sudo -iu enterprisedb $REPMGR cluster matrix
sudo -iu enterprisedb $REPMGR cluster crosscheck
sudo -iu enterprisedb $REPMGR node check
sudo -iu enterprisedb $REPMGR service status

sudo -iu enterprisedb psql -p 5444 -d repmgr -c "SELECT node_id, node_name, type, active, upstream_node_id FROM repmgr.nodes;"
```

---

## 13. Détacher un standby (le rendre indépendant)

Objectif : sortir un nœud du cluster pour en faire une instance autonome en lecture/écriture, en conservant ses données.

Deux opérations distinctes sont nécessaires. `standby unregister` ne supprime que la ligne dans `repmgr.nodes` : le nœud continue de streamer. Il faut également le sortir du mode recovery.

**Opération irréversible** : après le promote, le nœud change de timeline. Une réintégration exige un `standby clone` complet.

### 13.1 Contrôle préalable, sur le primary

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT application_name, state, sync_state, replay_lsn FROM pg_stat_replication;"
```

Le lag doit être nul, sinon le nœud détaché partira d'un état incomplet.

### 13.2 Retirer le nœud des métadonnées, depuis le primary

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby unregister --node-id=<ID>
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d repmgr -c "SELECT node_id, node_name, type, active FROM repmgr.nodes;"
```

### 13.3 Sortir le nœud du recovery, sur le nœud détaché

Ne pas utiliser `repmgr standby promote`, qui le réinscrirait comme primary du même cluster :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT pg_promote(true, 60);"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT pg_is_in_recovery();"
```

Attendu : `f`.

### 13.4 Nettoyer le nœud détaché

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "ALTER SYSTEM RESET primary_conninfo;"
sudo -iu enterprisedb sudo -n systemctl reload edb-as-12
mv /etc/repmgr/12/repmgr.conf /etc/repmgr/12/repmgr.conf.detached
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SHOW archive_command;"
```

Sous EPAS 12, `primary_conninfo` est de contexte *postmaster* : `SHOW` affichera l'ancienne valeur jusqu'au prochain redémarrage. C'est sans effet tant que `standby.signal` est absent, ce paramètre n'étant lu qu'au démarrage en mode recovery.

Si `archive_command` pointe vers une destination partagée avec le cluster, la changer immédiatement pour ne pas polluer les WAL du cluster réel.

### 13.5 Nettoyer le primary — étape indispensable

Le slot devenu inactif retient les WAL indéfiniment. Sous EPAS 12, `max_slot_wal_keep_size` n'existe pas : rien ne borne cette rétention et le `pg_wal` peut saturer jusqu'à l'arrêt de l'instance.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT slot_name, slot_type, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS wal_retenu FROM pg_replication_slots;"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT pg_drop_replication_slot('<nom_du_slot>');"
```

Puis retirer les lignes `pg_hba.conf` autorisant l'IP du nœud détaché (`replication` et base `repmgr`), et recharger :

```bash
cp -a /data/mosip/edb/as12/data/pg_hba.conf /data/mosip/edb/as12/data/pg_hba.conf.bak.$(date +%Y%m%d)
grep -nE '<IP_DETACHEE>' /data/mosip/edb/as12/data/pg_hba.conf
sudo -iu enterprisedb sudo -n systemctl reload edb-as-12
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT * FROM pg_hba_file_rules WHERE error IS NOT NULL;"
```

### 13.6 Vérifier l'indépendance

| Contrôle | Primary | Nœud détaché |
|---|---|---|
| `pg_is_in_recovery()` | `f` | `f` |
| `pg_stat_replication` | 0 walsender | — |
| `pg_stat_wal_receiver` | — | 0 receiver |
| `standby.signal` | absent | absent |
| `timeline_id` | inchangée | incrémentée |

Preuve décisive, le test croisé dans la base `postgres` (jamais dans les bases MOSIP) : créer une table distincte sur chaque nœud, puis vérifier sur les deux qu'aucun ne voit celle de l'autre.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT tablename FROM pg_tables WHERE tablename LIKE 'test_independance%';"
```

### 13.7 Conséquences à annoncer

- Le cluster n'a plus de standby : plus de switchover, aucune reprise en cas de perte du primary.
- Le nœud détaché contient une copie complète des bases MOSIP et **accepte les écritures**. Toute application encore pointée dessus y écrira sans erreur, et ces données seront perdues pour le cluster réel. À contrôler :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p 5432 -d postgres -c "SELECT datname, usename, client_addr, count(*) FROM pg_stat_activity WHERE backend_type = 'client backend' AND client_addr IS NOT NULL GROUP BY 1,2,3 ORDER BY 4 DESC;"
```

- Les archives WAL du nœud détaché ne sont plus consommées : prévoir une rétention, ou couper l'archivage s'il n'a plus d'objet.

---

## 14. Hors scope

- Failover automatique, nœud witness, daemon `repmgrd`
- VIP / PgBouncer / HAProxy
- EDB Failover Manager (EFM), alternative supportée par EDB
- Changement du code applicatif (chaîne de connexion, retry)

Pour un failover automatique ultérieur : ajouter un **witness** sur un troisième hôte (jamais colocalisé avec le primary), puis seulement activer `repmgrd`.
