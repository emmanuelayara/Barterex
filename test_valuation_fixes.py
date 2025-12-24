#!/usr/bin/env python3
"""
Test script to verify valuation system fixes
Tests the price estimator service and ensure all fixes are working
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.ai_price_estimator import AIPriceEstimator

def test_estimator():
    """Test the AI Price Estimator"""
    print("=" * 60)
    print("Testing Valuation System Fixes")
    print("=" * 60)
    
    estimator = AIPriceEstimator()
    
    # Test 1: Fallback estimate with proper confidence levels
    print("\n[TEST 1] Fallback Estimate - Confidence Capitalization")
    print("-" * 60)
    fallback = estimator._get_fallback_estimate('Electronics', 'good')
    print(f"Category: Electronics, Condition: good")
    print(f"Estimated Price: ${fallback['estimated_price']}")
    print(f"Confidence: {fallback['confidence']}")
    print(f"Data Points: {fallback['data_points']}")
    assert fallback['confidence'] in ['High', 'Medium', 'Low'], f"❌ Confidence should be capitalized, got: {fallback['confidence']}"
    assert fallback['confidence'] == 'Low', f"❌ Fallback should have 'Low' confidence, got: {fallback['confidence']}"
    print("✅ PASS: Confidence level is properly capitalized")
    
    # Test 2: Category normalization
    print("\n[TEST 2] Category Normalization")
    print("-" * 60)
    test_categories = [
        ('Electronics', 150),
        ('Fashion / Clothing', 30),
        ('Home & Kitchen', 80),
        ('Phones & Gadgets', 150),
        ('Unknown Category', 50),  # Should default to 50
    ]
    
    for category, expected_base in test_categories:
        estimate = estimator._get_fallback_estimate(category, 'new')
        # For 'new' condition, multiplier is 1.2, so price should be base * 1.2
        expected_price = expected_base * 1.2
        actual_price = estimate['estimated_price']
        print(f"  • {category:25} -> ${actual_price} (expected ~${expected_price})")
        # Allow small floating point differences
        assert abs(actual_price - expected_price) < 0.01, f"❌ Price mismatch for {category}"
    print("✅ PASS: All categories normalized correctly")
    
    # Test 3: Condition handling
    print("\n[TEST 3] Condition Handling")
    print("-" * 60)
    conditions = ['new', 'like-new', 'good', 'fair', 'poor']
    base_price = 100
    
    for condition in conditions:
        estimate = estimator._get_fallback_estimate('other', condition)
        print(f"  • Condition: {condition:10} -> ${estimate['estimated_price']}")
        assert estimate['estimated_price'] > 0, f"❌ Price should be positive for {condition}"
    print("✅ PASS: All conditions handled correctly")
    
    # Test 4: Credit value calculation
    print("\n[TEST 4] Credit Value Calculation")
    print("-" * 60)
    test_price = 100.0
    credit_info = estimator.get_credit_value_estimate(test_price)
    print(f"Price: ${test_price}")
    print(f"Commission (10%): ${credit_info['platform_commission']}")
    print(f"Credit Value (in response): ${credit_info['credit_value']}")
    
    assert 'credit_value' in credit_info, "❌ Response should have 'credit_value' key"
    assert 'net_credit_value' not in credit_info or credit_info.get('credit_value') > 0, "❌ credit_value should be present"
    assert credit_info['credit_value'] == 90.0, f"❌ Credit value should be 90 (100 - 10% commission), got {credit_info['credit_value']}"
    print("✅ PASS: Credit value correctly uses 'credit_value' key")
    
    # Test 5: Price estimate with multiple conditions
    print("\n[TEST 5] Full Price Estimation")
    print("-" * 60)
    estimate = estimator.estimate_price(
        description="Apple iPhone 13 Pro Max, 256GB, Gold, in excellent condition",
        condition="good",
        category="Electronics"
    )
    print(f"Description: Apple iPhone 13 Pro Max...")
    print(f"Condition: good")
    print(f"Category: Electronics")
    print(f"Estimated Price: ${estimate['estimated_price']}")
    print(f"Price Range: ${estimate['price_range']['min']} - ${estimate['price_range']['max']}")
    print(f"Confidence: {estimate['confidence']}")
    print(f"Data Points: {estimate['data_points']}")
    
    assert 'estimated_price' in estimate, "❌ Should have estimated_price"
    assert 'confidence' in estimate, "❌ Should have confidence"
    assert estimate['confidence'] in ['High', 'Medium', 'Low'], f"❌ Confidence should be High/Medium/Low, got {estimate['confidence']}"
    print("✅ PASS: Full estimation works correctly")
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED - Valuation system is working!")
    print("=" * 60)

if __name__ == '__main__':
    try:
        test_estimator()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
