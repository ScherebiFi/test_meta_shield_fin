# Meta ShieldFin — MVP de détection de fraude

Meta ShieldFin est une démonstration de détection de transactions avec FastAPI,
une file de travail asynchrone en mémoire, Scikit-Learn et un tableau de bord
SOC en streaming WebSocket.

## Démarrage

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Créez un fichier `.env` à la racine pour activer l'arbitrage cloud :

```dotenv
GROQ_API_KEY=votre_cle_groq
```

Sans clé Groq, l'application démarre quand même et active la politique locale
de secours lorsque l'analyse rencontre un cas ambigu.

Lancez l'API et le dashboard servi sur la même origine :

```bash
uvicorn main:app --reload
```

Ouvrez ensuite <http://127.0.0.1:8000/>. Pour démarrer les tests unitaires :

```bash
python -m unittest discover -s tests
```

## Webhook de paiement

`POST /api/webhook/payment-notification` valide le corps JSON, place la
transaction dans la file et attend son traitement avant de répondre. Un succès
renvoie la décision d'analyse. Une file saturée renvoie `503` avec
`Retry-After`; les erreurs de validation renvoient `422`.

```json
{
  "transaction_id": "tx_demo_001",
  "amount": 125.5,
  "velocity": 2,
  "country_risk": 0
}
```

`transaction_id` et `timestamp` sont générés s'ils sont omis. Les autres champs
sont strictement validés; les champs supplémentaires sont refusés.

L'endpoint `/api/health` indique la taille de la file, l'état du mode local et
la disponibilité cloud. Le bouton de simulation Fail-Safe bascule le système
en mode local et diffuse le nouvel état aux dashboards connectés.

## Limites du MVP

- La file est en mémoire : elle limite la saturation et applique une
  contre-pression, mais ne survit pas à un redémarrage ou à une panne du
  processus. Les transactions qui reçoivent un succès ont été traitées, mais
  ce n'est pas une file durable.
- Le webhook est public pour faciliter l'intégration de démonstration. Avant
  toute exposition réelle, ajoutez une authentification/signature vérifiée
  fournie par la passerelle, ainsi que des limites de débit.
- Le SHA-256 affiché est une empreinte de détection de modification, pas du
  chiffrement ni une preuve d'origine à lui seul; il ne masque donc aucune
  donnée. Les champs sélectionnés pour l'analyse cloud sont ceux du prompt
  AML/KYC, mais leur transfert reste soumis à vos règles de confidentialité.
- L'analyse ML et le rapport généré ne remplacent ni un contrôle de paiement,
  ni une revue de conformité, ni un modèle validé sur des données de production.
- Le moteur est préchauffé au démarrage. La latence affichée mesure le passage
  dans Isolation Forest (médiane à chaud testée sous 5 ms); elle n'inclut ni la
  file, ni le hachage SHA-256, ni le temps réseau Groq.
