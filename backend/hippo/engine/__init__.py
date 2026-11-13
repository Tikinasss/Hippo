"""Moteur de calcul d'impact carbone du parcours (déterministe, testé, sans LLM)."""
from .calcul import Calculateur, ConflitAlternatives, Fourchette
from .repository import DonneesInvalides, Referentiel, charger, referentiel

__all__ = ["Calculateur", "ConflitAlternatives", "Fourchette", "DonneesInvalides", "Referentiel", "charger", "referentiel"]
