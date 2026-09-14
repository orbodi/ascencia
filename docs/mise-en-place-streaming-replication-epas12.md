# Mise en place de la streaming replication — EPAS 12

Réplication physique native entre deux instances EDB Postgres Advanced Server 12, indépendamment de repmgr.

## Situer ce document

La streaming replication est la **couche de transport** : elle copie les WAL du primary vers le standby. repmgr est une **couche de pilotage** au-dessus : il enregistre les nœuds, orchestre les switchovers et surveille l'état. La réplication fonctionne parfaitement sans repmgr ; repmgr ne fonctionne pas sans elle.

Deux façons de créer le standby :

| Approche | Commande | Quand l'utiliser |
|---|---|---|
| Native | `pg_basebackup` | Réplication seule, ou contrôle fin des options |
| Via repmgr | `repmgr standby clone` | repmgr est déjà en place ; il encapsule `pg_basebackup` et enregistre le nœud |

Ce document couvre l'approche native. Pour la couche repmgr, voir [`mise-en-place-cluster-repmgr-epas12.md`](mise-en-place-cluster-repmgr-epas12.md).

## Spécificités PostgreSQL 12 à connaître

Trois changements majeurs par rapport aux versions 9.x à 11, source de la plupart des erreurs :

1. **`recovery.conf` n'existe plus.** Les paramètres de recovery sont désormais dans `postgresql.conf` ou `postgresql.auto.conf`. Un `recovery.conf` présent dans la data dir **empêche le démarrage**.
2. **Le mode standby est déclaré par un fichier vide `standby.signal`** dans la data dir. C'est lui, et non `primary_conninfo`, qui détermine si l'instance démarre en réplication.
3. **`primary_conninfo` est de contexte *postmaster*** : le modifier exige un redémarrage. Ce n'est qu'à partir de PostgreSQL 13 qu'un simple reload suffit.

| Convention | Signification |
|---|---|
| **[P]** | Sur le **primary** |
| **[S]** | Sur le **standby** |

---

## Phase 0 — Prérequis

### Étape 1 — Compatibilité **[P+S]**

Le standby est une copie binaire du primary. Les deux instances doivent partager :

- la **même version majeure** d'EPAS (12), et idéalement la même version mineure
- la même architecture processeur et le même `--with-blocksize`
- des chemins de tablespaces compatibles, ou un remappage explicite

```bash
/usr/edb/as12/bin/psql --version
rpm -q edb-as12-server
```

### Étape 2 — Réseau, comptes, espace disque **[P+S]**

```bash
hostname -I
ss -lntp | grep -E '5432|5444'
getent passwd enterprisedb
df -h <PGDATA_PARENT>
```

Le port du primary doit être joignable depuis le standby. Prévoyez sur le standby au moins l'espace occupé par la data dir du primary, plus une marge confortable pour `pg_wal`.

Relevez le port et la data dir réels via l'instance en fonctionnement, jamais par supposition :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT current_setting('port'), current_setting('data_directory'), current_setting('hba_file');"
```

---

## Phase 1 — Préparer le primary

### Étape 3 — Paramètres WAL **[P]**

Dans `postgresql.conf` :

```conf
listen_addresses = '*'          # ou la liste des IP internes
wal_level = replica             # 'logical' si de la réplication logique ou du CDC coexiste
max_wal_senders = 10            # un par standby, plus une marge pour pg_basebackup
max_replication_slots = 10      # si vous utilisez des slots
wal_keep_segments = 256         # PG12 : wal_keep_size n'apparaît qu'en PG13
hot_standby = on                # permet les lectures sur le standby
wal_log_hints = on              # requis pour pg_rewind et pour repmgr node rejoin
hot_standby_feedback = on       # le standby signale ses snapshots, limite les conflits de VACUUM
```

`wal_level` et `max_wal_senders` exigent un **redémarrage** :

```bash
systemctl restart edb-as-12
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT name, setting FROM pg_settings WHERE name IN ('wal_level','max_wal_senders','max_replication_slots','wal_keep_segments','wal_log_hints','hot_standby');"
```

`wal_keep_segments` fixe le nombre de segments de 16 Mo conservés au-delà du strict nécessaire. Il donne au standby une marge de reconnexion après une coupure : 256 segments représentent environ 4 Go d'historique. Un slot de réplication offre une garantie plus forte, avec le risque décrit à l'étape 6.

### Étape 4 — Rôle de réplication **[P]**

Un rôle dédié, sans privilège superutilisateur. `REPLICATION` suffit pour la réplication physique :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '<MOT_DE_PASSE>';"
```

