# Compte-rendu — Mise en place et test repmgr EPAS 12 (UAT)

| Champ | Valeur |
|---|---|
| Type | Compte-rendu d’intervention / Change Request |
| Environnement | UAT MOSIP — EPAS 12 |
| Date | 21 août 2026 |
| Objet | Finaliser la configuration **repmgr 5.3** (failover **manuel**) et valider un **switchover** réel |
| Périmètre | `dc1-uat` (`172.16.34.20`) / `dc2-uat` (`172.17.34.20`) |
| Hors périmètre | Failover automatique (`repmgrd`), witness, VIP, bascule applicative MOSIP, EFM |
| Statut | **OK** — switchover réel testé avec succès |

---

## 1. Contexte

Le cluster avait déjà :

- EPAS 12 en service `edb-as-12`, data dir `/data/mosip/edb/as12/data`, port **5432**
- Streaming replication **async** existante (user `replicator`, `application_name=dc2-uat`)
- Extension `repmgr 5.3`, rôle/base `repmgr`, nœuds déjà enregistrés dans `repmgr.nodes`

Le `dnf install -y edb-as12-repmgr --disablerepo="*" --enablerepo="edb-local"` avait **restauré le fichier d’exemple** `/etc/repmgr/12/repmgr.conf` (paramètres obligatoires commentés). `repmgr cluster show` échouait (`node_id` / `conninfo` / `data_directory` absents).

Objectif : rétablir une config opérationnelle et prouver un switchover manuel.

---

## 2. Topologie

| node_id | node_name | IP | Hostname OS constaté | Rôle **avant** test |
|---|---|---|---|---|
| 1 | `dc1-uat` | `172.16.34.20` | `mosipdbuat01` | primary |
| 2 | `dc2-uat` | `172.17.34.20` | (DC2) | standby |

Après un switchover **sans** `--dry-run`, les rôles sont **inversés** tant qu’un switchover inverse n’a pas été fait :

- primary = nœud promu (dc2-uat si la commande a été lancée depuis dc2)
- standby = ancien primary

Vérification :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf cluster show
```

---

## 3. Travaux réalisés

### 3.1 Paquet

```bash
dnf install -y edb-as12-repmgr --disablerepo="*" --enablerepo="edb-local"
```

`repmgrd` **non** activé (2 nœuds, pas de witness → risque de split-brain).

### 3.2 `repmgr.conf`

Fichier `/etc/repmgr/12/repmgr.conf` réécrit sur les deux nœuds (chemin stocké dans `repmgr.nodes.config_file`) :

- `node_id` / `node_name` = `dc1-uat` / `dc2-uat` (pas le hostname OS)
- `data_directory` / `config_directory` = `/data/mosip/edb/as12/data`
- `pg_bindir` / `repmgr_bindir` = `/usr/edb/as12/bin`
- `failover=manual`
- `service_*_command` via `sudo systemctl {start|stop|restart|reload} edb-as-12`
- **`port=5432` dans `conninfo`** (le profil `enterprisedb` exporte `PGPORT=5444` ; sans port explicite, SSH/repmgr tentait 5444)

### 3.3 Métadonnées

`repmgr.nodes.conninfo` mis à jour avec `port=5432` pour les deux nœuds.

### 3.4 Authentification

- `pg_hba.conf` (dc2) : `host replication repmgr 172.16.34.20/32 scram-sha-256` (+ ligne `repmgr`/`repmgr`)
- `/var/lib/edb/.pgpass` : lignes `repmgr` **et** `replication` pour `172.16.34.20` et `172.17.34.20` port 5432 (mode `0600`)

### 3.5 Prérequis déjà présents (non modifiés)

- SSH `enterprisedb` bidirectionnel : OK
- `sudo -n systemctl status edb-as-12` : OK sur les deux nœuds
- WAL : `wal_level=logical`, `wal_log_hints=on`, `shared_preload_libraries` contient déjà `repmgr`

**Pas de `standby clone`** : replica existant, clone aurait écrasé la data dir.

---

## 4. Tests

| Test | Résultat |
|---|---|
| `repmgr cluster show` | 2 nœuds `running`, même timeline |
| `repmgr node check` (dc1) | OK — 1 standby, 1 slot physique actif |
| `repmgr node check` (dc2) | OK — standby, lag **0 s**, attaché à dc1-uat |
| `standby switchover --dry-run` (sur dc2) | `prerequisites for executing STANDBY SWITCHOVER are met` |
| `standby switchover` **sans** `--dry-run` | **OK** (test réel) |

Commande utilisée (sur le standby à promouvoir) :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby switchover
```

Comportement observé / attendu :

1. Contrôles SSH, lag, connexion replication, archives
2. Arrêt propre du primary : `sudo systemctl stop edb-as-12`
3. Promote du standby (`pg_promote`)
4. Réintégration de l’ancien primary en standby

Le primary **n’a pas** été arrêté manuellement avant la commande.

---

## 5. Incidents rencontrés et corrections

| Symptôme | Cause | Correction |
|---|---|---|
| `required parameter was not found` | Fichier d’exemple après `dnf install` | Réécriture de `repmgr.conf` |
| `Connection refused` port **5444** | `PGPORT=5444` + `conninfo` sans port | `port=5432` dans le fichier **et** dans `repmgr.nodes` |
| `aucune entrée pg_hba` replication depuis `172.16.34.20` user `repmgr` | HBA du standby incomplet pour le switchover | Ligne `host replication repmgr 172.16.34.20/32 scram-sha-256` + reload |
| `fe_sendauth: no password supplied` | `.pgpass` sans database `replication` | Ajout des lignes `*:5432:replication:repmgr:` |

