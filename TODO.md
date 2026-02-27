# TODO - Fix Message Delivery Issue

## Issue: Messages not being received by cashier, registrar, and accounting

### Root Cause
The `Conversation` model has `unique_together = ['student', 'office', 'subject']` which prevents creating multiple conversations between the same student and office with the same subject. This causes `get_or_create` to return an existing conversation instead of creating a new one, and messages may not be properly delivered.

### Fix Plan
- [x] Analyze the issue and identify root cause
- [ ] Fix the unique_together constraint in models.py - remove 'subject' from unique constraint
- [ ] Create database migration for the model change
- [ ] Test the fix

### Changes Made
1. Removed 'subject' from unique_together constraint in Conversation model to allow multiple conversations per student-office pair
