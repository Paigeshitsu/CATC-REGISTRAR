const express = require('express');
const puppeteer = require('puppeteer');

const app = express();
const PORT = process.env.PORT || 3000;

// ============================================
// PROCESS-LEVEL ERROR HANDLING (Production Safety)
// ============================================

// Handle uncaught exceptions gracefully
process.on('uncaughtException', (err) => {
    console.error(`[FATAL] Uncaught Exception: ${err.message}`);
    console.error(err.stack);
    // Give time for logging before exit
    setTimeout(() => {
        process.exit(1);
    }, 1000);
});

// Handle unhandled promise rejections
process.on('unhandledRejection', (reason, promise) => {
    console.error(`[FATAL] Unhandled Promise Rejection at: ${promise}`);
    console.error(`[FATAL] Reason: ${reason}`);
});

// Middleware for JSON parsing errors
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// LBC Express tracking URL
const LBC_TRACKING_URL = 'https://www.lbcexpress.com/track/';

/**
 * Scrapes LBC Express tracking information for a given tracking number
 * @param {string} trackingNum - The LBC tracking number
 * @returns {Object} - Tracking information including status, timeline events
 */
async function scrapeLBCTracking(trackingNum) {
    let browser = null;
    
    try {
        // Launch headless browser
        browser = await puppeteer.launch({
            headless: 'new',
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        });

        const page = await browser.newPage();
        
        // Set user agent to avoid being blocked
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
        
        // Set viewport
        await page.setViewport({ width: 1280, height: 800 });

        // Navigate to the tracking page
        await page.goto(LBC_TRACKING_URL, {
            waitUntil: 'networkidle2',
            timeout: 30000
        });

        // Wait for the search input to be available
        await page.waitForSelector('input[type="text"], input[name*="track"], input[placeholder*="Track"], #tracking-number, .tracking-input', {
            timeout: 10000
        }).catch(() => {
            // If specific selector not found, try to find any text input on the page
            return page.waitForSelector('input[type="text"]', { timeout: 10000 });
        });

        // Find and fill the tracking number input
        // Try multiple selectors commonly used for tracking input
        const inputSelectors = [
            'input[type="text"]',
            'input[name="tracking_number"]',
            'input[name="track"]',
            'input[id="tracking-number"]',
            'input[placeholder*="Track"]',
            'input[placeholder*="track"]',
            '#tracking-number',
            '.tracking-input input',
            'input.tracking-input'
        ];

        let inputElement = null;
        for (const selector of inputSelectors) {
            try {
                inputElement = await page.$(selector);
                if (inputElement) break;
            } catch (e) {
                continue;
            }
        }

        if (!inputElement) {
            throw new Error('TRACKING_INPUT_NOT_FOUND');
        }

        // Clear and type the tracking number
        await inputElement.click({ clickCount: 3 });
        await inputElement.type(trackingNum, { delay: 100 });

        // Find and click the search button
        // Try multiple selectors for the search button
        const buttonSelectors = [
            'button[type="submit"]',
            'button:has-text("Track")',
            'button:has-text("Search")',
            'input[type="submit"]',
            '.track-button',
            '#track-btn',
            'button.track-btn',
            '.search-btn',
            'button.search-button'
        ];

        let searchButton = null;
        for (const selector of buttonSelectors) {
            try {
                searchButton = await page.$(selector);
                if (searchButton) break;
            } catch (e) {
                continue;
            }
        }

        if (searchButton) {
            await searchButton.click();
        } else {
            // Press Enter if no button found
            await inputElement.press('Enter');
        }

        // Wait for results to load
        await page.waitForFunction(() => {
            return document.readyState === 'complete';
        }, { timeout: 15000 });

        // Additional wait for dynamic content
        await new Promise(resolve => setTimeout(resolve, 3000));

        // Check for "not found" messages
        const notFoundSelectors = [
            '*:not(script):not(style)',
        ];
        
        const pageContent = await page.content();
        const notFoundPatterns = [
            'not found',
            'no results',
            'invalid',
            'tracking number not found',
            'no record'
        ];
        
        const lowerContent = pageContent.toLowerCase();
        for (const pattern of notFoundPatterns) {
            if (lowerContent.includes(pattern)) {
                // Check if it's actually showing results
                const hasResults = await page.evaluate(() => {
                    const tables = document.querySelectorAll('table');
                    const lists = document.querySelectorAll('ul, ol');
                    const divs = document.querySelectorAll('.tracking-result, .result, .status');
                    return tables.length > 0 || lists.length > 0 || divs.length > 0;
                });
                
                if (!hasResults) {
                    throw new Error('TRACKING_NOT_FOUND');
                }
            }
        }

        // Extract tracking data
        const trackingData = await page.evaluate(() => {
            const result = {
                trackingNumber: '',
                status: '',
                origin: '',
                destination: '',
                timeline: [],
                error: null
            };

            // Try to get tracking number from the page
            try {
                const trackingNumElements = document.querySelectorAll('[class*="tracking"], [id*="tracking"], .tracking-number, .track-number');
                for (const el of trackingNumElements) {
                    const text = el.textContent.trim();
                    if (text.match(/^\d{10,}$/) || text.match(/^[A-Z0-9]{8,}$/i)) {
                        result.trackingNumber = text;
                        break;
                    }
                }
            } catch (e) {
                // Ignore
            }

            // Try to get status
            try {
                const statusSelectors = [
                    '.status',
                    '.tracking-status',
                    '[class*="status"]',
                    '[id*="status"]',
                    '.current-status',
                    '.shipment-status'
                ];
                
                for (const selector of statusSelectors) {
                    const statusEl = document.querySelector(selector);
                    if (statusEl && statusEl.textContent.trim()) {
                        result.status = statusEl.textContent.trim();
                        break;
                    }
                }
            } catch (e) {
                // Ignore
            }

            // Try to get origin and destination
            try {
                const originDestSelectors = [
                    '.origin',
                    '.destination',
                    '[class*="origin"]',
                    '[class*="destination"]',
                    '.sender',
                    '.receiver',
                    '.from',
                    '.to'
                ];
                
                for (const selector of originDestSelectors) {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        const text = el.textContent.trim();
                        if (text && text.length < 100) {
                            if (!result.origin && text.toLowerCase().includes('from')) {
                                result.origin = text.replace(/from/i, '').trim();
                            }
                            if (!result.destination && text.toLowerCase().includes('to')) {
                                result.destination = text.replace(/to/i, '').trim();
                            }
                        }
                    });
                }
            } catch (e) {
                // Ignore
            }

            // Try to get timeline data from table or list
            try {
                // Try table first
                const tableRows = document.querySelectorAll('table tbody tr, table tr');
                
                if (tableRows.length > 0) {
                    tableRows.forEach(row => {
                        const cells = row.querySelectorAll('td, th');
                        if (cells.length >= 2) {
                            const dateTime = cells[0]?.textContent?.trim() || '';
                            const location = cells[1]?.textContent?.trim() || '';
                            const status = cells[2]?.textContent?.trim() || '';
                            
                            if (dateTime || location || status) {
                                result.timeline.push({
                                    dateTime: dateTime,
                                    location: location,
                                    status: status
                                });
                            }
                        }
                    });
                }

                // Try list/div format if no table data
                if (result.timeline.length === 0) {
                    const timelineItems = document.querySelectorAll('.timeline-item, .tracking-item, .history-item, [class*="timeline"] li, [class*="history"] li, .event');
                    
                    timelineItems.forEach(item => {
                        const text = item.textContent.trim();
                        if (text) {
                            // Try to parse the text into date/time, location, status
                            const parts = text.split(/\n|,/);
                            const timelineEntry = {
                                dateTime: '',
                                location: '',
                                status: ''
                            };
                            
                            parts.forEach(part => {
                                const trimmed = part.trim();
                                if (trimmed.match(/\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}/) || 
                                    trimmed.match(/\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}/) ||
                                    trimmed.match(/jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec/i)) {
                                    timelineEntry.dateTime = trimmed;
                                } else if (trimmed.length > 3 && !trimmed.match(/^\d+$/)) {
                                    if (!timelineEntry.location) {
                                        timelineEntry.location = trimmed;
                                    } else {
                                        timelineEntry.status = trimmed;
                                    }
                                }
                            });
                            
                            if (timelineEntry.dateTime || timelineEntry.location || timelineEntry.status) {
                                result.timeline.push(timelineEntry);
                            }
                        }
                    });
                }
            } catch (e) {
                // Ignore
            }

            return result;
        });

        // If no timeline found, try an alternative approach - look for specific patterns
        if (trackingData.timeline.length === 0) {
            const altTimelineData = await page.evaluate(() => {
                const timeline = [];
                
                // Look for any elements that might contain tracking info
                const allDivs = document.querySelectorAll('div');
                allDivs.forEach(div => {
                    const text = div.textContent;
                    // Check if it looks like a timeline entry (contains date and some status info)
                    if (text.match(/\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}/) || 
                        text.match(/\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}/) ||
                        text.match(/jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec/i)) {
                        
                        if (text.length > 20 && text.length < 500) {
                            const lines = text.split(/\n/).filter(l => l.trim());
                            if (lines.length >= 2) {
                                timeline.push({
                                    dateTime: lines[0]?.trim() || '',
                                    location: lines[1]?.trim() || '',
                                    status: lines.slice(2).join(', ').trim() || ''
                                });
                            }
                        }
                    }
                });
                
                return timeline.slice(0, 20); // Limit to 20 entries
            });
            
            if (altTimelineData.length > 0) {
                trackingData.timeline = altTimelineData;
            }
        }

        // Set tracking number if not found
        if (!trackingData.trackingNumber) {
            trackingData.trackingNumber = trackingNum;
        }

        // Clean up empty timeline entries
        trackingData.timeline = trackingData.timeline.filter(entry => {
            return entry.dateTime || entry.location || entry.status;
        });

        // If still no data found, throw error
        if (!trackingData.status && trackingData.timeline.length === 0) {
            throw new Error('NO_TRACKING_DATA');
        }

        return trackingData;

    } catch (error) {
        const errorMessage = error.message;
        
        if (errorMessage === 'TRACKING_NOT_FOUND' || errorMessage === 'TRACKING_INPUT_NOT_FOUND' || errorMessage === 'NO_TRACKING_DATA') {
            throw error;
        }
        
        // Timeout or network error
        if (errorMessage.includes('timeout') || errorMessage.includes('net::')) {
            throw new Error('NETWORK_TIMEOUT');
        }
        
        throw error;
    } finally {
        if (browser) {
            await browser.close();
        }
    }
}

