#!/usr/bin/env python3
"""
Debug why drug and TA filters are returning all results
"""
import requests

BASE_URL = "http://127.0.0.1:5000"

def test_individual_filters():
    """Test each filter type individually"""
    print("=== Testing Individual Filter Types ===")

    test_cases = [
        # Drug filters
        ("Drug: Avelumab Focus", {'drug_filters[]': ['Avelumab Focus']}),
        ("Drug: Tepotinib Focus", {'drug_filters[]': ['Tepotinib Focus']}),
        ("Drug: All EMD Portfolio", {'drug_filters[]': ['All EMD Portfolio']}),

        # TA filters
        ("TA: Bladder Cancer", {'ta_filters[]': ['Bladder Cancer']}),
        ("TA: Lung Cancer", {'ta_filters[]': ['Lung Cancer']}),
        ("TA: Renal Cancer", {'ta_filters[]': ['Renal Cancer']}),

        # Session filters (these work)
        ("Session: Proffered Paper", {'session_filters[]': ['Proffered Paper']}),
        ("Session: Mini Oral", {'session_filters[]': ['Mini Oral Session']}),

        # Date filters (these work)
        ("Date: Day 1", {'date_filters[]': ['Day 1 (10/17/2025)']}),
    ]

    for name, params in test_cases:
        try:
            response = requests.get(f"{BASE_URL}/api/data", params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                total = data.get('total', 0)

                if total == 4686:
                    print(f"BROKEN: {name}: {total} (all results - not filtering)")
                elif total == 0:
                    print(f"EMPTY: {name}: {total} (no results)")
                else:
                    print(f"WORKING: {name}: {total} results")

                # Show filter context if available
                filter_context = data.get('filter_context', {})
                if filter_context and 'filter_summary' in filter_context:
                    print(f"  Context: {filter_context['filter_summary']}")

            else:
                print(f"ERROR: {name}: HTTP {response.status_code}")

        except Exception as e:
            print(f"FAILED: {name}: {e}")

        print()  # Add spacing

if __name__ == "__main__":
    test_individual_filters()