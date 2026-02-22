"""OpenAI configuration and AI call logging models.

This module contains models for managing OpenAI API configuration,
tracking AI API calls with their costs, and configurable prompts.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from .base import db


class OpenAIConfig(db.Model):
    """Configuration OpenAI globale pour l'application.
    
    Cette configuration est gérée par l'administrateur et utilisée
    par défaut pour tous les utilisateurs qui n'ont pas leur propre clé.
    """

    __tablename__ = "openai_config"

    id = db.Column(db.Integer, primary_key=True)
    api_key_encrypted = db.Column(db.Text, nullable=True)
    base_url = db.Column(db.String(500), nullable=True, default="https://api.openai.com/v1")
    default_model = db.Column(db.String(100), nullable=True, default="gpt-4o-mini")
    image_model = db.Column(db.String(100), nullable=True, default="dall-e-2")
    source_name = db.Column(db.String(100), nullable=True, default="OpenAI")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    monthly_budget = db.Column(db.Numeric(10, 2), nullable=True)  # Budget mensuel en USD
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def set_api_key(self, api_key: str) -> None:
        """Chiffre et stocke la clé API OpenAI.
        
        Utilise Fernet pour le chiffrement symétrique.
        La clé de chiffrement doit être définie dans la configuration de l'application.
        """
        if not api_key:
            self.api_key_encrypted = None
            return
        
        from cryptography.fernet import Fernet
        from flask import current_app
        
        key = current_app.config.get("SMTP_ENCRYPTION_KEY")  # Réutilise la même clé de chiffrement
        if not key:
            current_app.logger.warning(
                "SMTP_ENCRYPTION_KEY non définie. La clé API ne peut pas être chiffrée."
            )
            return
        
        if isinstance(key, str):
            key = key.encode()
        
        f = Fernet(key)
        self.api_key_encrypted = f.encrypt(api_key.encode()).decode()

    def get_api_key(self) -> str | None:
        """Déchiffre et retourne la clé API OpenAI."""
        if not self.api_key_encrypted:
            return None
        
        from cryptography.fernet import Fernet
        from flask import current_app
        
        key = current_app.config.get("SMTP_ENCRYPTION_KEY")
        if not key:
            return None
        
        if isinstance(key, str):
            key = key.encode()
        
        try:
            f = Fernet(key)
            return f.decrypt(self.api_key_encrypted.encode()).decode()
        except Exception:
            return None

    @staticmethod
    def get_active() -> "OpenAIConfig | None":
        """Retourne la configuration OpenAI active."""
        return OpenAIConfig.query.filter_by(is_active=True).first()

    @staticmethod
    def get_or_create() -> "OpenAIConfig":
        """Retourne la configuration existante ou en crée une nouvelle."""
        config = OpenAIConfig.query.first()
        if not config:
            config = OpenAIConfig()
            db.session.add(config)
            db.session.commit()
        return config

    def to_dict(self, include_key_status: bool = False) -> dict:
        """Retourne un dictionnaire représentant la configuration."""
        data = {
            "id": self.id,
            "base_url": self.base_url,
            "default_model": self.default_model,
            "image_model": self.image_model,
            "source_name": self.source_name,
            "is_active": self.is_active,
            "monthly_budget": float(self.monthly_budget) if self.monthly_budget else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_key_status:
            data["has_api_key"] = bool(self.api_key_encrypted)
        return data


class AICallLog(db.Model):
    """Log des appels à l'API OpenAI.
    
    Enregistre chaque appel IA avec les détails de la requête,
    la réponse, le coût estimé et l'utilisateur concerné.
    """

    __tablename__ = "ai_call_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    
    # Type d'appel (enrichment, pairing, bottle_detection, etc.)
    call_type = db.Column(db.String(50), nullable=False, index=True)
    
    # Modèle utilisé
    model = db.Column(db.String(100), nullable=False)
    
    # Source de la clé API utilisée (global, user)
    api_key_source = db.Column(db.String(20), nullable=False, default="global")
    
    # Requête (prompts)
    system_prompt = db.Column(db.Text, nullable=True)
    user_prompt = db.Column(db.Text, nullable=True)
    
    # Réponse
    response_text = db.Column(db.Text, nullable=True)
    response_status = db.Column(db.String(20), nullable=False, default="success")  # success, error
    error_message = db.Column(db.Text, nullable=True)
    
    # Tokens et coût
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    total_tokens = db.Column(db.Integer, nullable=True)
    estimated_cost_usd = db.Column(db.Numeric(10, 6), nullable=True)  # Coût en USD
    
    # Métadonnées
    duration_ms = db.Column(db.Integer, nullable=True)  # Durée de l'appel en millisecondes
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Contexte additionnel (JSON)
    context = db.Column(db.JSON, nullable=True)  # Ex: wine_id, dish, etc.

    user = db.relationship("User", backref=db.backref("ai_call_logs", lazy="dynamic"))

    # Prix par 1000 tokens (approximatifs, à mettre à jour selon les tarifs OpenAI)
    # Ces valeurs sont des estimations et peuvent être configurées
    TOKEN_PRICES = {
        "gpt-5.2": {"input": 0.005, "output": 0.02},
        "gpt-5.1": {"input": 0.004, "output": 0.016},
        "gpt-5": {"input": 0.003, "output": 0.012},
        "gpt-5-mini": {"input": 0.0003, "output": 0.0012},
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        "dall-e-2": {"per_image": 0.02},
        "dall-e-3": {"per_image": 0.04},
    }

    @staticmethod
    def log_call(
        user_id: int,
        call_type: str,
        model: str,
        api_key_source: str = "global",
        system_prompt: str = None,
        user_prompt: str = None,
        response_text: str = None,
        response_status: str = "success",
        error_message: str = None,
        input_tokens: int = None,
        output_tokens: int = None,
        duration_ms: int = None,
        context: dict = None,
    ) -> "AICallLog":
        """Crée un log d'appel IA."""
        total_tokens = None
        if input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        
        # Calculer le coût estimé
        estimated_cost = AICallLog._calculate_cost(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        
        log = AICallLog(
            user_id=user_id,
            call_type=call_type,
            model=model,
            api_key_source=api_key_source,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            response_status=response_status,
            error_message=error_message,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost,
            duration_ms=duration_ms,
            context=context,
        )
        db.session.add(log)
        return log

    @staticmethod
    def _calculate_cost(
        model: str,
        input_tokens: int = None,
        output_tokens: int = None,
    ) -> Optional[Decimal]:
        """Calcule le coût estimé d'un appel."""
        if not model:
            return None
        
        # Normaliser le nom du modèle
        model_lower = model.lower()
        
        # Trouver les prix correspondants
        prices = None
        for model_key, model_prices in AICallLog.TOKEN_PRICES.items():
            if model_key in model_lower:
                prices = model_prices
                break
        
        if not prices:
            return None
        
        # Pour les modèles d'image
        if "per_image" in prices:
            return Decimal(str(prices["per_image"]))
        
        # Pour les modèles de texte
        if input_tokens is None or output_tokens is None:
            return None
        
        input_cost = (input_tokens / 1000) * prices.get("input", 0)
        output_cost = (output_tokens / 1000) * prices.get("output", 0)
        
        return Decimal(str(round(input_cost + output_cost, 6)))

    @staticmethod
    def get_user_monthly_cost(user_id: int, year: int = None, month: int = None) -> Decimal:
        """Calcule le coût total des appels IA d'un utilisateur pour un mois donné."""
        from sqlalchemy import func, extract
        
        if year is None or month is None:
            now = datetime.utcnow()
            year = now.year
            month = now.month
        
        result = db.session.query(
            func.sum(AICallLog.estimated_cost_usd)
        ).filter(
            AICallLog.user_id == user_id,
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        ).scalar()
        
        return Decimal(str(result)) if result else Decimal("0")

    @staticmethod
    def get_global_monthly_cost(year: int = None, month: int = None) -> Decimal:
        """Calcule le coût total de tous les appels IA pour un mois donné."""
        from sqlalchemy import func, extract
        
        if year is None or month is None:
            now = datetime.utcnow()
            year = now.year
            month = now.month
        
        result = db.session.query(
            func.sum(AICallLog.estimated_cost_usd)
        ).filter(
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        ).scalar()
        
        return Decimal(str(result)) if result else Decimal("0")

    @staticmethod
    def get_monthly_stats(year: int = None, month: int = None) -> dict:
        """Retourne les statistiques mensuelles des appels IA."""
        from sqlalchemy import func, extract
        
        if year is None or month is None:
            now = datetime.utcnow()
            year = now.year
            month = now.month
        
        # Statistiques globales
        stats = db.session.query(
            func.count(AICallLog.id).label("total_calls"),
            func.sum(AICallLog.input_tokens).label("total_input_tokens"),
            func.sum(AICallLog.output_tokens).label("total_output_tokens"),
            func.sum(AICallLog.estimated_cost_usd).label("total_cost"),
        ).filter(
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        ).first()
        
        # Statistiques par type d'appel
        by_type = db.session.query(
            AICallLog.call_type,
            func.count(AICallLog.id).label("count"),
            func.sum(AICallLog.estimated_cost_usd).label("cost"),
        ).filter(
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        ).group_by(AICallLog.call_type).all()
        
        # Statistiques par utilisateur
        by_user = db.session.query(
            AICallLog.user_id,
            func.count(AICallLog.id).label("count"),
            func.sum(AICallLog.estimated_cost_usd).label("cost"),
        ).filter(
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        ).group_by(AICallLog.user_id).order_by(
            func.sum(AICallLog.estimated_cost_usd).desc()
        ).limit(10).all()
        
        return {
            "year": year,
            "month": month,
            "total_calls": stats.total_calls or 0,
            "total_input_tokens": stats.total_input_tokens or 0,
            "total_output_tokens": stats.total_output_tokens or 0,
            "total_cost": float(stats.total_cost) if stats.total_cost else 0,
            "by_type": [
                {"type": t.call_type, "count": t.count, "cost": float(t.cost) if t.cost else 0}
                for t in by_type
            ],
            "by_user": [
                {"user_id": u.user_id, "count": u.count, "cost": float(u.cost) if u.cost else 0}
                for u in by_user
            ],
        }

    def to_dict(self, include_prompts: bool = False) -> dict:
        """Retourne un dictionnaire représentant le log."""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "call_type": self.call_type,
            "model": self.model,
            "api_key_source": self.api_key_source,
            "response_status": self.response_status,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": float(self.estimated_cost_usd) if self.estimated_cost_usd else None,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "context": self.context,
        }
        if include_prompts:
            data["system_prompt"] = self.system_prompt
            data["user_prompt"] = self.user_prompt
            data["response_text"] = self.response_text
            data["error_message"] = self.error_message
        return data


