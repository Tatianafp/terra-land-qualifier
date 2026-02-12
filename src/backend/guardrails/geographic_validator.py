"""
Geographic validation guardrail.

This module provides fuzzy matching to validate if a location
is within the allowed operational areas.
"""

import sys
from pathlib import Path
from typing import Optional, Tuple

from fuzzywuzzy import fuzz, process

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ALLOWED_BAIRROS, CIDADE_ALVO


class GeographicValidator:
    """
    Validates geographic locations against allowed areas.
    
    Uses fuzzy matching to handle variations in spelling and capitalization.
    """
    
    def __init__(self, similarity_threshold: int = 80):
        """
        Initialize the geographic validator.
        
        Args:
            similarity_threshold: Minimum similarity score (0-100) to consider a match
        """
        self.allowed_bairros = ALLOWED_BAIRROS
        self.cidade_alvo = CIDADE_ALVO
        self.similarity_threshold = similarity_threshold
    
    def validate_bairro(self, bairro: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if a bairro is in the allowed list using fuzzy matching.
        
        Args:
            bairro: The neighborhood name to validate
        
        Returns:
            Tuple of (is_valid, matched_bairro_name)
            - is_valid: True if bairro is allowed
            - matched_bairro_name: The standardized name from ALLOWED_BAIRROS, or None
        
        Examples:
            >>> validator = GeographicValidator()
            >>> validator.validate_bairro("campeche")
            (True, "Campeche")
            >>> validator.validate_bairro("jurere")
            (True, "Jurerê Internacional")
            >>> validator.validate_bairro("rio tavares")
            (False, None)
        """
        if not bairro:
            return False, None
        
        # Normalize input
        bairro_normalized = bairro.strip()
        
        # Try exact match first (case-insensitive)
        for allowed in self.allowed_bairros:
            if bairro_normalized.lower() == allowed.lower():
                return True, allowed
        
        # Try fuzzy matching
        match = process.extractOne(
            bairro_normalized,
            self.allowed_bairros,
            scorer=fuzz.token_sort_ratio
        )
        
        if match and match[1] >= self.similarity_threshold:
            matched_bairro = match[0]
            return True, matched_bairro
        
        return False, None
    
    def validate_cidade(self, cidade: str) -> bool:
        """
        Validate if cidade is the target city.
        
        Args:
            cidade: The city name to validate
        
        Returns:
            True if cidade matches CIDADE_ALVO (case-insensitive)
        """
        if not cidade:
            return False
        
        return cidade.strip().lower() == self.cidade_alvo.lower()
    
    def validate_location(
        self,
        bairro: str,
        cidade: Optional[str] = None
    ) -> Tuple[bool, Optional[str], str]:
        """
        Validate complete location (bairro + cidade).
        
        Args:
            bairro: Neighborhood name
            cidade: City name (optional, defaults to CIDADE_ALVO)
        
        Returns:
            Tuple of (is_valid, matched_bairro, reason)
            - is_valid: True if location is valid
            - matched_bairro: Standardized bairro name or None
            - reason: Explanation of validation result
        """
        # Validate cidade if provided
        if cidade and not self.validate_cidade(cidade):
            return False, None, f"Cidade '{cidade}' não é {self.cidade_alvo}"
        
        # Validate bairro
        is_valid, matched_bairro = self.validate_bairro(bairro)
        
        if is_valid:
            return True, matched_bairro, f"Bairro '{matched_bairro}' validado com sucesso"
        else:
            return False, None, f"Bairro '{bairro}' não está na área de atuação"


# Global instance for easy import
geographic_validator = GeographicValidator()