---

## 6. Points d’attention

- **Applications MOSIP** : repmgr ne bascule pas les clients. Les écritures vont sur le **nouveau** primary (`172.17.34.20:5432` après switchover depuis dc2). Sans VIP/PgBouncer, il faut repointer les apps.
- Réplication **async** : switchover propre = lag 0 au moment du test ; un crash primary peut perdre des transactions non rejouées.
- Ne pas activer `repmgrd` sans nœud witness / 3e nœud.
- Home `enterprisedb` = `/var/lib/edb` (pas `/home/enterprisedb`).

---

## 7. Rollback

Retour à la topologie initiale : même commande **sur le standby actuel** (l’ancien primary), d’abord `--dry-run` :

```bash
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby switchover --dry-run
sudo -iu enterprisedb /usr/edb/as12/bin/repmgr -f /etc/repmgr/12/repmgr.conf standby switchover
```

---

## 8. Livrables

- Runbook : [`docs/repmgr-epas12.md`](repmgr-epas12.md)
- Le présent CR

---

## 9. Décision / clôture

Intervention **clôturée OK**. Cluster gérable par **switchover manuel** repmgr. Bascule applicative et VIP hors de cette CR.

---

# Addendum — Détachement de DC2 (25 août 2026)

| Champ | Valeur |
|---|---|
| Objet | Rendre DC2 indépendant du cluster repmgr |
| Nœud détaché | `dc2-uat` — `172.17.34.20` (node_id 2) |
| Nœud conservé | `dc1-uat` — `172.16.34.20` (primary, node_id 1) |
| Statut | **OK** — indépendance vérifiée |

## A1. Situation de départ

Après les switchovers de validation, le cluster était revenu en **timeline 3** avec DC1 primary et DC2 standby, réplication streaming async, lag nul.

## A2. Opérations réalisées

| Étape | Nœud | Action |
|---|---|---|
| 1 | DC1 | `repmgr standby unregister --node-id=2` |
| 2 | DC2 | `SELECT pg_promote(true, 60)` — sortie du mode recovery |
| 3 | DC2 | `ALTER SYSTEM RESET primary_conninfo`, `repmgr.conf` renommé en `.detached` |
| 4 | DC1 | Suppression du slot physique `dc2_slot` |
| 5 | DC1 | Retrait des règles `pg_hba.conf` autorisant `172.17.34.20` |

`repmgr.nodes` ne contient plus que `dc1-uat`.

## A3. Vérification de l'indépendance

| Contrôle | DC1 | DC2 |
|---|---|---|
| `pg_is_in_recovery()` | `f` | `f` |
| `pg_stat_replication` | 0 walsender | — |
| `pg_stat_wal_receiver` | — | 0 receiver |
| `standby.signal` | absent | absent |
| `timeline_id` | **3** | **4** |
| `repmgr.nodes` | `dc1-uat` seul | retiré |

Les timelines divergentes constituent la preuve la plus solide : les deux historiques de transactions sont inconciliables, aucune réplication ne peut reprendre accidentellement.

## A4. Constats annexes relevés pendant l'intervention

**Slots logiques inactifs sur DC1 — à traiter.** Sept slots logiques sans consommateur retenaient environ **119 Go** de WAL, dont **100 Go** pour `streammaster` :

| Slot | WAL retenu | Nature probable |
|---|---|---|
| `streammaster` | 100 Go | CDC MOSIP master data |
| `streamschtsp` | 4,6 Go | CDC MOSIP |
| `streamaudit` | 4,5 Go | CDC MOSIP audit |
| `streamregprc` | 4,5 Go | CDC MOSIP registration processor |
| `streamauth` | 4,5 Go | CDC MOSIP auth |
| `test_failover_01` / `02` | 480 Mo chacun | résidus de tests |

Sous EPAS 12, `max_slot_wal_keep_size` n'existe pas : cette rétention n'est pas bornée et le `pg_wal` peut saturer jusqu'à l'arrêt de l'instance. Le `catalog_xmin` figé bloque également le `VACUUM`, avec un risque de bloat puis de wraparound.

Ces slots ne doivent **pas** être supprimés sans validation applicative : les détruire imposerait un re-snapshot complet des tables CDC. Les deux slots `test_failover_*` semblent en revanche être des artefacts sans consommateur légitime.

**Archives WAL sur DC2.** 4,8 Go pour 155 fichiers, sur un système de fichiers de 800 Go occupé à 26 %. Aucune urgence, mais plus aucun consommateur : prévoir une rétention ou couper l'archivage selon l'usage retenu pour DC2.

## A5. Conséquences

- **L'UAT n'a plus de standby** : plus de switchover possible, aucune reprise en cas de perte de DC1.
- DC2 contient une copie complète des bases MOSIP et accepte les écritures. Toute application encore pointée sur `172.17.34.20` y écrira sans erreur, avec perte définitive de ces données pour le cluster réel.
- Réintégration éventuelle de DC2 : `standby clone` complet depuis DC1, soit une recopie intégrale.

## A6. Référence

Procédure détaillée : section 13 du runbook [`docs/repmgr-epas12.md`](repmgr-epas12.md).
