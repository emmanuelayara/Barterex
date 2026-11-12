// Load on the upload page, then run runValuationModalTests().
window.runValuationModalTests = function () {
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const element = id => document.getElementById(id);
  const base = {
    token: 'test-token', estimated_value: 1974, value_range: {low: 1678, high: 2270},
    confidence: 'very_low', market_listings: 1, sources_used: ['<img src=x onerror=alert(1)>'],
    risk: {level: 'MEDIUM', flags: [{message: 'Check the item condition.'}]},
    notes: "Some risk signals detected | Flags: {'message': 'Check the item condition.'}"
  };
  showAiValuationResult(base);
  assert(!element('aiComparableDetails').hidden && !element('aiComparableDetails').open, 'Listings must be collapsed');
  assert(!element('aiRiskDetails').hidden && !element('aiRiskDetails').open, 'Medium risk must be collapsed');
  assert(element('aiRiskSummary').textContent === 'Medium risk details', 'Medium-risk summary missing');
  assert(element('aiRiskFlags').textContent.includes('Check the item condition.'), 'Risk flags missing');
  assert(element('aiValuationNotes').textContent === 'Some risk signals detected', 'Raw duplicate flags were not removed');
  assert(element('aiComparableContent').textContent.includes('<img'), 'Source text missing');
  assert(!element('aiComparableContent').querySelector('img'), 'Source markup must not execute');
  assert(!element('aiConfidenceBadge'), 'Confidence must not be shown');
  element('aiComparableDetails').open = true;
  element('aiRiskDetails').open = true;
  showAiValuationResult({...base, market_listings: 0, sources_used: [], risk: {level: 'HIGH', flags: []}, notes: ''});
  assert(!element('aiComparableDetails').open && !element('aiRiskDetails').open, 'New results must reset disclosures');
  assert(element('aiComparableContent').textContent.includes('0 comparable listings'), 'Zero listings should be represented');
  assert(element('aiValuationSubtitle').textContent.includes('higher risk'), 'High-risk warning must remain visible');
  assert(!element('aiRiskDetails').hidden && element('aiRiskFlags').hidden, 'Empty high-risk details must not retain old flags');
  showAiValuationResult({...base, market_listings: null, sources_used: [], risk: {level: 'LOW', flags: []}, notes: ''});
  assert(element('aiComparableDetails').hidden && element('aiRiskDetails').hidden, 'Unavailable details must be hidden');
  return 'Valuation modal checks passed';
};
