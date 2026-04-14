
    function toggleDelivery(selectElement, docId) {
        // Delivery options are always visible now - no toggling needed
    }
    
    function handleDeliveryChange(selectElement, docId) {
        // Show popup modal notice when LBC Delivery is selected
        if (selectElement.value === 'LBC') {
            var lbcModal = new bootstrap.Modal(document.getElementById('lbcNoticeModal'));
            lbcModal.show();
        }
        // Also call toggleDelivery to show/hide the wrapper
        toggleDelivery(selectElement, docId);
    }
    
    function showApprovalNotice(event) {
        // Let the form submit normally - the modal will show after submission via messages
        return true;
    }
    
     // Run on page load - show delivery options for pre-selected documents
    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('.selection-box').forEach(function(select) {
            if (select.value !== 'none') {
                toggleDelivery(select, select.name.replace('selection_', ''));
            }
        });
    });

    // LBC Booking Functions
    window.currentLBCStep = 1;
    window.currentTrackingNumber = '';
    
    

    
    function lbcNextStep(step) {
        var targetStep = document.getElementById('lbc-step-' + step);
        if (!targetStep) {
            return;
        }

        // Hide all steps first, then explicitly show the target.
        document.querySelectorAll('.lbc-step').forEach(function(el) {
            el.classList.remove('active');
            el.style.display = 'none';
        });

        targetStep.classList.add('active');
        targetStep.style.display = 'block';
        
        // Update step indicators
        document.querySelectorAll('.lbc-step-indicator .step').forEach(function(el, index) {
            el.classList.remove('active', 'completed');
            if (index + 1 <= step) el.classList.add('active');
            if (index + 1 < step) el.classList.add('completed');
        });
        
        // Update confirmation if step 4
        if (step === 4) updateLBCConfirmation();
    }

    function goToLbcReceiverStep() {
        lbcNextStep(2);
    }
    
    function validateLBCStep(step) {
        if (step === 2) {
            // Validate receiver fields
            var required = ['lbc-receiver-firstname', 'lbc-receiver-lastname', 'lbc-receiver-phone', 
                           'lbc-receiver-floor', 'lbc-receiver-street', 'lbc-receiver-barangay', 
                           'lbc-receiver-city', 'lbc-receiver-province'];
            for (var i = 0; i < required.length; i++) {
                var field = document.getElementById(required[i]);
                if (!field.value.trim()) {
                    field.classList.add('is-invalid');
                    return false;
                } else {
                    field.classList.remove('is-invalid');
                }
            }
        }
        return true;
    }
    
    function updateLBCConfirmation() {
        var senderInfo = document.getElementById('lbc-sender-firstname').value + ' ' + 
                        document.getElementById('lbc-sender-lastname').value + '<br>' +
                        document.getElementById('lbc-sender-address').value;
        
        var receiverInfo = document.getElementById('lbc-receiver-firstname').value + ' ' + 
                          document.getElementById('lbc-receiver-lastname').value + '<br>' +
                          document.getElementById('lbc-receiver-floor').value + ', ' +
                          document.getElementById('lbc-receiver-street').value + '<br>' +
                          document.getElementById('lbc-receiver-barangay').value + ', ' +
                          document.getElementById('lbc-receiver-city').value + ', ' +
                          document.getElementById('lbc-receiver-province').value;
        
        var serviceType = document.getElementById('lbc-service-type');
        var serviceName = serviceType.options[serviceType.selectedIndex].text;
        
        var packageInfo = document.getElementById('lbc-package-content').value + ' (' + 
                         document.getElementById('lbc-package-count').value + ' item(s), ' +
                         document.getElementById('lbc-package-weight').value + ' kg)<br>' +
                         'Service: ' + serviceName;
        
        // Calculate estimated delivery
        var today = new Date();
        var deliveryDays = serviceType.value === 'express' ? 2 : 5;
        var deliveryDate = new Date(today.getTime() + (deliveryDays * 24 * 60 * 60 * 1000));
        var deliveryEstimate = deliveryDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        
        document.getElementById('confirm-sender').innerHTML = senderInfo;
        document.getElementById('confirm-receiver').innerHTML = receiverInfo;
        document.getElementById('confirm-package').innerHTML = packageInfo;
        document.getElementById('confirm-delivery').textContent = deliveryEstimate;
    }
    
    function lbcBookShipment() {
        // Generate a tracking number (simulated for now)
        // NOTE: In production, this should come from actual LBC API booking
        var trackingNum = 'LBC' + Date.now().toString().slice(-10);
        currentTrackingNumber = trackingNum;
        
        // Use the batch ID from the modal opener
        var batchId = window.currentLBCBatchId;
        
        // Update form fields
        document.getElementById('tracking-number-display').textContent = trackingNum;
        document.getElementById('lbc_tracking_input').value = trackingNum;
        document.getElementById('lbc_batch_id_input').value = batchId || '';
        
        // Store the booking info
        var bookingData = {
            tracking: trackingNum,
            sender: {
                name: document.getElementById('lbc-sender-firstname').value + ' ' + document.getElementById('lbc-sender-lastname').value,
                phone: document.getElementById('lbc-sender-phone').value,
                address: document.getElementById('lbc-sender-address').value
            },
            receiver: {
                firstname: document.getElementById('lbc-receiver-firstname').value,
                lastname: document.getElementById('lbc-receiver-lastname').value,
                phone: document.getElementById('lbc-receiver-phone').value,
                address: document.getElementById('lbc-receiver-floor').value + ', ' + document.getElementById('lbc-receiver-street').value + ', ' + document.getElementById('lbc-receiver-barangay').value + ', ' + document.getElementById('lbc-receiver-city').value + ', ' + document.getElementById('lbc-receiver-province').value
            },
            package: {
                content: document.getElementById('lbc-package-content').value,
                count: document.getElementById('lbc-package-count').value,
                weight: document.getElementById('lbc-package-weight').value,
                service: document.getElementById('lbc-service-type').value
            }
        };
        
        document.getElementById('lbc_receiver_input').value = JSON.stringify(bookingData.receiver);
        document.getElementById('lbc_package_input').value = JSON.stringify(bookingData.package);
        
        // Move to tracking view
        document.querySelectorAll('.lbc-step-indicator .step').forEach(function(el, index) {
            el.classList.remove('active');
            el.classList.add('completed');
        });
        
        document.querySelectorAll('.lbc-step').forEach(function(el) {
            el.classList.remove('active');
        });
        document.getElementById('lbc-step-5').classList.add('active');
        
        // Initialize tracking timeline with sample data
        initializeTrackingTimeline(trackingNum);
        
        // Submit booking via AJAX to save tracking number
        var form = document.getElementById('lbcBookingForm');
        var formData = new FormData(form);
        
        fetch('', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            console.log('LBC Booking response:', data);
            if (data.success) {
                // Show success - tracking saved
                console.log('Tracking number saved successfully');
                // Close the LBC booking modal and reload to show updated buttons
                var modal = bootstrap.Modal.getInstance(document.getElementById('lbcBookingModal'));
                if (modal) {
                    modal.hide();
                }
                // Reload page after a short delay to show TRACK button
                setTimeout(function() {
                    window.location.reload();
                }, 1500);
            }
        })
        .catch(function(error) {
            console.error('Error saving booking:', error);
        });
    }
    
    function initializeTrackingTimeline(trackingNum) {
        // Show loading state
        document.getElementById('tracking-status').textContent = 'PROCESSING';
        document.getElementById('tracking-status').className = 'badge bg-warning';
        
        // Sample timeline data (in production, this would come from the API)
        var timelineData = [
            { datetime: new Date().toLocaleString(), location: 'Legazpi City, Albay', status: 'Shipment booked and pending pickup' },
            { datetime: '', location: 'Legazpi City, Albay', status: 'Picked up by LBC Rider' },
            { datetime: '', location: 'Legazpi City Hub', status: 'Arrived at LBC Legazpi Hub' },
            { datetime: '', location: 'Legazpi City Hub', status: 'In transit to destination' },
            { datetime: '', location: 'Destination City', status: 'Out for delivery' },
            { datetime: '', location: 'Destination', status: 'Delivered' }
        ];
        
        // Populate timeline
        var timelineHTML = '';
        timelineData.forEach(function(item, index) {
            timelineHTML += '<div class="tracking-item">' +
                '<div class="small text-muted">' + (item.datetime || 'Pending...') + '</div>' +
                '<div class="fw-bold text-' + (index === timelineData.length - 1 ? 'success' : 'dark') + '">' + item.status + '</div>' +
                '<div class="small text-info"><i class="bi bi-geo-alt"></i> ' + item.location + '</div>' +
            '</div>';
        });
        
        document.getElementById('tracking-timeline').innerHTML = timelineHTML;
    }
    
    function refreshTracking() {
        // Call the Django LBC API to get real-time tracking
        if (currentTrackingNumber) {
            var apiUrl = '/api/track/' + currentTrackingNumber + '/';
            
            fetch(apiUrl)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateTrackingDisplay(data.data);
                    } else if (data.data) {
                        // Django returns data in data field
                        updateTrackingDisplay(data.data);
                    } else {
                        // Keep showing simulated data if API fails
                        console.log('Using simulated tracking data');
                    }
                })
                .catch(error => {
                    console.log('Tracking API not available, showing simulated data');
                });
        }
    }
    
    function updateTrackingDisplay(data) {
        if (data.status) {
            var statusBadge = document.getElementById('tracking-status');
            if (data.status.toLowerCase().includes('delivered')) {
                statusBadge.textContent = 'DELIVERED';
                statusBadge.className = 'badge bg-success';
            } else if (data.status.toLowerCase().includes('transit') || data.status.toLowerCase().includes('shipment')) {
                statusBadge.textContent = 'IN TRANSIT';
                statusBadge.className = 'badge bg-primary';
            } else {
                statusBadge.textContent = data.status;
                statusBadge.className = 'badge bg-info';
            }
        }
        
        if (data.timeline && data.timeline.length > 0) {
            var timelineHTML = '';
            data.timeline.forEach(function(item, index) {
                timelineHTML += '<div class="tracking-item">' +
                    '<div class="small text-muted">' + (item.dateTime || 'Pending...') + '</div>' +
                    '<div class="fw-bold text-' + (index === 0 ? 'success' : 'dark') + '">' + (item.status || 'Update') + '</div>' +
                    '<div class="small text-info"><i class="bi bi-geo-alt"></i> ' + (item.location || 'Unknown') + '</div>' +
                '</div>';
            });
            document.getElementById('tracking-timeline').innerHTML = timelineHTML;
        }
    }
    
    // Helper function to get CSRF token
    function getCsrfToken() {
        // Try to get from cookie
        var name = 'csrftoken';
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // View Live Tracking from request history
     function viewLiveTracking(trackingNumber, saveNotification) {
        // Update modal with tracking number
        document.getElementById('modal-tracking-number').textContent = trackingNumber;
        document.getElementById('modal-tracking-status').textContent = 'LOADING...';
        document.getElementById('modal-tracking-status').className = 'badge bg-warning';
        document.getElementById('modal-tracking-timeline').innerHTML = '<div class="text-center py-3"><div class="spinner-border text-primary"></div></div>';

        // Show modal FIRST, then fetch data (prevent race condition)
        var modalEl = document.getElementById('liveTrackingModal');
        var modal = bootstrap.Modal.getOrCreateInstance(modalEl, {
            backdrop: 'static',
            keyboard: false
        });
        modal.show();
        
         // Determine API endpoint
         var apiEndpoint = saveNotification ? '/api/track/notify/' : '/api/track/';
         var apiUrl = apiEndpoint + encodeURIComponent(trackingNumber) + '/';
         
         var fetchOptions = {
             method: saveNotification ? 'POST' : 'GET',
             headers: {
                 'Content-Type': 'application/json',
                 'X-CSRFToken': getCsrfToken()
             }
         };
        
        // Use fetch with proper error handling
        fetch(apiUrl, fetchOptions)
            .then(function(response) {
                if (!response.ok) {
                    throw new Error('HTTP error! status: ' + response.status);
                }
                return response.json();
            })
            .then(function(data) {
                var trackingData = data.success ? data.data : data;
                
                // Update status
                var statusBadge = document.getElementById('modal-tracking-status');
                var markDeliveredBtn = document.getElementById('markDeliveredBtn');
                if (trackingData && trackingData.status) {
                    statusBadge.textContent = trackingData.status.toUpperCase();
                    
                    var statusLower = trackingData.status.toLowerCase();
                    if (statusLower.includes('delivered')) {
                        statusBadge.className = 'badge bg-success';
                        markDeliveredBtn.style.display = 'none';
                    } else if (statusLower.includes('transit') || statusLower.includes('shipment')) {
                        statusBadge.className = 'badge bg-primary';
                        markDeliveredBtn.style.display = 'inline-block';
                    } else if (statusLower.includes('pending')) {
                        statusBadge.className = 'badge bg-warning text-dark';
                        markDeliveredBtn.style.display = 'inline-block';
                    } else {
                        statusBadge.className = 'badge bg-info';
                        markDeliveredBtn.style.display = 'inline-block';
                    }
                } else {
                    statusBadge.textContent = 'UNKNOWN';
                    statusBadge.className = 'badge bg-secondary';
                    markDeliveredBtn.style.display = 'inline-block';
                }
                
                // Update timeline
                var timelineEl = document.getElementById('modal-tracking-timeline');
                if (trackingData && trackingData.timeline && trackingData.timeline.length > 0) {
                    var timelineHTML = '';
                    trackingData.timeline.forEach(function(item, index) {
                        timelineHTML += '<div class="tracking-item">' +
                            '<div class="small text-muted">' + (item.dateTime || 'Pending...') + '</div>' +
                            '<div class="fw-bold text-' + (index === 0 ? 'success' : 'dark') + '">' + (item.status || 'Update') + '</div>' +
                            '<div class="small text-info"><i class="bi bi-geo-alt"></i> ' + (item.location || 'Unknown') + '</div>' +
                        '</div>';
                    });
                    timelineEl.innerHTML = timelineHTML;
                } else {
                    timelineEl.innerHTML = '<div class="text-center text-muted py-3">No tracking updates available yet.</div>';
                }
                
                // Show notification saved message if applicable
                if (saveNotification && data.notification_saved) {
                    console.log('Notification saved successfully');
                }
            })
             .catch(function(error) {
                 console.error('Tracking API error:', error);
                 // Fallback to show mock data when API fails
                 document.getElementById('modal-tracking-status').textContent = 'AVAILABLE';
                 document.getElementById('modal-tracking-status').className = 'badge bg-info';
                 
                 // Always show the tracking number and at least initial timeline
                 document.getElementById('modal-tracking-timeline').innerHTML = 
                     '<div class="tracking-item">' +
                         '<div class="small text-muted">' + new Date().toLocaleString() + '</div>' +
                         '<div class="fw-bold text-success">Tracking number available</div>' +
                         '<div class="small text-info"><i class="bi bi-geo-alt"></i> Shipment pending processing</div>' +
                     '</div>' +
                     '<div class="tracking-item">' +
                         '<div class="small text-muted">Pending...</div>' +
                         '<div class="fw-bold text-dark">Awaiting LBC pickup</div>' +
                         '<div class="small text-info"><i class="bi bi-geo-alt"></i> Legazpi City, Albay</div>' +
                     '</div>' +
                     '<div class="tracking-item">' +
                         '<div class="small text-muted">Pending...</div>' +
                         '<div class="fw-bold text-muted">In transit to destination</div>' +
                         '<div class="small text-info"><i class="bi bi-geo-alt"></i> --</div>' +
                     '</div>';
             });
    }
    
    // Refresh tracking in modal
    function refreshModalTracking() {
        var trackingNumber = document.getElementById('modal-tracking-number').textContent;
        if (trackingNumber && trackingNumber !== '--') {
            viewLiveTracking(trackingNumber);
        }
    }
    
    // Save tracking to notifications (uses combined endpoint)

    
    // Mark package as delivered
    function markAsDelivered() {
        var trackingNumber = document.getElementById('modal-tracking-number').textContent;
        if (trackingNumber && trackingNumber !== '--') {
            var csrfToken = getCsrfToken();
            
            fetch('/api/mark-delivered/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ tracking_number: trackingNumber })
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success) {
                    // Update the status badge in the modal
                    var statusBadge = document.getElementById('modal-tracking-status');
                    statusBadge.textContent = 'DELIVERED';
                    statusBadge.className = 'badge bg-success fs-6';
                    
                    // Hide Mark as Delivered button
                    var markDeliveredBtn = document.getElementById('markDeliveredBtn');
                    markDeliveredBtn.style.display = 'none';
                    
                    alert('✓ Package marked as delivered!');
                    
                    // Close the modal after a short delay
                    setTimeout(function() {
                        var modal = bootstrap.Modal.getInstance(document.getElementById('liveTrackingModal'));
                        if (modal) {
                            modal.hide();
                        }
                        // Reload page to update the dashboard
                        window.location.reload();
                    }, 1500);
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(function(error) {
                console.error('Error marking delivered:', error);
                alert('Error marking as delivered. Please try again.');
            });
        }
    }

    function prepareLbcModal(batchId) {
        window.currentLBCBatchId = batchId;
        document.getElementById('lbc_batch_id_input').value = batchId || '';
        document.getElementById('lbc_tracking_input').value = '';
        document.getElementById('tracking-number-display').textContent = '--';
        document.getElementById('tracking-status').textContent = 'PENDING';
        document.getElementById('tracking-status').className = 'badge bg-success';
        document.getElementById('tracking-estimate').textContent = '';
        document.getElementById('tracking-timeline').innerHTML = '';
        lbcNextStep(1);
    }

    document.addEventListener('DOMContentLoaded', function() {
        var nextToReceiverBtn = document.getElementById('lbc-next-to-receiver-btn');
        if (nextToReceiverBtn) {
            nextToReceiverBtn.addEventListener('click', function() {
                lbcNextStep(2);
            });
        }
    });

    window.showLbcModal = prepareLbcModal;
    window.prepareLbcModal = prepareLbcModal;
    window.lbcNextStep = lbcNextStep;
    window.goToLbcReceiverStep = goToLbcReceiverStep;

