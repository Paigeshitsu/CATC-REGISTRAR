# System Impact Map: Rush Feature for All Document Requests

## Analysis Summary

The rush feature is **already implemented** in the backend but is **currently restricted** in the UI to only TOR (Transcript of Records) documents.

### Current Implementation Status

1. **Model** ([`requests_app/models.py`](requests_app/models.py:176)): 
   - `rush_processing` BooleanField exists on `DocumentRequest` model
   - [`get_price()`](requests_app/models.py:181) correctly applies 2x multiplier when `rush_processing=True`

2. **Views** ([`requests_app/views.py`](requests_app/views.py:346)):
   - Rush processing is properly handled for ALL document types
   - Line 346: `rush_requested = request.POST.get(f'rush_{base.id}') == '1'`
   - Line 356: `rush_processing=rush_requested` is passed to `DocumentRequest.objects.create()`

3. **Template** ([`requests_app/templates/dashboard.html`](requests_app/templates/dashboard.html:69)):
   - **PROBLEM**: Rush checkbox is wrapped in `{% if doc.is_tor %}` condition
   - This restricts rush to only TOR documents

---

## Required Change

### File: [`requests_app/templates/dashboard.html`](requests_app/templates/dashboard.html:69-76)

**Change**: Remove the `{% if doc.is_tor %}` condition that wraps the rush checkbox.

**Current code (lines 69-76)**:
```html
{% if doc.is_tor %}
<div class="form-check mt-2">
    <input class="form-check-input" type="checkbox" name="rush_{{ doc.id }}" id="rush_{{ doc.id }}" value="1">
    <label class="form-check-label small text-warning fw-bold" for="rush_{{ doc.id }}">
        <i class="bi bi-lightning-fill"></i> Rush (1 Day) - 2x Price
    </label>
</div>
{% endif %}
```

**Required code**:
```html
<div class="form-check mt-2">
    <input class="form-check-input" type="checkbox" name="rush_{{ doc.id }}" id="rush_{{ doc.id }}" value="1">
    <label class="form-check-label small text-warning fw-bold" for="rush_{{ doc.id }}">
        <i class="bi bi-lightning-fill"></i> Rush (1 Day) - 2x Price
    </label>
</div>
```

---

## Impact Assessment

- **Backend**: No changes required - already supports rush for all documents
- **Database**: No changes required - migration 0028 already added the field
- **User Experience**: Users will now see the rush option for ALL document types, not just TOR

---

## Files Touched

| File | Change | Reason |
|------|--------|--------|
| `requests_app/templates/dashboard.html` | Remove conditional `{% if doc.is_tor %}` wrapper | Make rush checkbox visible for all document types |
