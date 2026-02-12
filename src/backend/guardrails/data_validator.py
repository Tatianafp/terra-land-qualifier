"""
Data validation guardrail.

This module validates extracted data against business rules
and ensures data completeness before qualification.
"""

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MAX_LAND_SIZE_M2, MAX_PRICE_BRL, MIN_LAND_SIZE_M2, MIN_PRICE_BRL


class DataValidator:
    """
    Validates extracted data against business rules.
    
    Ensures data quality, completeness, and reasonable ranges.
    """
    
    REQUIRED_FIELDS = [
        "location",
        "land_size_m2",
        "asking_price",
        "legal_status"
    ]
    
    def __init__(self):
        """Initialize the data validator."""
        self.min_land_size = MIN_LAND_SIZE_M2
        self.max_land_size = MAX_LAND_SIZE_M2
        self.min_price = MIN_PRICE_BRL
        self.max_price = MAX_PRICE_BRL
    
    def validate_land_size(self, size_m2: float) -> Tuple[bool, str]:
        """
        Validate land size is within reasonable range.
        
        Args:
            size_m2: Land size in square meters
        
        Returns:
            Tuple of (is_valid, message)
        """
        if not isinstance(size_m2, (int, float)):
            return False, "Tamanho do terreno deve ser um número"
        
        if size_m2 <= 0:
            return False, "Tamanho do terreno deve ser maior que zero"
        
        if size_m2 < self.min_land_size:
            return False, f"Tamanho do terreno muito pequeno (mín: {self.min_land_size}m²)"
        
        if size_m2 > self.max_land_size:
            return False, f"Tamanho do terreno suspeito (máx: {self.max_land_size}m²)"
        
        return True, "Tamanho validado"
    
    def validate_price(self, price: float) -> Tuple[bool, str]:
        """
        Validate asking price is within reasonable range.
        
        Args:
            price: Asking price in BRL
        
        Returns:
            Tuple of (is_valid, message)
        """
        if not isinstance(price, (int, float)):
            return False, "Preço deve ser um número"
        
        if price <= 0:
            return False, "Preço deve ser maior que zero"
        
        if price < self.min_price:
            return False, f"Preço muito baixo (mín: R$ {self.min_price:,.2f})"
        
        if price > self.max_price:
            return False, f"Preço suspeito (máx: R$ {self.max_price:,.2f})"
        
        return True, "Preço validado"
    
    def validate_legal_status(self, status: str) -> Tuple[bool, str]:
        """
        Validate legal status response.
        
        Args:
            status: Legal documentation status
        
        Returns:
            Tuple of (is_valid, message)
        """
        if not isinstance(status, str):
            return False, "Status jurídico deve ser texto"
        
        status_lower = status.lower().strip()
        
        # Check for affirmative keywords
        affirmative_keywords = ["sim", "possui", "tem", "regularizado", "ok"]
        negative_keywords = ["não", "nao", "sem", "pendente", "irregular"]
        
        has_affirmative = any(kw in status_lower for kw in affirmative_keywords)
        has_negative = any(kw in status_lower for kw in negative_keywords)
        
        if not has_affirmative and not has_negative:
            return False, "Status jurídico não está claro (Sim/Não)"
        
        return True, "Status jurídico validado"
    
    def check_completeness(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Check if all required fields are present and valid.
        
        Args:
            data: Dictionary with extracted data
        
        Returns:
            Tuple of (is_complete, missing_fields)
        """
        missing_fields = []
        
        for field in self.REQUIRED_FIELDS:
            if field not in data or data[field] is None:
                missing_fields.append(field)
            elif isinstance(data[field], str) and not data[field].strip():
                missing_fields.append(field)
        
        is_complete = len(missing_fields) == 0
        return is_complete, missing_fields
    
    def extract_numeric_value(self, text: str) -> Optional[float]:
        """
        Extract numeric value from text using regex.
        
        Handles formats like:
        - "450m²" -> 450
        - "R$ 850.000" -> 850000
        - "850 mil" -> 850000
        
        Args:
            text: Text containing numeric value
        
        Returns:
            Extracted numeric value or None
        """
        if not isinstance(text, str):
            return None
        
        # Remove common currency symbols and units
        cleaned = text.replace("R$", "").replace("m²", "").strip()
        
        # Handle "mil" (thousand) and "milhão/milhões" (million)
        if "milhão" in cleaned.lower() or "milhões" in cleaned.lower():
            # Extract number before "milhão"
            match = re.search(r'([\d.,]+)\s*milhõ', cleaned.lower())
            if match:
                num = float(match.group(1).replace(".", "").replace(",", "."))
                return num * 1_000_000
        
        if "mil" in cleaned.lower():
            # Extract number before "mil"
            match = re.search(r'([\d.,]+)\s*mil', cleaned.lower())
            if match:
                num = float(match.group(1).replace(".", "").replace(",", "."))
                return num * 1_000
        
        # Standard numeric extraction
        # Handle Brazilian format (850.000,50) and US format (850,000.50)
        match = re.search(r'([\d.,]+)', cleaned)
        if match:
            num_str = match.group(1)
            
            # Detect format by checking last separator
            if ',' in num_str and '.' in num_str:
                # Both present - check which comes last
                if num_str.rindex(',') > num_str.rindex('.'):
                    # Brazilian format: 1.000.000,50
                    num_str = num_str.replace(".", "").replace(",", ".")
                else:
                    # US format: 1,000,000.50
                    num_str = num_str.replace(",", "")
            elif ',' in num_str:
                # Only comma - assume decimal separator
                num_str = num_str.replace(",", ".")
            
            try:
                return float(num_str)
            except ValueError:
                return None
        
        return None
    
    def validate_all(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Run all validations on extracted data.
        
        Args:
            data: Dictionary with extracted data
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Check completeness
        is_complete, missing = self.check_completeness(data)
        if not is_complete:
            errors.append(f"Campos faltando: {', '.join(missing)}")
            return False, errors
        
        # Validate land size
        if "land_size_m2" in data:
            is_valid, msg = self.validate_land_size(data["land_size_m2"])
            if not is_valid:
                errors.append(msg)
        
        # Validate price
        if "asking_price" in data:
            is_valid, msg = self.validate_price(data["asking_price"])
            if not is_valid:
                errors.append(msg)
        
        # Validate legal status
        if "legal_status" in data:
            is_valid, msg = self.validate_legal_status(data["legal_status"])
            if not is_valid:
                errors.append(msg)
        
        return len(errors) == 0, errors


# Global instance for easy import
data_validator = DataValidator()