s
# LBC Booking Modal Cleanup - CRITICAL FIX

## Status: 🔄 IN PROGRESS


2. [ ] Update dashboard.html 
   - [ ] Replace broken openLBCBookingModal() → Bootstrap modal trigger showLbcModal()
   - [ ] Remove malformed custom overlay JS (lines ~1260-1560) 
   - [ ] Fix step navigation (lbcNextStep simplified, validation preserved)
   - [ ] Complete form submission (lbcBookShipment → AJAX tracking save)
3. [ ] Test button/modal
4. [ ] Verify no JS errors  
5. [ ] Backend integration - Tracking saved to DB
6. [ ] attempt_completion - Task complete!
```

**Current Issue**: "BOOK SHIPPING" button does nothing (showLbcModal() missing)

**Next**: Clean dashboard.html → Fix button + modal
