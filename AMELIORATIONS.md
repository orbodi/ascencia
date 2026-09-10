# Améliorations apportées

## Version 4 — autonomie contrôlée et modèle institutionnel

- cycle autonome périodique et déclenchement immédiat par API ou par l'agent ;
- génération, campagne de confirmation, relances limitées, régénération, publication et diffusion enchaînées ;
- publication automatique conditionnée aux confirmations et à une option explicite ;
- approbation par un enseignant limitée à ses propres séances après confirmation ;
- collecte des disponibilités partielles également disponible depuis le lien reçu par e-mail ;
- export PDF en grille hebdomadaire conforme au modèle fourni, avec logo Ascencia Keyce ;
- verrou anti-concurrence pour une instance et journalisation des transitions ;
- guide spécifique pour l'autonomie et WhatsApp réel.

## Version 3 — confirmation et diffusion

- campagne de présence rattachée à chaque version de planning ;
- réponses vérifiées par lien e-mail ou commande WhatsApp ;
- publication bloquée tant que les confirmations ne sont pas complètes ;
- indisponibilités converties en contraintes pour la régénération ;
- classeur Excel versionné avec synthèse, planning complet et feuilles par groupe ;
- PDF par groupe et diffusion à une liste de destinataires WhatsApp ;
- historique des tentatives, échecs et relances ;
- interface de suivi et guide de mise en place réelle.
- prise en compte du semestre, des priorités, des prérequis pédagogiques et d’un plafond quotidien de huit heures par groupe.

## Cohérence avec le sujet du mémoire

- génération d’un brouillon hebdomadaire à partir des cours, salles, groupes, créneaux et indisponibilités ;
- contrôle des conflits d’enseignant, de groupe et de salle ;
- contrôle de la capacité des salles, de la durée du cours et du jour du créneau ;
- score heuristique destiné à équilibrer les journées et à limiter les contraintes inutiles ;
- rapport explicite des séances proposées, déjà planifiées, terminées ou impossibles à placer ;
- publication d’une version identifiée, datée et rattachée à l’administrateur ;
- archivage de la version officielle précédente pour la même semaine.

## Fiabilité et sécurité

- une proposition de report ne peut plus être appliquée avant son approbation ;
- les modifications manuelles passent par le même contrôle de conflits ;
- le système revérifie les contraintes au moment d’appliquer ou de publier ;
- les messages WhatsApp sont dédupliqués par leur identifiant ;
- le jeton technique n’est plus intégré dans le frontend ;
- le démarrage en production est refusé si les secrets de démonstration n’ont pas été remplacés.

## Agent et interface

- réponses locales rapides et factuelles pour l’état du système, le planning et les validations ;
- recours à Gemini pour les demandes conversationnelles complexes ;
- actions rapides dans le chat et indication constante de la supervision humaine ;
- nouvel écran « Génération & publication » ;
- parcours d’approbation puis d’application rendu visible ;
- données fictives clairement marquées et automatiquement placées sur la semaine courante ;
- interface responsive enrichie par une navigation illustrée et une meilleure hiérarchie visuelle.

## Vérifications effectuées

- 23 tests automatisés réussis ;
- 1 test conditionnel ignoré ;
- compilation Python réussie ;
- contrôle TypeScript réussi ;
- build de production du frontend réussi.

## Limite conservée volontairement

Le moteur actuel est heuristique et déterministe. Il ne constitue pas encore une optimisation mathématique globale. Son remplacement futur par OR-Tools est prévu par l’architecture sans remettre en cause le circuit de validation et de publication.
