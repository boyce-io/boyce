"""
Question Parser

Parses natural language questions to extract entities:
- Metrics (what to measure)
- Dimensions (how to group)
- Filters (what to filter)
- Time ranges (when)
- Sort/Limit (ordering)
"""

import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class ParsedQuestion:
    """Structured representation of a parsed question."""
    raw_question: str
    metrics: List[str]  # "top performing", "total revenue"
    dimensions: List[str]  # "product_category", "customer_region", "marketing_channel"
    filters: List[str]  # "millennials", "Gen Z", "United States"
    time_ranges: List[str]  # "last 30 days", "this quarter"
    sort: Optional[str]  # "top", "bottom", "highest", "lowest"
    limit: Optional[int]  # 10, 100
    aggregation_type: Optional[str]  # "sum", "count", "average"
    comparison: Optional[str]  # "compare A vs B"


class QuestionParser:
    """
    Parse natural language questions into structured components.
    
    Examples:
    - "What are the top performing product categories by sales?"
      → metrics: ["top performing"], dimensions: ["product_category"], filters: []
    
    - "Show me total revenue by customer region for the last 30 days"
      → metrics: ["revenue"], dimensions: ["customer_region"], filters: ["last 30 days"]
    """
    
    def __init__(self):
        """Initialize parser with patterns."""
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for entity extraction."""
        
        # Metric patterns (what to measure)
        self.metric_patterns = [
            r'\b(top|bottom|highest|lowest)\s+(\w+)',  # "top performing"
            r'\b(total|sum|count|average|avg)\s+(\w+)',  # "total revenue"
            r'\b(revenue|sales|orders|aov|conversion|performance)',  # standalone metrics
            r'\b(trending|popular|best)',  # qualitative metrics
        ]
        
        # Dimension patterns (how to group)
        self.dimension_patterns = [
            r'\bby\s+(\w+(?:\s+\w+)?)',  # "by product_category", "by region"
            r'\bfor\s+(?:each|every)\s+(\w+)',  # "for each customer"
            r'\bper\s+(\w+)',  # "per order"
            r'\b(product|category|customer|region|channel|order)',  # explicit dimensions
        ]
        
        # Filter patterns
        self.filter_patterns = [
            r'\bfor\s+(\w+(?:\s+\w+)?)',  # "for Electronics", "for California"
            r'\bin\s+(?:the\s+)?([A-Z][\w\s]+)',  # "in United States", "in California"
            r'\bvia\s+(\w+)',  # "via email", "via social"
            r'\b(electronics|clothing|home|sports|books)',  # product category shortcuts
        ]
        
        # Time range patterns
        self.time_patterns = [
            r'\blast\s+(\d+)\s+(day|week|month|quarter|year)s?',  # "last 30 days"
            r'\bpast\s+(\d+)\s+(day|week|month|quarter|year)s?',  # "past 7 days"
            r'\bthis\s+(week|month|quarter|year)',  # "this quarter"
            r'\btoday|yesterday',  # shortcuts
        ]
        
        # Sort patterns
        self.sort_patterns = [
            r'\b(top|bottom)\s+(\d+)?',  # "top 10"
            r'\b(highest|lowest)',  # "highest rated"
            r'\b(best|worst)',  # "best performing"
        ]
        
        # Limit patterns
        self.limit_pattern = r'\b(top|bottom)\s+(\d+)\b'
        
        # Aggregation type patterns
        self.aggregation_patterns = [
            (r'\btotal\b', 'sum'),
            (r'\bsum\b', 'sum'),
            (r'\bcount\b', 'count'),
            (r'\baverage\b', 'avg'),
            (r'\bavg\b', 'avg'),
            (r'\bmean\b', 'avg'),
        ]
        
        # Comparison patterns
        self.comparison_pattern = r'\bcompare\s+(\w+)\s+(?:vs|versus|and)\s+(\w+)'
    
    def parse(self, question: str) -> ParsedQuestion:
        """
        Parse a natural language question into structured components.
        
        Args:
            question: Natural language question
            
        Returns:
            ParsedQuestion with extracted entities
        """
        question_lower = question.lower()
        
        # Extract metrics
        metrics = self._extract_metrics(question_lower)
        
        # Extract dimensions
        dimensions = self._extract_dimensions(question_lower)
        
        # Extract filters
        filters = self._extract_filters(question, question_lower)  # Use original for capitalization
        
        # Extract time ranges
        time_ranges = self._extract_time_ranges(question_lower)
        
        # Extract sort
        sort_dir = self._extract_sort(question_lower)
        
        # Extract limit
        limit = self._extract_limit(question_lower)
        
        # Extract aggregation type
        agg_type = self._extract_aggregation_type(question_lower)
        
        # Extract comparison
        comparison = self._extract_comparison(question_lower)
        
        return ParsedQuestion(
            raw_question=question,
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            time_ranges=time_ranges,
            sort=sort_dir,
            limit=limit,
            aggregation_type=agg_type,
            comparison=comparison
        )
    
    def _extract_metrics(self, question: str) -> List[str]:
        """Extract metric terms from question."""
        metrics = []
        for pattern in self.metric_patterns:
            matches = re.finditer(pattern, question)
            for match in matches:
                if match.lastindex == 2:
                    # Two-word metrics like "top performing"
                    metrics.append(f"{match.group(1)} {match.group(2)}")
                else:
                    # Single-word metrics
                    metrics.append(match.group(1))
        return list(set(metrics))  # Remove duplicates
    
    def _extract_dimensions(self, question: str) -> List[str]:
        """Extract dimension terms from question."""
        dimensions = []
        for pattern in self.dimension_patterns:
            matches = re.finditer(pattern, question)
            for match in matches:
                dim = match.group(1).strip()
                # Clean up plurals
                if dim.endswith('s') and dim not in ['analysis', 'series']:
                    dim = dim[:-1]  # "channels" → "channel"
                dimensions.append(dim)
        return list(set(dimensions))
    
    def _extract_filters(self, original_question: str, lower_question: str) -> List[str]:
        """Extract filter terms from question."""
        filters = []
        for pattern in self.filter_patterns:
            matches = re.finditer(pattern, lower_question)
            for match in matches:
                # Use original question to preserve capitalization
                start, end = match.span(1)
                filter_val = original_question[start:end].strip()
                filters.append(filter_val)
        return list(set(filters))
    
    def _extract_time_ranges(self, question: str) -> List[str]:
        """Extract time range terms from question."""
        time_ranges = []
        for pattern in self.time_patterns:
            matches = re.finditer(pattern, question)
            for match in matches:
                time_ranges.append(match.group(0))
        return time_ranges
    
    def _extract_sort(self, question: str) -> Optional[str]:
        """Extract sort direction from question."""
        for pattern in self.sort_patterns:
            match = re.search(pattern, question)
            if match:
                sort_word = match.group(1)
                if sort_word in ['top', 'highest', 'best']:
                    return 'desc'
                elif sort_word in ['bottom', 'lowest', 'worst']:
                    return 'asc'
        return 'desc'  # Default to descending for "top" queries
    
    def _extract_limit(self, question: str) -> Optional[int]:
        """Extract limit number from question."""
        match = re.search(self.limit_pattern, question)
        if match and match.group(2):
            return int(match.group(2))
        # Default limit for "top" queries
        if 'top' in question or 'bottom' in question:
            return 10
        return None
    
    def _extract_aggregation_type(self, question: str) -> Optional[str]:
        """Extract aggregation type from question."""
        for pattern, agg_type in self.aggregation_patterns:
            if re.search(pattern, question):
                return agg_type
        return 'sum'  # Default to sum
    
    def _extract_comparison(self, question: str) -> Optional[str]:
        """Extract comparison terms from question."""
        match = re.search(self.comparison_pattern, question)
        if match:
            return f"{match.group(1)} vs {match.group(2)}"
        return None


def test_parser():
    """Test the question parser."""
    parser = QuestionParser()
    
    test_questions = [
        "What are the top performing product categories by sales?",
        "Show me total revenue by customer region for the last 30 days",
        "Which products have the highest order volume by category?",
        "Compare sales between email and social marketing channels",
        "Top 5 customers by total order value in California",
    ]
    
    print("=" * 60)
    print("QUESTION PARSER TEST")
    print("=" * 60)
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n{i}. Question: {question}")
        parsed = parser.parse(question)
        print(f"   Metrics: {parsed.metrics}")
        print(f"   Dimensions: {parsed.dimensions}")
        print(f"   Filters: {parsed.filters}")
        print(f"   Time ranges: {parsed.time_ranges}")
        print(f"   Sort: {parsed.sort}")
        print(f"   Limit: {parsed.limit}")
        print(f"   Aggregation: {parsed.aggregation_type}")
        print(f"   Comparison: {parsed.comparison}")
    
    print(f"\n✅ Parsed {len(test_questions)} questions successfully")


if __name__ == "__main__":
    test_parser()