Le compte `repmgr` utilisé par repmgr est distinct et doit, lui, être superutilisateur. Les deux peuvent coexister : c'est le cas sur l'UAT MOSIP, où `replicator` porte le flux et `repmgr` le pilotage.

### Étape 5 — Autorisation réseau **[P]**

La base logique `replication` est un mot-clé, pas une vraie base. Elle doit être déclarée explicitement : une règle sur `all` ne la couvre pas.

Dans `pg_hba.conf`, en adaptant la méthode à `password_encryption` :

```text
host  replication  replicator  <IP_STANDBY>/32  scram-sha-256
```

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/pg_ctl reload -D <PGDATA>
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT type, database, user_name, address, auth_method FROM pg_hba_file_rules WHERE 'replication' = ANY(database);"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT * FROM pg_hba_file_rules WHERE error IS NOT NULL;"
```

La seconde requête doit ne rien renvoyer. Une erreur de syntaxe est ignorée au `reload`, les anciennes règles restant actives, mais empêche le prochain démarrage.

### Étape 6 — Slot de réplication (recommandé) **[P]**

Un slot garantit que le primary ne recycle aucun WAL non encore reçu par le standby, quelle que soit la durée de l'interruption.

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT pg_create_physical_replication_slot('<NOM_SLOT>');"
```

> **Danger à comprendre avant d'en créer un.** Sous EPAS 12, le paramètre `max_slot_wal_keep_size` n'existe pas : il n'apparaît qu'en PostgreSQL 13. Un slot dont le consommateur disparaît retient donc les WAL **sans aucune borne**, jusqu'à saturation du système de fichiers et arrêt de l'instance. Un slot logique inactif bloque en outre le `VACUUM` par son `catalog_xmin` figé, ce qui provoque du bloat puis, à terme, un risque de wraparound.
>
> Un slot doit donc être supervisé, et **supprimé dès qu'il n'a plus de consommateur**.

Supervision à mettre en place dès la création :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT slot_name, slot_type, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS wal_retenu FROM pg_replication_slots ORDER BY 4 DESC;"
```

Alternative sans slot : s'appuyer sur `wal_keep_segments` et, si un archivage existe, sur un `restore_command` côté standby. Moins de risque de saturation, mais un standby arrêté trop longtemps devra être recloné.

---

## Phase 2 — Créer le standby

### Étape 7 — Fichier `.pgpass` **[S]**

`pg_basebackup -R` écrit `primary_conninfo` **sans le mot de passe**. Le standby doit donc pouvoir s'authentifier par `.pgpass`, sinon il ne se rattachera pas après le clone.

Dans le home de `enterprisedb` relevé à l'étape 2 :

```text
<IP_PRIMARY>:<PORT>:replication:replicator:<MOT_DE_PASSE>
```

```bash
chown enterprisedb:enterprisedb /var/lib/edb/.pgpass
chmod 0600 /var/lib/edb/.pgpass
```

Test avant de lancer la copie :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql "host=<IP_PRIMARY> port=<PORT> user=replicator dbname=postgres replication=database" -c "IDENTIFY_SYSTEM;"
```

La commande doit renvoyer le `systemid`, la timeline et la LSN courante, sans invite de mot de passe. Si elle échoue ici, `pg_basebackup` échouera aussi.

### Étape 8 — Copie de base **[S]**

L'instance locale doit être **arrêtée** et la data dir **vide**. `pg_basebackup` refuse d'écrire dans un répertoire non vide.

```bash
systemctl stop edb-as-12

# Si un contenu existe et doit être conservé :
# mv <PGDATA> <PGDATA>.bak.$(date +%Y%m%d%H%M)
mkdir -p <PGDATA>
chown enterprisedb:enterprisedb <PGDATA>
chmod 700 <PGDATA>

sudo -iu enterprisedb /usr/edb/as12/bin/pg_basebackup \
  -h <IP_PRIMARY> -p <PORT> -U replicator \
  -D <PGDATA> \
  -Fp -Xs -R -P -v \
  -c fast \
  -S <NOM_SLOT>
```

Signification des options :