// API Endpoint: GET /api/track/:trackingNum
app.get('/api/track/:trackingNum', async (req, res) => {
    const { trackingNum } = req.params;
    
    // Validate tracking number
    if (!trackingNum || trackingNum.trim() === '') {
        return res.status(400).json({
            success: false,
            error: 'Tracking number is required',
            message: 'Please provide a valid LBC tracking number'
        });
    }

    try {
        const trackingData = await scrapeLBCTracking(trackingNum.trim());
        
        return res.status(200).json({
            success: true,
            data: trackingData
        });
        
    } catch (error) {
        const errorMessage = error.message;
        
        console.error(`Tracking error for ${trackingNum}:`, errorMessage);
        
        // Handle specific error types
        if (errorMessage === 'TRACKING_NOT_FOUND' || errorMessage === 'NO_TRACKING_DATA') {
            return res.status(404).json({
                success: false,
                error: 'Tracking Number Not Found',
                message: 'The provided tracking number was not found in the LBC system',
                trackingNumber: trackingNum
            });
        }
        
        if (errorMessage === 'NETWORK_TIMEOUT') {
            return res.status(500).json({
                success: false,
                error: 'Network Timeout',
                message: 'Unable to connect to LBC tracking server. Please try again later.',
                trackingNumber: trackingNum
            });
        }
        
        // Default server error
        return res.status(500).json({
            success: false,
            error: 'Server Error',
            message: 'An error occurred while processing your request',
            trackingNumber: trackingNum
        });
    }
});

// Health check endpoint
app.get('/health', (req, res) => {
    res.status(200).json({
        status: 'ok',
        service: 'LBC Tracking API'
    });
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
    console.log(`LBC Tracking API server running on http://0.0.0.0:${PORT}`);
    console.log(`Endpoint: GET http://localhost:${PORT}/api/track/:trackingNum`);
});
