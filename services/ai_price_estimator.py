"""
AI Price Estimation Service
Analyzes item images and descriptions to estimate market prices
using computer vision and web scraping techniques.
"""

import os
import base64
import requests
from typing import Dict, List, Optional, Tuple
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PriceEstimationError(Exception):
    """Custom exception for price estimation errors"""
    pass


class AIPriceEstimator:
    """
    Service to estimate item prices using:
    1. OpenAI Vision API for image analysis
    2. Google Custom Search API for price comparisons
    3. Fallback heuristics based on category and condition
    """
    
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        self.google_cx = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
        self.cache = {}  # Simple in-memory cache
        self.cache_duration = timedelta(hours=24)
    
    def estimate_price(
        self, 
        image_path: Optional[str] = None,
        image_data: Optional[bytes] = None,
        description: str = "",
        condition: str = "good",
        category: str = "other"
    ) -> Dict:
        """
        Main method to estimate item price
        
        Args:
            image_path: Path to image file
            image_data: Raw image bytes (alternative to image_path)
            description: Item description
            condition: Item condition (new, like-new, good, fair, poor)
            category: Item category
            
        Returns:
            Dict with estimated price range, confidence, and source info
        """
        try:
            # Step 1: Try to search for market prices first (fastest path)
            search_query = self._build_search_query(description, None, category)
            price_data = self._search_market_prices(search_query, condition)
            
            # If we got market data, use it immediately
            if price_data:
                adjusted_prices = self._adjust_for_condition(price_data, condition)
                final_estimate = self._calculate_final_estimate(
                    adjusted_prices, 
                    None,
                    category
                )
                logger.info(f"Price estimate completed using {len(price_data)} market data points")
                return final_estimate
            
            # Step 2: If no market data, fall back to category-based estimate
            logger.info("No market data found, using fallback estimate")
            return self._get_fallback_estimate(category, condition)
            
        except Exception as e:
            logger.error(f"Price estimation error: {str(e)}", exc_info=True)
            return self._get_fallback_estimate(category, condition)
    
    def _analyze_image(
        self, 
        image_path: Optional[str],
        image_data: Optional[bytes],
        description: str
    ) -> Dict:
        """
        Analyze image using OpenAI Vision API to identify item details
        """
        if not self.openai_api_key:
            logger.warning("OpenAI API key not configured, skipping image analysis")
            return {"item_type": "unknown", "features": [], "estimated_age": "unknown"}
        
        try:
            # Encode image to base64
            if image_path:
                with open(image_path, "rb") as image_file:
                    image_data = image_file.read()
            
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # Call OpenAI Vision API
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}"
            }
            
            payload = {
                "model": "gpt-4o-mini",  # or gpt-4-vision-preview
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Analyze this item image and provide details for price estimation.
Description provided by user: {description}

Please provide:
1. Item type/category (be specific)
2. Brand (if visible)
3. Condition assessment (new, like-new, good, fair, poor)
4. Key features or specifications
5. Estimated age or model year
6. Any damage or wear visible

Return as JSON format."""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=8
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # Try to parse JSON from response
                try:
                    analysis = json.loads(content)
                except:
                    # If not valid JSON, extract key info manually
                    analysis = {
                        "item_type": description,
                        "features": [content[:200]],
                        "ai_description": content
                    }
                
                logger.info(f"Image analysis completed: {analysis.get('item_type', 'unknown')}")
                return analysis
            else:
                logger.warning(f"OpenAI API error: {response.status_code}")
                return {"item_type": description, "features": []}
                
        except Exception as e:
            logger.error(f"Image analysis failed: {str(e)}", exc_info=True)
            return {"item_type": description, "features": []}
    
    def _build_search_query(
        self, 
        description: str, 
        analysis: Optional[Dict],
        category: str
    ) -> str:
        """Build optimized search query for price lookup"""
        
        # Start with description
        query_parts = [description]
        
        # Add AI analysis details if available
        if analysis:
            item_type = analysis.get('item_type', '')
            brand = analysis.get('brand', '')
            
            if item_type and item_type != 'unknown':
                query_parts.insert(0, item_type)
            if brand:
                query_parts.insert(0, brand)
        
        # Add category if not redundant
        if category and category.lower() not in description.lower():
            query_parts.append(category)
        
        # Add "price" keyword for better results
        query = ' '.join(query_parts) + ' price buy sell'
        
        return query[:200]  # Limit query length
    
    def _search_market_prices(self, query: str, condition: str) -> List[Dict]:
        """
        Search for market prices using Google Custom Search API
        Targets marketplaces like eBay, Facebook Marketplace, Craigslist, etc.
        """
        if not self.google_api_key or not self.google_cx:
            logger.warning("Google API not configured, using fallback prices")
            return []
        
        try:
            # Search parameters
            params = {
                'key': self.google_api_key,
                'cx': self.google_cx,
                'q': query,
                'num': 10  # Get top 10 results
            }
            
            response = requests.get(
                'https://www.googleapis.com/customsearch/v1',
                params=params,
                timeout=8
            )
            
            if response.status_code == 200:
                results = response.json().get('items', [])
                prices = self._extract_prices_from_results(results)
                logger.info(f"Found {len(prices)} price references for: {query}")
                return prices
            else:
                logger.warning(f"Google Search API error: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Price search failed: {str(e)}", exc_info=True)
            return []
    
    def _extract_prices_from_results(self, results: List[Dict]) -> List[Dict]:
        """Extract price information from search results"""
        import re
        
        prices = []
        price_pattern = r'\$?\s*(\d{1,6}(?:[.,]\d{2})?)'
        
        for result in results:
            snippet = result.get('snippet', '') + ' ' + result.get('title', '')
            
            # Find all price-like numbers
            matches = re.findall(price_pattern, snippet)
            
            for match in matches:
                try:
                    # Clean and convert to float
                    price = float(match.replace(',', ''))
                    
                    # Filter unrealistic prices (between $1 and $100,000)
                    if 1 <= price <= 100000:
                        prices.append({
                            'price': price,
                            'source': result.get('displayLink', 'unknown'),
                            'title': result.get('title', '')[:100]
                        })
                except ValueError:
                    continue
        
        return prices
    
    def _adjust_for_condition(self, price_data: List[Dict], condition: str) -> List[float]:
        """Apply condition-based price adjustment"""
        
        # Condition multipliers
        condition_multipliers = {
            'new': 1.0,
            'like-new': 0.85,
            'like_new': 0.85,
            'good': 0.65,
            'fair': 0.45,
            'poor': 0.25
        }
        
        multiplier = condition_multipliers.get(condition.lower(), 0.65)
        
        adjusted_prices = []
        for item in price_data:
            adjusted_price = item['price'] * multiplier
            adjusted_prices.append(adjusted_price)
        
        return adjusted_prices
    
    def _calculate_final_estimate(
        self,
        adjusted_prices: List[float],
        analysis: Optional[Dict],
        category: str
    ) -> Dict:
        """Calculate final price estimate with confidence level"""
        
        if not adjusted_prices:
            return self._get_fallback_estimate(category, "good")
        
        # Calculate statistics
        adjusted_prices.sort()
        count = len(adjusted_prices)
        
        # Remove outliers (top and bottom 10%)
        if count > 10:
            trim_count = max(1, count // 10)
            adjusted_prices = adjusted_prices[trim_count:-trim_count]
        
        # Calculate price range
        min_price = min(adjusted_prices)
        max_price = max(adjusted_prices)
        avg_price = sum(adjusted_prices) / len(adjusted_prices)
        median_price = adjusted_prices[len(adjusted_prices) // 2]
        
        # Confidence based on data points
        if count >= 8:
            confidence = "high"
        elif count >= 4:
            confidence = "medium"
        else:
            confidence = "low"
        
        return {
            'estimated_price': round(median_price, 2),
            'price_range': {
                'min': round(min_price, 2),
                'max': round(max_price, 2),
                'average': round(avg_price, 2)
            },
            'confidence': confidence,
            'data_points': count,
            'currency': 'USD',
            'timestamp': datetime.utcnow().isoformat(),
            'sources': f"Based on {count} market listings"
        }
    
    def _get_fallback_estimate(self, category: str, condition: str) -> Dict:
        """
        Provide fallback estimates based on category averages
        when API data is unavailable
        """
        
        # Category-based average prices
        category_averages = {
            'electronics': 150,
            'furniture': 200,
            'clothing': 30,
            'books': 15,
            'toys': 25,
            'sports': 50,
            'tools': 75,
            'appliances': 120,
            'jewelry': 100,
            'art': 80,
            'collectibles': 60,
            'automotive': 300,
            'other': 50
        }
        
        base_price = category_averages.get(category.lower(), 50)
        
        # Adjust for condition
        condition_multipliers = {
            'new': 1.2,
            'like-new': 1.0,
            'like_new': 1.0,
            'good': 0.75,
            'fair': 0.5,
            'poor': 0.3
        }
        
        multiplier = condition_multipliers.get(condition.lower(), 0.75)
        estimated_price = base_price * multiplier
        
        return {
            'estimated_price': round(estimated_price, 2),
            'price_range': {
                'min': round(estimated_price * 0.7, 2),
                'max': round(estimated_price * 1.3, 2),
                'average': round(estimated_price, 2)
            },
            'confidence': 'low',
            'data_points': 0,
            'currency': 'USD',
            'timestamp': datetime.utcnow().isoformat(),
            'sources': 'Category-based estimate (no market data available)',
            'note': 'This is a rough estimate. Actual market value may vary significantly.'
        }
    
    def get_credit_value_estimate(self, estimated_price: float) -> Dict:
        """
        Convert estimated price to platform credit value
        Apply platform commission and conversion rate
        """
        
        # Platform takes 10% commission
        platform_commission = 0.10
        
        # Calculate credit value
        gross_value = estimated_price
        commission = gross_value * platform_commission
        net_credit_value = gross_value - commission
        
        return {
            'gross_value': round(gross_value, 2),
            'platform_commission': round(commission, 2),
            'commission_rate': f"{platform_commission * 100}%",
            'net_credit_value': round(net_credit_value, 2),
            'explanation': f"You'll receive approximately ${net_credit_value:.2f} in credits after {platform_commission * 100}% platform fee"
        }


# Singleton instance
_estimator_instance = None

def get_price_estimator() -> AIPriceEstimator:
    """Get or create the price estimator singleton"""
    global _estimator_instance
    if _estimator_instance is None:
        _estimator_instance = AIPriceEstimator()
    return _estimator_instance
