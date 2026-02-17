#!/usr/bin/env python
"""Comprehensive Test Runner for Barterex"""
import subprocess
import sys
import os
from datetime import datetime

test_files = [
    'test_models.py',
    'test_app_models.py',
    'test_security.py',
    'test_rate_limiting.py',
    'test_ranking_system.py',
    'test_migration.py',
    'test_login_page.py',
    'test_item_validators.py',
    'test_google_api.py',
    'test_full_workflow.py',
    'test_form_validation.py',
    'test_email_config.py',
    'test_db_update.py',
    'test_approval.py',
    'test_appeal.py'
]

def run_tests():
    print("\n" + "="*80)
    print("BARTEREX TEST SUITE RUNNER")
    print("Started: {}".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    print("="*80 + "\n")
    
    results = {
        'passed': [],
        'failed': [],
        'error': [],
        'timeout': []
    }
    
    total_tests = len(test_files)
    
    for idx, test_file in enumerate(test_files, 1):
        if not os.path.exists(test_file):
            print("[{}/{}] SKIP {} (not found)".format(idx, total_tests, test_file))
            continue
            
        print("[{}/{}] RUN {} ".format(idx, total_tests, test_file), end='', flush=True)
        
        try:
            result = subprocess.run(
                [sys.executable, test_file],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print("[PASS]")
                results['passed'].append(test_file)
            else:
                print("[FAIL]")
                results['failed'].append((test_file, result.stdout + result.stderr))
                
        except subprocess.TimeoutExpired:
            print("[TIMEOUT]")
            results['timeout'].append(test_file)
        except Exception as e:
            print("[ERROR] {}".format(str(e)[:40]))
            results['error'].append((test_file, str(e)))
    
    # Print Summary
    print("\n" + "="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)
    
    passed_count = len(results['passed'])
    failed_count = len(results['failed'])
    error_count = len(results['error'])
    timeout_count = len(results['timeout'])
    total_run = passed_count + failed_count + error_count + timeout_count
    
    print("\nTotal Tests Run: {}/{}".format(total_run, total_tests))
    print("PASSED:  {}".format(passed_count))
    print("FAILED:  {}".format(failed_count))
    print("ERROR:   {}".format(error_count))
    print("TIMEOUT: {}".format(timeout_count))
    
    if total_run > 0:
        success_rate = (passed_count / total_run) * 100
        print("\nSuccess Rate: {:.1f}%".format(success_rate))
    
    # Detailed Results
    if results['passed']:
        print("\n" + "-"*80)
        print("PASSED TESTS:")
        print("-"*80)
        for test in results['passed']:
            print("  [OK] {}".format(test))
    
    if results['failed']:
        print("\n" + "-"*80)
        print("FAILED TESTS:")
        print("-"*80)
        for test, output in results['failed']:
            print("  [FAIL] {}".format(test))
            lines = output.split('\n')
            for line in lines:
                if 'Error' in line or 'FAILED' in line or 'error' in line.lower():
                    print("     {}".format(line.strip()[:70]))
                    break
    
    if results['error']:
        print("\n" + "-"*80)
        print("ERROR TESTS:")
        print("-"*80)
        for test, error in results['error']:
            print("  [ERROR] {}: {}".format(test, error[:60]))
    
    if results['timeout']:
        print("\n" + "-"*80)
        print("TIMEOUT TESTS:")
        print("-"*80)
        for test in results['timeout']:
            print("  [TIMEOUT] {}".format(test))
    
    print("\n" + "="*80)
    print("Completed: {}".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    print("="*80 + "\n")
    
    # Return exit code based on results
    if failed_count > 0 or error_count > 0 or timeout_count > 0:
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(run_tests())
