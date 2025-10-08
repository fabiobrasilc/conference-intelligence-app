"""
AI-First Endpoint Testing Script
=================================

Tests the new /api/chat/ai-first endpoint with queries from The Bible.
Validates:
1. AI pharmaceutical knowledge (drug understanding without expansion)
2. Table generation accuracy
3. Response quality
4. Backend logging

Run with Flask server already started on port 5001.
"""

import requests
import json
import time
import pandas as pd
from typing import Dict, List, Any
import sys

# Test queries from The Bible (PHASE_1_DETAILS.md)
TEST_QUERIES = [
    {
        "query": "What is pembrolizumab?",
        "expected_behavior": "AI should explain drug + show table of pembro studies",
        "test_drug_knowledge": True,
        "expected_table": True,
        "check_keywords": ["pembrolizumab", "keytruda", "pd-1", "checkpoint"]
    },
    {
        "query": "Show me ADC studies in breast cancer",
        "expected_behavior": "AI knows ADC = antibody-drug conjugates, filters breast cancer",
        "test_drug_knowledge": True,
        "expected_table": True,
        "check_keywords": ["adc", "antibody", "breast"]
    },
    {
        "query": "EV + P data updates",
        "expected_behavior": "AI knows EV = enfortumab vedotin, P = pembrolizumab",
        "test_drug_knowledge": True,
        "expected_table": True,
        "check_keywords": ["enfortumab", "pembrolizumab"]
    },
    {
        "query": "What's MD Anderson presenting?",
        "expected_behavior": "Show table of MD Anderson studies",
        "test_drug_knowledge": False,
        "expected_table": True,
        "check_keywords": ["md anderson", "anderson"]
    },
    {
        "query": "Sessions on 10/19",
        "expected_behavior": "Large result set - show first 500 + offer refinement",
        "test_drug_knowledge": False,
        "expected_table": True,
        "check_keywords": ["10/19", "october"]
    },
    {
        "query": "Pembrolizumab studies at MD Anderson",
        "expected_behavior": "Multi-dimensional query - focused table",
        "test_drug_knowledge": True,
        "expected_table": True,
        "check_keywords": ["pembrolizumab", "md anderson"]
    },
    {
        "query": "Top 20 most active authors",
        "expected_behavior": "AI counts/ranks from data",
        "test_drug_knowledge": False,
        "expected_table": False,  # Should be a ranked list, not table
        "check_keywords": ["author", "presenter"]
    },
    {
        "query": "Bladder cancer immunotherapy combinations",
        "expected_behavior": "Should contextualize vs. Bavencio (avelumab)",
        "test_drug_knowledge": False,
        "expected_table": True,
        "check_keywords": ["bladder", "immunotherapy", "bavencio"]
    },
    {
        "query": "What are your capabilities?",
        "expected_behavior": "Meta query - should NOT return all 4686 studies!",
        "test_drug_knowledge": False,
        "expected_table": False,
        "check_keywords": ["capabilities", "help", "can do"]
    },
    {
        "query": "gleecotamab gonetecan",
        "expected_behavior": "AI infers ADC from -mab + -tecan suffix",
        "test_drug_knowledge": True,
        "expected_table": True,
        "check_keywords": ["gleecotamab", "adc", "antibody"]
    }
]