| Option | Effet |
|---|---|
| `-Fp` | Format `plain` : arborescence directement exploitable |
| `-Xs` | Les WAL sont streamés **pendant** la copie, sur une seconde connexion. Évite l'échec sur les bases volumineuses dont les WAL seraient recyclés avant la fin |
| `-R` | Écrit `standby.signal` et ajoute `primary_conninfo` dans `postgresql.auto.conf` |
| `-P -v` | Progression et détail |
| `-c fast` | Checkpoint immédiat sur le primary au lieu d'attendre le checkpoint naturel |
| `-S` | Utilise le slot créé à l'étape 6 |

Ajoutez `-C -S <NOM_SLOT>` pour créer le slot au moment de la copie plutôt qu'à l'étape 6, et `--waldir=<CHEMIN>` si `pg_wal` doit résider sur un volume distinct.

`-Xs` consomme un `wal_sender` en plus de celui de la copie : prévoyez `max_wal_senders` en conséquence.

### Étape 9 — Vérifier le résultat de la copie **[S]**

```bash
ls -l <PGDATA>/standby.signal
grep -n 'primary_conninfo\|primary_slot_name' <PGDATA>/postgresql.auto.conf
ls <PGDATA>/recovery.conf 2>/dev/null && echo "A SUPPRIMER — empeche le demarrage en PG12"
```

`standby.signal` doit exister, `primary_conninfo` être renseigné, et aucun `recovery.conf` ne doit subsister.

Ajoutez un `application_name` dans `primary_conninfo` : il identifie le standby dans `pg_stat_replication` et sert de référence pour une éventuelle réplication synchrone.

```conf
primary_conninfo = 'host=<IP_PRIMARY> port=<PORT> user=replicator application_name=<NOM_STANDBY>'
primary_slot_name = '<NOM_SLOT>'
```

Sous EPAS 12, ces deux paramètres ne sont pris en compte qu'au démarrage.

---

## Phase 3 — Démarrer et vérifier

### Étape 10 — Démarrage **[S]**

```bash
systemctl start edb-as-12
systemctl status edb-as-12 --no-pager | head -5
```

En cas d'échec, la cause est dans le journal de l'instance :

```bash
journalctl -u edb-as-12 -n 50 --no-pager
```

### Étape 11 — Contrôles côté standby **[S]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT pg_is_in_recovery();"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT status, sender_host, sender_port, slot_name, latest_end_lsn FROM pg_stat_wal_receiver;"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT now() - pg_last_xact_replay_timestamp() AS retard_rejeu;"
```

Attendu : `pg_is_in_recovery()` à `t`, un `wal_receiver` en statut `streaming`, et un retard de rejeu faible.

Une tentative d'écriture doit être refusée avec `cannot execute ... in a read-only transaction`.

### Étape 12 — Contrôles côté primary **[P]**

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT application_name, client_addr, state, sync_state, sent_lsn, replay_lsn, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)) AS retard FROM pg_stat_replication;"
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT slot_name, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS wal_retenu FROM pg_replication_slots;"
```

Attendu : une ligne en `state = streaming`, `sync_state = async` par défaut, un retard faible, et le slot en `active = t`.

### Étape 13 — Test fonctionnel **[P] puis [S]**

Ne vous contentez pas des compteurs : validez la propagation réelle. Dans la base `postgres`, jamais dans les bases applicatives.

Sur le primary :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "CREATE TABLE test_replication(id int, ts timestamptz DEFAULT now()); INSERT INTO test_replication(id) VALUES (1);"
```

Sur le standby, quelques secondes plus tard :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "SELECT * FROM test_replication;"
```

La ligne doit apparaître. Nettoyage depuis le primary :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/psql -p <PORT> -d postgres -c "DROP TABLE test_replication;"
```

---

## Phase 4 — Supervision

Trois indicateurs suffisent à détecter l'essentiel des dérives.

**Retard de réplication**, sur le primary :

```sql
SELECT application_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS retard_octets,
       write_lag, flush_lag, replay_lag
