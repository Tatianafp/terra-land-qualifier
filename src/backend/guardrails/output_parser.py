"""
Output parser for extracting structured JSON from LLM responses.

This module handles parsing the final qualification JSON from agent output.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import LeadQualification


class OutputParser:
    """
    Parses LLM output to extract structured qualification data.
    
    Handles various output formats and extracts JSON robustly.
    """
    
    def extract_json_from_text(self, text: str) -> Optional[dict]:
        """
        Extract JSON object from text that may contain other content.
        
        Handles:
        - JSON wrapped in markdown code blocks
        - JSON with surrounding text
        - Multiple JSON objects (returns first valid one)
        
        Args:
            text: Text potentially containing JSON
        
        Returns:
            Parsed JSON dict or None if no valid JSON found
        """
        if not text:
            return None
        
        # Try to find JSON in markdown code blocks first
        code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        code_matches = re.findall(code_block_pattern, text, re.DOTALL)
        
        for match in code_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        
        # Try to find raw JSON object
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        json_matches = re.findall(json_pattern, text, re.DOTALL)
        
        for match in json_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        
        # Last resort: try parsing entire text as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    
    def parse_qualification(self, text: str) -> Optional[LeadQualification]:
        """
        Parse text to extract LeadQualification object.
        
        Args:
            text: LLM output text
        
        Returns:
            LeadQualification object or None if parsing fails
        """
        json_data = self.extract_json_from_text(text)
        
        if not json_data:
            return None
        
        try:
            # Validate and parse using Pydantic model
            return LeadQualification(**json_data)
        except Exception as e:
            print(f"Error parsing qualification: {e}")
            return None
    
    def is_qualification_complete(self, text: str) -> bool:
        """
        Check if the text contains a complete qualification JSON.
        
        Args:
            text: LLM output text
        
        Returns:
            True if valid qualification JSON is present
        """
        qualification = self.parse_qualification(text)
        return qualification is not None


# Global instance for easy import
output_parser = OutputParser()