import numpy as np
from sklearn.ensemble import IsolationForest
import hashlib
import json
import random
from datetime import datetime, timezone
from time import perf_counter

class MLFraudDetector:
    def __init__(self):
        print("[*] Initialisation du moteur ML local (Isolation Forest)...")
        # 1. Génération d'un dataset d'entraînement initial (transactions normales)
        np.random.seed(42)
        train_data = np.column_stack((
            np.random.normal(50, 20, 1000),
            np.random.poisson(2, 1000),
            np.zeros(1000),
        ))
        
        # Entraînement du modèle non-supervisé (Isolation Forest)
        self.model = IsolationForest(
            contamination=0.05,
            n_estimators=8,
            max_samples=64,
            n_jobs=1,
            random_state=42,
        )
        self.model.fit(train_data)
        self.model.decision_function(np.array([[50.0, 2.0, 0.0]]))
        print("[+] Modèle Isolation Forest entraîné avec succès !")

    def generate_mock_transaction(self):
        """Simule l'arrivée d'une transaction en direct (normale ou attaque)."""
        is_attack = random.random() < 0.25 # 25% de chance d'injecter une anomalie
        
        if is_attack:
            tx = {
                "transaction_id": f"tx_{random.randint(10000, 99999)}",
                "amount": round(random.uniform(800.0, 5000.0), 2),
                "velocity": random.randint(15, 40),
                "country_risk": random.choice([1, 2]),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            tx = {
                "transaction_id": f"tx_{random.randint(10000, 99999)}",
                "amount": round(random.uniform(5.0, 150.0), 2),
                "velocity": random.randint(1, 3),
                "country_risk": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        return tx

    def compute_integrity_hash(self, transaction: dict) -> str:
        """
        Calcule l'empreinte SHA-256 canonique de la transaction.
        """
        tx_string = json.dumps(transaction, sort_keys=True)
        return hashlib.sha256(tx_string.encode('utf-8')).hexdigest()

    def predict(self, transaction: dict, force_local_failsafe: bool = False):
        """
        Analyse la transaction et retourne la durée mesurée du scoring local.
        Retourne le statut (SAFE, BLOCKED, GREY_ZONE).
        """
        features = np.array([[
            transaction['amount'],
            transaction['velocity'],
            transaction['country_risk'],
        ]])
        started_at = perf_counter()
        decision_score = float(self.model.decision_function(features)[0])
        latency_ms = (perf_counter() - started_at) * 1000
        raw_score = decision_score + self.model.offset_
        prediction = -1 if decision_score < 0 else 1
        integrity_hash = self.compute_integrity_hash(transaction)

        # Si le mode Fail-Safe local est activé (Panne Cloud simulée)
        if force_local_failsafe:
            if (
                prediction == -1
                or transaction['amount'] >= 500
                or transaction['velocity'] >= 8
                or transaction['country_risk'] > 0
            ):
                return {
                    "status": "BLOCKED_FAILSAFE",
                    "score": float(raw_score),
                    "action": "BLOCK",
                    "reason": "Mode Secours Actif : Seuil local durci sans passer par le Cloud.",
                    "integrity_hash": integrity_hash,
                    "latency_ms": round(latency_ms, 3),
                }
            return {
                "status": "SAFE_FAILSAFE",
                "score": float(raw_score),
                "action": "ALLOW",
                "reason": "Transaction validée par la politique ML locale (mode secours).",
                "integrity_hash": integrity_hash,
                "latency_ms": round(latency_ms, 3),
            }

        # Logique standard
        if prediction == 1 and transaction['amount'] < 500:
            return {
                "status": "SAFE",
                "score": float(raw_score),
                "action": "ALLOW",
                "reason": "Transaction validée par le moteur ML local.",
                "integrity_hash": integrity_hash,
                "latency_ms": round(latency_ms, 3),
            }
        elif prediction == -1 or transaction['amount'] > 1000:
            return {
                "status": "BLOCKED",
                "score": float(raw_score),
                "action": "BLOCK",
                "reason": "Anomalie critique détectée par Isolation Forest (Botnet/Montant suspect).",
                "integrity_hash": integrity_hash,
                "latency_ms": round(latency_ms, 3),
            }
        else:
            # Zone Grise -> À envoyer à l'IA Meta Llama via Groq
            return {
                "status": "GREY_ZONE",
                "score": float(raw_score),
                "action": "DELEGATE_TO_AI",
                "reason": "Transaction ambigüe : Analyse sémantique requise par l'agent Meta Llama.",
                "integrity_hash": integrity_hash,
                "latency_ms": round(latency_ms, 3),
            }