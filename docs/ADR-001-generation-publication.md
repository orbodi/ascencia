# ADR-001 — Génération sous contraintes et publication supervisée

**Statut :** Accepté  
**Date :** 20 août 2026  
**Décideur :** administration académique

## Contexte

Le système doit générer un emploi du temps exploitable sans présenter une réponse du modèle de langage comme une décision officielle. Les données de démonstration doivent suivre la même logique que de futures données réelles.

## Décision

Le moteur déterministe contrôle les contraintes et calcule un brouillon par score d'équilibrage. L'agent conversationnel prépare et explique ce brouillon. Seul un administrateur authentifié peut publier la version après contrôle. Chaque version conserve son rapport, son auteur et sa date.

## Options considérées

- Génération directe par le modèle de langage : écartée, car non déterministe et difficile à vérifier.
- Génération et publication immédiates : écartées, car elles suppriment le contrôle humain.
- Brouillon déterministe, explication par l'agent et publication supervisée : retenue.

## Conséquences

- Les conflits forts sont contrôlés par du code testable.
- Les décisions restent traçables et défendables dans le mémoire.
- Le moteur heuristique pourra être remplacé ultérieurement par OR-Tools sans modifier le circuit de validation et de publication.
