# Guide de démonstration

## 1. Préparation

Lancer les migrations, puis réinitialiser les données fictives :

```powershell
docker compose run --rm app python -m alembic upgrade head
docker compose run --rm app python -m scripts.seed --reset
```

Ouvrir `http://localhost:8000/backoffice` et se connecter avec le compte de démonstration configuré dans `.env`.

## 2. Montrer les données et les contraintes

Présenter brièvement les enseignants, groupes, salles, cours et créneaux. Les identités portent la mention « Démo » et les courriels utilisent le domaine réservé `example.test`.

## 3. Interroger l’agent

Dans « Assistant IA », utiliser successivement les actions rapides :

1. « Donne-moi l’état du système » ;
2. « Affiche le planning de la semaine » ;
3. « Combien de validations sont en attente ? ».

Ces trois réponses simples sont produites directement à partir de la base. Les demandes plus complexes sont confiées à Gemini si une clé est configurée.

## 4. Générer et publier

Ouvrir « Génération & publication ». La semaine suivante est proposée par défaut afin de ne pas écraser le planning de démonstration courant.

1. Cliquer sur « Générer un brouillon » ;
2. contrôler le nombre de séances proposées et non placées ;
3. ouvrir le détail de la version ;
4. cliquer sur « Publier cette version » et confirmer.

Le moteur contrôle les conflits d’enseignant, de groupe et de salle, les indisponibilités, la capacité des salles, la durée des cours et la cohérence du jour. La version publiée est enregistrée avec son auteur et sa date.

## 5. Montrer une replanification supervisée

Demander à l’agent d’enregistrer une indisponibilité fictive pour l’enseignante `Ama Mensah (Démo)` un mercredi de la semaine courante. Faire rechercher les cours impactés et proposer un autre créneau.

Dans « Validations » :

1. approuver la proposition ;
2. constater qu’elle n’est pas encore appliquée ;
3. appliquer ensuite la modification au planning.

## Limite à annoncer honnêtement

Cette version utilise un moteur heuristique sous contraintes. Elle ne doit pas être décrite comme une optimisation mathématique globale. Un solveur spécialisé pourra remplacer ce moteur sans modifier le circuit de validation et de publication.
