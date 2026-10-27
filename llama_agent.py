import json
import os
from groq import Groq
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

class LlamaFraudAgent:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("La variable GROQ_API_KEY est absente.")
        
        # Initialisation du client Groq pour Meta Llama 3.1
        self.client = Groq(api_key=api_key, timeout=10.0, max_retries=1)
        # Modèle ultra-rapide et performant de Meta sur Groq
        self.model_name = "llama-3.1-8b-instant"
        print("[+] Agent Meta Llama (Groq) initialisé avec succès !")

    def analyze_grey_zone(self, transaction: dict, ml_score: float) -> dict:
        """
        Envoie la transaction ambigüe à Meta Llama 3.1 pour une analyse sémantique 
        profonde et la génération d'un rapport AML/KYC.
        """
        prompt = f"""
        Tu es l'agent expert en cybersécurité financière de la plateforme "Meta ShieldFin".
        Analyse la transaction suspecte suivante classée en "Zone Grise" par le moteur ML local :
        
        - ID Transaction : {transaction.get('transaction_id')}
        - Montant : {transaction.get('amount')} EUR/USD
        - Vélocité (requêtes/min) : {transaction.get('velocity')}
        - Indice de risque géographique : {transaction.get('country_risk')}
        - Score d'anomalie ML : {ml_score}
        - Timestamp : {transaction.get('timestamp')}

        Consignes strictes :
        1. Détermine la décision finale : "BLOCK" (Bloquer), "CHALLENGE_2FA" (Exiger une double authentification), ou "ALLOW" (Autoriser).
        2. Rédige un court rapport de conformité AML/KYC professionnel (en français) justifiant la décision.
        
        Réponds UNIQUEMENT sous un format JSON strict avec les clés suivantes :
        {{
          "decision": "...",
          "risk_level": "...",
          "aml_report": "..."
        }}
        """

        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "Tu es un système expert de conformité bancaire et de détection des fraudes. Tu réponds exclusivement en JSON valide."
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model=self.model_name,
            response_format={"type": "json_object"}
        )

        response_content = chat_completion.choices[0].message.content
        if not response_content:
            raise ValueError("Réponse Groq vide.")
        result = json.loads(response_content)
        if result.get("decision") not in {"BLOCK", "CHALLENGE_2FA", "ALLOW"}:
            raise ValueError("Décision Groq inconnue.")
        if not isinstance(result.get("aml_report"), str):
            raise ValueError("Rapport AML/KYC invalide.")
        return result