class AIFirstTester:
    def __init__(self, base_url="http://127.0.0.1:5001"):
        self.base_url = base_url
        self.endpoint = f"{base_url}/api/chat/ai-first"
        self.results = []

    def send_query(self, query: str, filters: Dict = None) -> Dict[str, Any]:
        """Send query to AI-first endpoint and collect response."""
        if filters is None:
            filters = {
                "drug_filters": [],
                "ta_filters": [],
                "session_filters": [],
                "date_filters": []
            }

        payload = {
            "message": query,
            **filters
        }

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                stream=True,
                timeout=60
            )

            if response.status_code != 200:
                return {
                    "error": f"HTTP {response.status_code}",
                    "response": response.text
                }

            # Parse SSE stream
            ai_response = ""
            table_data = None
            events = []

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Remove 'data: ' prefix

                        if data_str == '[DONE]':
                            break

                        try:
                            event = json.loads(data_str)
                            events.append(event)

                            if 'text' in event:
                                ai_response += event['text']

                            if 'table' in event:
                                table_data = event['table']

                        except json.JSONDecodeError:
                            pass

            return {
                "ai_response": ai_response,
                "table_data": table_data,
                "table_count": len(table_data) if table_data else 0,
                "events": events
            }

        except Exception as e:
            return {
                "error": str(e),
                "response": None
            }

    def validate_response(self, test_case: Dict, result: Dict) -> Dict[str, Any]:
        """Validate response against expected behavior."""
        validation = {
            "query": test_case["query"],
            "passed": True,
            "issues": []
        }

        # Check for errors
        if "error" in result:
            validation["passed"] = False
            validation["issues"].append(f"Error: {result['error']}")
            return validation

        ai_response = result.get("ai_response", "").lower()
        table_count = result.get("table_count", 0)

        # Test 1: Table generation expectation
        if test_case["expected_table"]:
            if table_count == 0:
                validation["issues"].append(f"Expected table but got none")
                validation["passed"] = False
            elif table_count > 500:
                validation["issues"].append(f"Table too large: {table_count} rows (should limit to 500)")
        else:
            if table_count > 0:
                validation["issues"].append(f"Unexpected table with {table_count} rows")

        # Test 2: Check for expected keywords in response
        missing_keywords = []
        for keyword in test_case["check_keywords"]:
            if keyword.lower() not in ai_response:
                missing_keywords.append(keyword)

        if missing_keywords:
            validation["issues"].append(f"Missing keywords: {', '.join(missing_keywords)}")

        # Test 3: Drug knowledge test (if applicable)
        if test_case["test_drug_knowledge"]:
            # For queries like "EV + P", AI should understand abbreviations
            if "ev" in test_case["query"].lower() and "enfortumab" not in ai_response:
                validation["issues"].append("AI didn't recognize 'EV' = enfortumab vedotin")

            if test_case["query"].lower() == "show me adc studies in breast cancer":
                if "antibody" not in ai_response and "conjugate" not in ai_response:
                    validation["issues"].append("AI didn't explain ADC = antibody-drug conjugate")

        # Test 4: Meta query check (shouldn't dump all data)
        if "capabilities" in test_case["query"].lower():
            if table_count > 100:
                validation["issues"].append(f"Meta query returned {table_count} studies - should be 0!")
                validation["passed"] = False

        return validation

    def run_test_suite(self):
        """Run all test queries and generate report."""
        print("="*80)
        print("AI-FIRST ENDPOINT TEST SUITE")
        print("="*80)
        print(f"Testing endpoint: {self.endpoint}")
        print(f"Number of test queries: {len(TEST_QUERIES)}\n")

        for i, test_case in enumerate(TEST_QUERIES, 1):
            print(f"\n[TEST {i}/{len(TEST_QUERIES)}] {test_case['query']}")
            print(f"Expected: {test_case['expected_behavior']}")
            print("-" * 80)

            # Send query
            result = self.send_query(test_case["query"])

            # Validate
            validation = self.validate_response(test_case, result)
            self.results.append(validation)

            # Print results
            if "error" in result:
                print(f"[ERROR]: {result['error']}")
            else:
                status = "[PASS]" if validation["passed"] else "[FAIL]"
                print(f"{status}")
                print(f"  AI Response Length: {len(result.get('ai_response', ''))} chars")
                print(f"  Table Rows: {result.get('table_count', 0)}")

                if validation["issues"]:
                    print(f"  Issues:")
                    for issue in validation["issues"]:
                        print(f"    - {issue}")

                # Show snippet of AI response
                ai_text = result.get('ai_response', '')
                if ai_text:
                    snippet = ai_text[:200] + "..." if len(ai_text) > 200 else ai_text
                    print(f"  AI Response Snippet: {snippet}")

            time.sleep(1)  # Rate limiting

        # Final summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)

        passed = sum(1 for r in self.results if r["passed"])
        failed = len(self.results) - passed

        print(f"Total Tests: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed/len(self.results)*100):.1f}%")

        if failed > 0:
            print(f"\nFailed Tests:")
            for r in self.results:
                if not r["passed"]:
                    print(f"  - {r['query']}")
                    for issue in r["issues"]:
                        print(f"      {issue}")

        # Save detailed results
        self.save_results()

    def save_results(self):
        """Save test results to JSON file."""
        output_file = "ai_first_test_results.json"
        with open(output_file, 'w') as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "endpoint": self.endpoint,
                "total_tests": len(self.results),
                "passed": sum(1 for r in self.results if r["passed"]),
                "failed": sum(1 for r in self.results if not r["passed"]),
                "results": self.results
            }, f, indent=2)

        print(f"\n[SAVED] Detailed results saved to: {output_file}")


if __name__ == "__main__":
    # Windows Unicode compatibility
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # Check if server is running
    try:
        response = requests.get("http://127.0.0.1:5001/")
        print("[OK] Flask server detected on port 5001\n")
    except requests.exceptions.ConnectionError:
        print("[ERROR] Flask server not running on port 5001")
        print("   Please start server: python app.py")
        sys.exit(1)

    # Run tests
    tester = AIFirstTester()
    tester.run_test_suite()