FROM pg_stat_replication;
```

**Absence de standby connecté** : `SELECT count(*) FROM pg_stat_replication;` à zéro alors qu'un standby est attendu signale une rupture du flux.

**Rétention des slots**, le risque le plus insidieux sous EPAS 12 puisque rien ne la borne :

```sql
SELECT slot_name, active,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS wal_retenu
FROM pg_replication_slots
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC;
```

Alertez sur tout slot `active = f` dont la rétention croît. Surveillez conjointement l'espace libre de `pg_wal`.

---

## Options avancées

### Réplication synchrone

Par défaut la réplication est **asynchrone** : le primary valide sans attendre le standby, ce qui autorise une perte de transactions en cas de crash. Le mode synchrone supprime ce risque au prix de la latence d'écriture.

```conf
synchronous_standby_names = '<NOM_STANDBY>'
synchronous_commit = on
```

> **Piège majeur avec un seul standby.** Si le standby devient indisponible, le primary **bloque toutes les validations** en attendant un accusé qui ne viendra jamais. Le cluster paraît figé alors que le primary est sain. Le mode synchrone ne se justifie qu'avec au moins deux standbys, ou avec `ANY 1 (...)` et une supervision capable de retirer le paramètre en urgence.

### Réplication en cascade

Un standby peut alimenter un autre standby, ce qui décharge le primary. Le standby intermédiaire a besoin de `max_wal_senders` et d'une règle `pg_hba` pour `replication`, exactement comme un primary.

### Réplication logique et CDC

`wal_level = logical` permet la coexistence de slots logiques, utilisés par exemple par Debezium pour du CDC. Ces slots relèvent de la même vigilance de rétention, en plus sévère : leur `catalog_xmin` bloque le `VACUUM`.

L'extension EDB `pg_failover_slots` synchronise les slots logiques vers le standby, afin qu'ils survivent à une bascule. Sans elle, un failover détruit les slots logiques et impose un re-snapshot complet des tables suivies.

---

## Erreurs fréquentes

| Message | Cause | Résolution |
|---|---|---|
| `no pg_hba.conf entry for replication connection` | Règle sur `all` au lieu de `replication` | Ligne dédiée `host replication ...` (étape 5) |
| `fe_sendauth: no password supplied` | `.pgpass` absent, mal placé, ou droits ≠ `0600` | Étape 7, dans le home réel de `enterprisedb` |
| `directory "..." exists but is not empty` | Data dir du standby non vide | Déplacer le répertoire avant `pg_basebackup` |
| `requested WAL segment has already been removed` | WAL recyclés pendant une interruption longue, sans slot | Utiliser `-Xs`, un slot, ou augmenter `wal_keep_segments` |
| `number of requested standby connections exceeds max_wal_senders` | `max_wal_senders` trop bas, `-Xs` en consommant un de plus | Augmenter le paramètre et redémarrer |
| Le standby démarre en primary | `standby.signal` absent | Créer le fichier vide et redémarrer |
| Refus de démarrage, mention de `recovery.conf` | Fichier hérité d'une version antérieure à 12 | Le supprimer |
| `primary_conninfo` modifié sans effet | Contexte *postmaster* en PG12 | Redémarrer l'instance |
| `pg_wal` sature le disque | Slot inactif sans borne sous EPAS 12 | Supprimer le slot orphelin, superviser la rétention |

---

## Annexe — Valeurs relevées sur l'UAT MOSIP

La réplication y préexistait à la mise en place de repmgr. Configuration constatée :

| Élément | Valeur |
|---|---|
| Rôle de réplication | `replicator` |
| Rôle de pilotage repmgr | `repmgr` (superutilisateur) |
| Mode | streaming **asynchrone** |
| Slot physique | `dc2_slot` |
| `application_name` du standby | `dc2-uat` |
| `wal_level` | `logical` |
| `max_wal_senders` / `max_replication_slots` | 16 / 16 |
| `wal_log_hints` | `on` |
| `password_encryption` | `scram-sha-256` |
| Extension de bascule des slots | `pg_failover_slots` |
| Port | `5432` |
| Data directory | `/data/mosip/edb/as12/data` |

Règles `pg_hba.conf` en place sur le primary :

```text
host  replication  replicator  <IP_STANDBY>/32  scram-sha-256
host  repmgr       repmgr      <IP_STANDBY>/32  scram-sha-256
```

`wal_level = logical` s'explique par la présence de slots logiques de CDC (`streamregprc`, `streamaudit`, `streammaster`, `streamauth`, `streamschtsp`). Ces slots relèvent de l'équipe applicative : leur suppression imposerait un re-snapshot des tables concernées, et leur inactivité prolongée fait croître `pg_wal` sans limite.
