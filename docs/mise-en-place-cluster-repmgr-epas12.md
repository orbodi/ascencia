# Mise en place d'un cluster repmgr sur EPAS 12 — pas à pas

Document **séquentiel** : les étapes s'exécutent dans l'ordre, chacune avec sa vérification. Ne passez pas à la suivante si la vérification échoue.

Pour la documentation de référence (paramètres, exploitation, détachement d'un nœud), voir [`repmgr-epas12.md`](repmgr-epas12.md). Pour la couche de réplication native sous-jacente, voir [`mise-en-place-streaming-replication-epas12.md`](mise-en-place-streaming-replication-epas12.md).

**Cible** : cluster 2 nœuds, 1 primary + 1 standby, failover **manuel**, sans witness ni `repmgrd`.

| Convention | Signification |
|---|---|
| **[P]** | À exécuter sur le **primary** |
| **[S]** | À exécuter sur le **standby** |
| **[P+S]** | À exécuter sur **les deux** nœuds |

Toutes les commandes sont lancées en `root`, et les commandes PostgreSQL via `sudo -iu enterprisedb`.

---

## Phase 0 — Découverte de l'environnement

**Ne sautez pas cette phase.** Les chemins et le port d'une installation EPAS varient fortement d'un site à l'autre. Supposer les valeurs par défaut est la première cause d'échec : sur l'UAT MOSIP, le port réel était 5432 et non 5444, et la data dir `/data/mosip/edb/as12/data` et non `/var/lib/edb/as12/data`.

### Étape 1 — Identité et compte de service **[P+S]**

```bash
hostname
hostname -I
id enterprisedb
getent passwd enterprisedb
```

Relevez le **home** de `enterprisedb` : c'est là qu'iront `.pgpass` et les clés SSH. Sur EPAS il vaut souvent `/var/lib/edb`, pas `/home/enterprisedb`.

Si les deux serveurs portent le même hostname, notez leurs IP et travaillez exclusivement avec celles-ci.

### Étape 2 — Binaires **[P+S]**

```bash
ls -l /usr/edb/as12/bin/repmgr /usr/edb/as12/bin/psql /usr/edb/as12/bin/pg_ctl
```

Ce répertoire sera `pg_bindir` et `repmgr_bindir`. Si les fichiers sont absents, cherchez avec `rpm -ql edb-as12-server-core | grep bin/psql`.

### Étape 3 — Port et data directory réels **[P]**

```bash
ss -lntp | egrep '5444|5432'
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT current_setting('port') AS port, current_setting('data_directory') AS data_directory, current_setting('config_file') AS config_file, current_setting('hba_file') AS hba_file;"
```

C'est l'instance en fonctionnement qui fait foi, pas les répertoires présents sur le disque. Un `/var/lib/edb/as12/data` existant mais vide est un leurre fréquent.

### Étape 4 — Service systemd **[P+S]**

```bash
systemctl status edb-as-12 --no-pager | head -5
```

Si le nom diffère : `systemctl list-units --type=service --all '*edb*' --no-pager`. Ce nom servira dans les `service_*_command`.

### Étape 5 — État de la réplication et paramètres WAL **[P]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT pid, usename, client_addr, application_name, state, sync_state FROM pg_stat_replication;"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT name, setting FROM pg_settings WHERE name IN ('shared_preload_libraries','wal_level','hot_standby','max_wal_senders','max_replication_slots','wal_log_hints','password_encryption');"
```

Cette étape détermine le chemin à suivre :

- **`pg_stat_replication` vide** : aucun standby. Vous suivrez la phase 5, variante A (clone).
- **`pg_stat_replication` peuplé** : une réplication existe déjà. Vous suivrez la variante B (enregistrement sans clone). **Ne clonez pas**, cela écraserait la data dir du standby.

Relevez aussi `password_encryption` : il détermine la méthode à écrire dans `pg_hba.conf` (`scram-sha-256` ou `md5`).

### Étape 6 — Traces repmgr éventuelles **[P]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "\du repmgr"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "\l repmgr"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d repmgr -c "SELECT node_id, node_name, type, active, conninfo, config_file FROM repmgr.nodes;"
```

Si `repmgr.nodes` est déjà peuplé, le cluster a été partiellement configuré : les phases 3 et 4 sont à sauter, et vos `node_name` devront **reprendre exactement** ceux déjà enregistrés.

---

## Phase 1 — Installation du paquet

### Étape 7 — Installer repmgr **[P+S]**

Depuis un dépôt local :

```bash
dnf install -y edb-as12-repmgr --disablerepo="*" --enablerepo="edb-local"
```

`--disablerepo="*"` évite qu'une autre version soit tirée depuis BaseOS, EPEL ou le dépôt EDB public.

Vérification :

```bash
rpm -q edb-as12-repmgr
/usr/edb/as12/bin/repmgr --version
```

### Étape 8 — Neutraliser `repmgrd` **[P+S]**

Sur un cluster à 2 nœuds sans witness, le failover automatique expose au split-brain :

```bash
systemctl disable --now repmgrd 2>/dev/null || true
systemctl disable --now edb-as12-repmgrd 2>/dev/null || true
```

> **Attention** : le paquet réinstalle un `repmgr.conf` d'exemple. Si une configuration existait, elle est écrasée. Sauvegardez avant, ou reconstruisez-la en phase 5.

---

## Phase 2 — Paramètres de l'instance

### Étape 9 — Paramètres WAL **[P]**

À poser **avant** l'enregistrement. Le standby les héritera par le clone.

Dans le `postgresql.conf` identifié à l'étape 3 :

```conf
shared_preload_libraries = 'repmgr'   # conserver les modules déjà présents, séparés par des virgules
wal_level = replica                   # 'logical' convient aussi
hot_standby = on
max_wal_senders = 10
max_replication_slots = 10
wal_keep_segments = 256               # PG12 : wal_keep_size n'existe qu'à partir de PG13
wal_log_hints = on                    # requis pour pg_rewind / node rejoin
hot_standby_feedback = on
```

`shared_preload_libraries` et `wal_level` exigent un **redémarrage** :

```bash
systemctl restart edb-as-12
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SHOW shared_preload_libraries;"
```

`repmgr` doit apparaître dans la liste. Ne touchez pas à un `archive_command` déjà en production.

---

## Phase 3 — Rôle et base repmgr

### Étape 10 — Créer le rôle et la base **[P]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "CREATE USER repmgr WITH REPLICATION LOGIN SUPERUSER PASSWORD '<MOT_DE_PASSE>';"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "CREATE DATABASE repmgr OWNER repmgr;"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "ALTER USER repmgr SET search_path TO repmgr, \"\$user\", public;"
```

`SUPERUSER` est nécessaire pour installer l'extension et pour `pg_promote()` sous PostgreSQL 12.

> Évitez les commandes `psql -c` sur plusieurs lignes : le collage en terminal peut fusionner les lignes et produire des erreurs de syntaxe. Une commande par appel.

### Étape 11 — Autorisations réseau **[P+S]**

Dans le `pg_hba.conf` identifié à l'étape 3, en adaptant la méthode à `password_encryption`. Les **deux** nœuds ont besoin des deux lignes, afin que le switchover fonctionne dans les deux sens :

```text
host  replication  repmgr  <IP_AUTRE_NOEUD>/32  scram-sha-256
host  repmgr       repmgr  <IP_AUTRE_NOEUD>/32  scram-sha-256
```

La ligne `replication` est celle qu'on oublie : sans elle, le switchover échoue au moment où l'ancien primary tente de se rattacher.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/pg_ctl reload -D <PGDATA>
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT * FROM pg_hba_file_rules WHERE error IS NOT NULL;"
```

Aucune ligne retournée : le fichier est syntaxiquement valide.

### Étape 12 — Fichier `.pgpass` **[P+S]**

Dans le home relevé à l'étape 1. Les lignes `replication` sont **obligatoires**, faute de quoi le switchover échoue sur `fe_sendauth: no password supplied` :

```text
<IP_P>:<PORT>:repmgr:repmgr:<MOT_DE_PASSE>
<IP_S>:<PORT>:repmgr:repmgr:<MOT_DE_PASSE>
<IP_P>:<PORT>:replication:repmgr:<MOT_DE_PASSE>
<IP_S>:<PORT>:replication:repmgr:<MOT_DE_PASSE>
```

```bash
chown enterprisedb:enterprisedb /var/lib/edb/.pgpass
chmod 0600 /var/lib/edb/.pgpass
sudo -iu enterprisedb /usr/edb/as12/bin/psql -h <IP_P> -p <PORT> -U repmgr -d repmgr -c "SELECT current_user;"
```

Le test doit réussir **sans invite de mot de passe**. Pour relire le fichier sans exposer le secret :

```bash
awk -F: '{print $1":"$2":"$3":"$4":***"}' /var/lib/edb/.pgpass
```

---

## Phase 4 — Configuration repmgr

### Étape 13 — Écrire `repmgr.conf` **[P+S]**

Chemin **absolu**, stocké dans les métadonnées et réutilisé lors des exécutions distantes : `/etc/repmgr/12/repmgr.conf`.

```bash
cp -a /etc/repmgr/12/repmgr.conf /etc/repmgr/12/repmgr.conf.sample
mkdir -p /var/log/edb/as12
touch /var/log/edb/as12/repmgr.log
```

Sur le **primary** :

```conf
node_id=1
node_name='<NOM_NOEUD_1>'
conninfo='host=<IP_P> user=repmgr dbname=repmgr port=<PORT> connect_timeout=2'
data_directory='<PGDATA>'
config_directory='<PGDATA>'
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

Sur le **standby**, le même fichier avec `node_id=2`, son `node_name` et son propre `conninfo`.

Quatre pièges à éviter :

1. Le fichier livré par le paquet a **tous les paramètres commentés**. `node_id`, `node_name`, `conninfo` et `data_directory` doivent être **actifs**, sinon `repmgr` refuse de démarrer.
2. **Précisez toujours `port=`** dans `conninfo`. Le profil `enterprisedb` exporte `PGPORT=5444` : sans port explicite, les appels distants tentent 5444 et échouent en `Connection refused`.
3. `node_name` doit être **stable**, jamais `primary` ni `standby`, puisque les rôles s'échangent. Si le cluster est déjà enregistré, reprenez à l'identique les noms de `repmgr.nodes`.
4. Les `service_*_command` passent par systemd. Sans eux, repmgr appelle `pg_ctl` directement et systemd perd le suivi du service.

```bash
chown enterprisedb:enterprisedb /etc/repmgr/12/repmgr.conf /var/log/edb/as12/repmgr.log
chmod 640 /etc/repmgr/12/repmgr.conf
```

### Étape 14 — Autoriser systemd sans mot de passe **[P+S]**

```bash
cat > /etc/sudoers.d/repmgr <<'EOF'
Defaults:enterprisedb !requiretty
enterprisedb ALL=(root) NOPASSWD: /usr/bin/systemctl start edb-as-12, /usr/bin/systemctl stop edb-as-12, /usr/bin/systemctl restart edb-as-12, /usr/bin/systemctl reload edb-as-12, /usr/bin/systemctl status edb-as-12
EOF
chmod 440 /etc/sudoers.d/repmgr
visudo -cf /etc/sudoers.d/repmgr
```

Vérification, sur chaque nœud :

```bash
sudo -iu enterprisedb sudo -n systemctl status edb-as-12 --no-pager | head -3
```

Le service doit s'afficher, sans demande de mot de passe.

### Étape 15 — SSH sans mot de passe **[P+S]**

Le switchover exécute des commandes à distance sous l'identité `enterprisedb`.

```bash
sudo -iu enterprisedb ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519
```

Échangez les clés publiques entre les deux nœuds, puis testez **dans les deux sens** :

```bash
sudo -iu enterprisedb ssh -o BatchMode=yes -o ConnectTimeout=10 <IP_AUTRE_NOEUD> true && echo SSH_OK || echo SSH_FAIL
sudo -iu enterprisedb ssh -o BatchMode=yes <IP_AUTRE_NOEUD> /usr/edb/as12/bin/pg_ctl --version
```

Les deux directions doivent répondre `SSH_OK`. Un seul sens fonctionnel suffit à faire échouer le switchover inverse.

---

## Phase 5 — Enregistrement du cluster

### Étape 16 — Enregistrer le primary **[P]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf primary register --dry-run
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf primary register
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

Cette commande installe l'extension `repmgr` et crée la table `repmgr.nodes`. Elle précède obligatoirement tout enregistrement de standby.

### Étape 17, variante A — Créer le standby par clone **[S]**

**Uniquement si aucune réplication n'existait** à l'étape 5. Cette opération **détruit** le contenu de la data dir du standby.

```bash
systemctl stop edb-as-12
# mv <PGDATA> <PGDATA>.bak.$(date +%Y%m%d%H%M)   # si un ancien contenu doit être conservé

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -h <IP_P> -U repmgr -d repmgr -p <PORT> \
  -f /etc/repmgr/12/repmgr.conf standby clone --dry-run

sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -h <IP_P> -U repmgr -d repmgr -p <PORT> \
  -f /etc/repmgr/12/repmgr.conf standby clone

systemctl start edb-as-12
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby register
```

### Étape 17, variante B — Enregistrer un standby existant **[S]**

**Si une réplication fonctionnait déjà.** Aucun clone, aucun arrêt de service :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby register
```

Ajoutez `--force` si un enregistrement obsolète existe pour ce `node_id`.

---

## Phase 6 — Vérifications

### Étape 18 — État du cluster **[P+S]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf node check
```

Lancez ces commandes **depuis les deux nœuds** : c'est le seul moyen de détecter une configuration correcte d'un côté et défaillante de l'autre.

Attendu sur `cluster show` : un `primary` marqué `* running`, un `standby` marqué `running` avec le primary en `Upstream`, et une **timeline identique**.

Attendu sur `node check` : toutes les lignes en `OK`. Côté primary, `Downstream servers` doit compter le standby ; côté standby, `Replication lag` doit être proche de zéro.

`cluster check` n'existe pas en repmgr 5.3 : utilisez `node check`.

### Étape 19 — Contrôles SQL **[P]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT application_name, state, sync_state, pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS lag_bytes FROM pg_stat_replication;"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT slot_name, slot_type, active FROM pg_replication_slots;"
```

Sur le standby, `SELECT pg_is_in_recovery();` doit renvoyer `t`, et une tentative d'écriture doit être refusée.

---

## Phase 7 — Validation par switchover

### Étape 20 — Simulation **[S]**

`--dry-run` ne modifie aucun rôle. C'est le contrôle le plus complet de la chaîne SSH, sudo, authentification et réplication.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby switchover --dry-run
```

Attendu en dernière ligne : `INFO: prerequisites for executing STANDBY SWITCHOVER are met`.

En cas d'échec, consultez la table des erreurs en fin de document. Ne passez pas à l'étape suivante avant d'avoir un dry-run propre.

### Étape 21 — Switchover réel **[S]**

**N'arrêtez pas le primary vous-même.** Les deux instances doivent être en fonctionnement : c'est repmgr qui arrête le primary au bon moment, après avoir vérifié le rattrapage des WAL. Un primary arrêté à l'avance transforme l'opération en incident et impose un `standby promote` suivi d'un `node rejoin`.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby switchover
```

Déroulement : contrôles, arrêt propre du primary via `service_stop_command`, promotion du standby par `pg_promote()`, puis redémarrage de l'ancien primary en standby de la nouvelle primaire.

Indisponibilité en écriture : de l'ordre de 10 à 30 secondes sur une instance saine, bornée à `shutdown_check_timeout` (60 secondes par défaut) pour la phase d'arrêt. Sur une instance très chargée, le checkpoint d'arrêt est le facteur dominant.

### Étape 22 — Après le switchover **[P+S]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

Les rôles sont inversés et la timeline a été incrémentée. **repmgr ne bascule pas les applications** : sans VIP ni proxy, les chaînes de connexion doivent être repointées vers la nouvelle primaire, sinon les écritures échouent sur le standby en lecture seule.

Pour revenir à la topologie initiale, relancez un switchover depuis l'autre nœud, à nouveau avec `--dry-run` d'abord.

---

## Récapitulatif

| Phase | Étapes | Objet |
|---|---|---|
| 0 | 1 à 6 | Découverte : chemins, port, service, réplication existante |
| 1 | 7 à 8 | Paquet installé, `repmgrd` neutralisé |
| 2 | 9 | Paramètres WAL et `shared_preload_libraries` |
| 3 | 10 à 12 | Rôle `repmgr`, `pg_hba.conf`, `.pgpass` |
| 4 | 13 à 15 | `repmgr.conf`, sudoers, SSH bidirectionnel |
| 5 | 16 à 17 | `primary register`, puis clone ou enregistrement |
| 6 | 18 à 19 | `cluster show` et `node check` sur les deux nœuds |
| 7 | 20 à 22 | Dry-run, switchover réel, bascule applicative |

---

## Erreurs rencontrées et résolution

| Message | Cause | Résolution |
|---|---|---|
| `"node_id": required parameter was not found` | Fichier d'exemple du paquet, paramètres commentés | Réécrire `repmgr.conf` (étape 13) |
| `Connection refused ... port 5444` | `PGPORT=5444` et `conninfo` sans port | Ajouter `port=` dans le fichier **et** dans `repmgr.nodes` |
| `No route to host ... port 5444` | Même cause, avec un firewall ouvert sur 5432 uniquement | Idem |
| `aucune entrée dans pg_hba.conf pour la connexion de la réplication` | Ligne `replication` absente sur le nœud cible | Étape 11, sur les deux nœuds |
| `fe_sendauth: no password supplied` | `.pgpass` sans entrée pour la base `replication` | Étape 12 |
| `unable to connect via SSH` | Clé `enterprisedb` absente, ou `pg_bindir` erroné | Étape 15 |
| `unknown repmgr action 'cluster check'` | Commande inexistante en repmgr 5.3 | Utiliser `node check` |
| `directory exists and is not empty` | Data dir du standby non vide au clone | Déplacer le répertoire, ou `--force` après validation |
| `syntax error at or near "="` en `psql -c` | Lignes fusionnées au collage en terminal | Une commande `psql -c` par ligne |

Si le `conninfo` en base est incorrect alors que `cluster show` fonctionne, corrigez les métadonnées :

```sql
UPDATE repmgr.nodes SET conninfo = 'host=<IP> user=repmgr dbname=repmgr port=<PORT> connect_timeout=2' WHERE node_id = <ID>;
```

---

## Annexe — Valeurs relevées sur l'UAT MOSIP

Référence de ce qu'a donné la phase 0 sur cet environnement. **Ne les reprenez pas telles quelles** sur un autre site.

| Élément | Valeur |
|---|---|
| Compte OS et base | `enterprisedb`, home `/var/lib/edb` |
| Port | `5432` |
| Binaires | `/usr/edb/as12/bin` |
| Data directory | `/data/mosip/edb/as12/data` |
| Service systemd | `edb-as-12` |
| Version repmgr | 5.3 (extension et binaire) |
| Nœud 1 | `dc1-uat` — `172.16.34.20` |
| Nœud 2 | `dc2-uat` — `172.17.34.20` |
| Réplication | streaming **asynchrone** |
| `password_encryption` | `scram-sha-256` |
| `wal_level` | `logical` |

Deux particularités de ce site : la réplication préexistait, ce qui a imposé la variante B de l'étape 17, et les deux serveurs partageaient le même hostname, ce qui a rendu obligatoire l'usage des adresses IP dans toutes les configurations.