class OpenAIPrompt(db.Model):
    """Prompts configurables pour les différentes fonctionnalités IA.
    
    Permet aux administrateurs de personnaliser les prompts système et utilisateur
    utilisés par les services d'IA (enrichissement, accords mets-vins, détection de bouteilles).
    """

    __tablename__ = "openai_prompt"

    id = db.Column(db.Integer, primary_key=True)
    
    # Identifiant unique du prompt (wine_enrichment, wine_pairing, bottle_detection, label_generation)
    prompt_key = db.Column(db.String(50), nullable=False, unique=True, index=True)
    
    # Nom affiché dans l'interface d'administration
    display_name = db.Column(db.String(100), nullable=False)
    
    # Description du prompt pour l'administrateur
    description = db.Column(db.Text, nullable=True)
    
    # Prompt système (instructions générales pour l'IA)
    system_prompt = db.Column(db.Text, nullable=False)
    
    # Prompt utilisateur (template avec variables)
    user_prompt = db.Column(db.Text, nullable=False)
    
    # Variables disponibles pour ce prompt (JSON)
    # Ex: ["wine_name", "year", "region", "grape", "description"]
    available_variables = db.Column(db.JSON, nullable=True)
    
    # Schéma JSON attendu en réponse (optionnel)
    response_schema = db.Column(db.JSON, nullable=True)
    
    # Paramètres supplémentaires (max_tokens, temperature, etc.)
    parameters = db.Column(db.JSON, nullable=True)
    
    # État du prompt
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Métadonnées
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Prompts par défaut pour chaque fonctionnalité
    DEFAULT_PROMPTS = {
        "wine_enrichment": {
            "display_name": "Enrichissement de fiche vin",
            "description": "Prompt utilisé pour enrichir les fiches de vins avec des informations complémentaires (histoire, accords, garde, etc.)",
            "system_prompt": """Tu es un assistant sommelier chargé d'enrichir la fiche d'un alcool.
Tu réponds exclusivement en français et fournis des informations fiables,
concis, adaptées à un public de passionnés.""",
            "user_prompt": """Voici les informations connues sur l'alcool :
{wine_details}

Complète avec 4 à 6 éclairages distincts (estimation du prix actuel, histoire du domaine, profil aromatique, accords mets et vins, potentiel de garde, etc.).
Chaque éclairage doit tenir en 2 à 4 phrases maximum.
Structure ta réponse au format JSON selon le schéma demandé, sans texte additionnel.""",
            "available_variables": ["wine_details"],
            "response_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "insights": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 6,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "category": {"type": "string"},
                                "title": {"type": "string"},
                                "content": {"type": "string"},
                                "source": {"type": "string"},
                                "source_url": {"type": ["string", "null"]},
                                "weight": {"type": "integer"},
                            },
                            "required": ["category", "title", "content", "source", "source_url", "weight"],
                        },
                    }
                },
                "required": ["insights"],
            },
            "parameters": {
                "max_output_tokens": 1800,
                "enable_web_search": True,
                "web_search_context_size": "high",
            },
        },
        "wine_pairing": {
            "display_name": "Accords mets-vins",
            "description": "Prompt utilisé pour recommander des vins en fonction d'un plat",
            "system_prompt": """Tu es un sommelier expert spécialisé dans les accords mets-vins.
Tu dois analyser la liste des vins disponibles et recommander les meilleurs accords pour le plat indiqué.

Tu dois fournir DEUX types de recommandations :
1. "priority_wines" : Les vins à consommer EN PRIORITÉ (ceux qui sont dans leur fenêtre de dégustation optimale ou qui doivent être bus rapidement selon leur garde)
2. "best_wines" : Les MEILLEURS vins pour ce plat, peu importe s'ils sont à consommer maintenant ou non

Pour chaque vin, tu dois :
- Évaluer l'accord avec le plat (score de 1 à 10)
- Expliquer pourquoi ce vin convient
- Indiquer si le vin est à consommer en priorité (basé sur l'année et la garde recommandée)
- Donner des informations sur la garde si disponibles

Réponds UNIQUEMENT en JSON selon le schéma demandé.""",
            "user_prompt": """Voici le plat prévu : {dish}

Année actuelle : {current_year}

Voici la liste des vins disponibles en JSON :
{wines_json}

Analyse ces vins et recommande :
1. 1 à 2 vins à consommer EN PRIORITÉ (qui sont dans leur fenêtre de dégustation ou doivent être bus bientôt)
2. 1 à 2 MEILLEURS vins pour ce plat (peu importe la garde)

IMPORTANT : Les vins recommandés dans "priority_wines" et "best_wines" doivent être DIFFÉRENTS.
Ne recommande pas le même vin dans les deux catégories.

Pour déterminer si un vin est à consommer en priorité, considère :
- L'année du millésime
- La garde recommandée (garde_min, garde_max dans extra_attributes)
- Le type de vin (les vins blancs et rosés se conservent généralement moins longtemps)

Fournis une explication générale sur les accords recommandés.""",
            "available_variables": ["dish", "current_year", "wines_json"],
            "response_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "priority_wines": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "wine_id": {"type": "integer"},
                                "reason": {"type": "string"},
                                "score": {"type": "integer"},
                                "garde_info": {"type": "string"},
                            },
                            "required": ["wine_id", "reason", "score", "garde_info"],
                        },
                    },
                    "best_wines": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "wine_id": {"type": "integer"},
                                "reason": {"type": "string"},
                                "score": {"type": "integer"},
                                "garde_info": {"type": "string"},
                            },
                            "required": ["wine_id", "reason", "score", "garde_info"],
                        },
                    },
                    "explanation": {"type": "string"},
                },
                "required": ["priority_wines", "best_wines", "explanation"],
            },
            "parameters": {"max_output_tokens": 1500},
        },
        "bottle_detection": {
            "display_name": "Détection de bouteilles",
            "description": "Prompt utilisé pour analyser une image et identifier les bouteilles d'alcool",
            "system_prompt": """Tu es un expert sommelier et caviste. Tu analyses des photos de bouteilles d'alcool (vins, spiritueux, bières, etc.).

Pour chaque bouteille visible sur l'image, tu dois identifier avec PRÉCISION:
- Le nom COMPLET du produit incluant la marque ET la variante/gamme/couleur
  Exemples: "Chimay Bleue", "Château Margaux 2015", "Rhum Diplomatico Reserva Exclusiva", "Whisky Lagavulin 16 ans", "Leffe Blonde"
- Le type d'alcool PRÉCIS (champ alcohol_type):
  Pour les bières: "Bière blonde", "Bière brune", "Bière trappiste", "Bière blanche", "IPA", etc.
  Pour les vins: "Vin rouge", "Vin blanc", "Vin rosé", "Champagne", "Crémant", etc.
  Pour les spiritueux: "Rhum ambré", "Whisky single malt", "Vodka", "Gin", "Cognac", etc.
- Le millésime/année si visible sur l'étiquette
- La région d'origine ou le pays
- Le cépage pour les vins, ou le style/type pour les bières
- La contenance en mL (750, 330, 500, 1000, etc.)
- Une brève description des caractéristiques
{categories_section}

RÈGLES IMPORTANTES:
1. Le nom doit être COMPLET et PRÉCIS - inclure la couleur/variante (ex: "Chimay Bleue" pas juste "Chimay")
2. Pour les bières, TOUJOURS préciser la couleur ou le style dans le nom ET le type
3. Pour les vins, inclure le domaine/château ET l'appellation si visible
4. Si plusieurs bouteilles identiques, indiquer la quantité exacte
5. Utiliser 0 pour les nombres inconnus, chaîne vide pour les textes inconnus
6. Score de confiance basé sur la lisibilité de l'étiquette
7. Pour alcohol_type, UTILISE EN PRIORITÉ les catégories disponibles listées ci-dessus

Réponds UNIQUEMENT en JSON valide selon le schéma demandé.""",
            "user_prompt": """Analyse cette image et identifie TOUTES les bouteilles d'alcool visibles.

Pour chaque bouteille:
1. Lis ATTENTIVEMENT l'étiquette pour extraire le nom COMPLET (marque + variante/couleur)
2. Identifie le type PRÉCIS d'alcool (pas juste "bière" mais "bière trappiste brune")
3. Note toutes les informations visibles
4. Regroupe les bouteilles identiques avec leur quantité""",
            "available_variables": ["categories_section"],
            "response_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "bottles": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string", "description": "Nom du produit (domaine, château, marque)"},
                                "quantity": {"type": "integer", "description": "Nombre de bouteilles identiques"},
                                "year": {"type": "integer", "description": "Millésime ou année de production (0 si inconnu)"},
                                "region": {"type": "string", "description": "Région d'origine (vide si inconnue)"},
                                "grape": {"type": "string", "description": "Cépage principal (vide si inconnu)"},
                                "volume_ml": {"type": "integer", "description": "Contenance en millilitres (0 si inconnue)"},
                                "description": {"type": "string", "description": "Brève description du produit"},
                                "alcohol_type": {"type": "string", "description": "Type d'alcool (Vin rouge, Champagne, Rhum, etc.)"},
                                "confidence": {"type": "number", "description": "Score de confiance de la détection (0-1)"},
                            },
                            "required": ["name", "quantity", "year", "region", "grape", "volume_ml", "description", "alcohol_type", "confidence"],
                        },
                    },
                    "total_bottles": {"type": "integer", "description": "Nombre total de bouteilles détectées"},
                },
                "required": ["bottles", "total_bottles"],
            },
            "parameters": {"max_output_tokens": 2000},
        },
        "label_generation": {
            "display_name": "Génération d'étiquette",
            "description": "Prompt utilisé pour générer une image d'étiquette stylisée pour un vin",
            "system_prompt": "",
            "user_prompt": """Design a flat, poster-like illustration of a refined French wine label.
Use elegant typography, subtle texture, and muted natural colors.
Show only the label on a neutral background, no bottle photo.
Incorporate the following information in French: {wine_details}. Requête de référence: {query}.""",
            "available_variables": ["wine_details", "query"],
            "response_schema": None,
            "parameters": {"size": "1024x1024"},
        },
    }

    @classmethod
    def get_prompt(cls, prompt_key: str) -> Optional["OpenAIPrompt"]:
        """Récupère un prompt par sa clé.
        
        Si le prompt n'existe pas en base, retourne None.
        Utilisez get_or_create_default pour obtenir le prompt par défaut.
        """
        return cls.query.filter_by(prompt_key=prompt_key, is_active=True).first()

    @classmethod
    def get_or_create_default(cls, prompt_key: str) -> "OpenAIPrompt":
        """Récupère un prompt ou crée le prompt par défaut s'il n'existe pas.
        
        Args:
            prompt_key: Clé du prompt (wine_enrichment, wine_pairing, bottle_detection, label_generation)
            
        Returns:
            Instance de OpenAIPrompt
        """
        prompt = cls.query.filter_by(prompt_key=prompt_key).first()
        
        if prompt:
            return prompt
        
        # Créer le prompt par défaut
        if prompt_key not in cls.DEFAULT_PROMPTS:
            raise ValueError(f"Prompt inconnu: {prompt_key}")
        
        defaults = cls.DEFAULT_PROMPTS[prompt_key]
        prompt = cls(
            prompt_key=prompt_key,
            display_name=defaults["display_name"],
            description=defaults["description"],
            system_prompt=defaults["system_prompt"],
            user_prompt=defaults["user_prompt"],
            available_variables=defaults.get("available_variables"),
            response_schema=defaults.get("response_schema"),
            parameters=defaults.get("parameters"),
            is_active=True,
        )
        db.session.add(prompt)
        db.session.commit()
        
        return prompt

    @classmethod
    def initialize_defaults(cls) -> None:
        """Initialise tous les prompts par défaut s'ils n'existent pas."""
        for prompt_key in cls.DEFAULT_PROMPTS:
            cls.get_or_create_default(prompt_key)

    @classmethod
    def reset_to_default(cls, prompt_key: str) -> "OpenAIPrompt":
        """Réinitialise un prompt à sa valeur par défaut.
        
        Args:
            prompt_key: Clé du prompt à réinitialiser
            
        Returns:
            Instance de OpenAIPrompt réinitialisée
        """
        if prompt_key not in cls.DEFAULT_PROMPTS:
            raise ValueError(f"Prompt inconnu: {prompt_key}")
        
        prompt = cls.query.filter_by(prompt_key=prompt_key).first()
        defaults = cls.DEFAULT_PROMPTS[prompt_key]
        
        if prompt:
            prompt.display_name = defaults["display_name"]
            prompt.description = defaults["description"]
            prompt.system_prompt = defaults["system_prompt"]
            prompt.user_prompt = defaults["user_prompt"]
            prompt.available_variables = defaults.get("available_variables")
            prompt.response_schema = defaults.get("response_schema")
            prompt.parameters = defaults.get("parameters")
            prompt.is_active = True
        else:
            prompt = cls(
                prompt_key=prompt_key,
                display_name=defaults["display_name"],
                description=defaults["description"],
                system_prompt=defaults["system_prompt"],
                user_prompt=defaults["user_prompt"],
                available_variables=defaults.get("available_variables"),
                response_schema=defaults.get("response_schema"),
                parameters=defaults.get("parameters"),
                is_active=True,
            )
            db.session.add(prompt)
        
        db.session.commit()
        return prompt

    def render_system_prompt(self, **kwargs) -> str:
        """Rend le prompt système avec les variables fournies.
        
        Args:
            **kwargs: Variables à substituer dans le prompt
            
        Returns:
            Prompt système avec les variables substituées
        """
        try:
            return self.system_prompt.format(**kwargs)
        except KeyError as e:
            # Si une variable manque, retourner le prompt tel quel
            return self.system_prompt

    def render_user_prompt(self, **kwargs) -> str:
        """Rend le prompt utilisateur avec les variables fournies.
        
        Args:
            **kwargs: Variables à substituer dans le prompt
            
        Returns:
            Prompt utilisateur avec les variables substituées
        """
        try:
            return self.user_prompt.format(**kwargs)
        except KeyError as e:
            # Si une variable manque, retourner le prompt tel quel
            return self.user_prompt

    def get_parameter(self, key: str, default: Any = None) -> Any:
        """Récupère un paramètre du prompt.
        
        Args:
            key: Clé du paramètre
            default: Valeur par défaut si le paramètre n'existe pas
            
        Returns:
            Valeur du paramètre ou la valeur par défaut
        """
        if not self.parameters:
            return default
        return self.parameters.get(key, default)

    def to_dict(self, include_schema: bool = False) -> dict:
        """Retourne un dictionnaire représentant le prompt.
        
        Args:
            include_schema: Inclure le schéma de réponse JSON
            
        Returns:
            Dictionnaire avec les données du prompt
        """
        data = {
            "id": self.id,
            "prompt_key": self.prompt_key,
            "display_name": self.display_name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "available_variables": self.available_variables,
            "parameters": self.parameters,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_schema:
            data["response_schema"] = self.response_schema
        return data
